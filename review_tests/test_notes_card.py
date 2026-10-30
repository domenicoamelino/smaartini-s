import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import meeting_review as review
import notes_card as card
import notes_store as store
import notes_models as models
import notes_ingestion as ingestion
from notes_document import combine_pages,all_blocks,fingerprint,validate_page
from test_notes_backend import image,page
import test_notes_http as http_fixture


class Card(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);store.init(self.root)
        self.session=card.create(self.root,'alice','chat:message','English');self.raw=image()
    def tearDown(self):self.tmp.cleanup()
    def prepare(self,count=2):
        card.metadata(self.root,self.session,{'title':'Project notes','date':'2026-10-30','count':count})
        for i in range(count):card.image(self.root,self.session,i,self.raw)
    def job(self,jid):
        with review.connection(self.root) as db:return dict(db.execute('SELECT * FROM notes_jobs WHERE id=?',(jid,)).fetchone())
    def document(self,jid):
        sources=store.source_pages(self.root,jid);result=[]
        for i,source in enumerate(sources):
            p=page();p['image_sha256']=source['sha256'];p['blocks'][0]['text']='page %d not approved'%(i+1);result.append(p)
        return combine_pages(result)
    def test_session_owner_idempotency_and_no_job_before_confirmation(self):
        self.assertEqual(card.create(self.root,'alice','chat:message','English')['id'],self.session['id'])
        with self.assertRaises(KeyError):card.get(self.root,self.session['id'],'bob')
        self.prepare();self.assertEqual(store.listing(self.root,'alice'),[])
        self.assertEqual(card.status(self.root,self.session)['state'],'waiting_upload')
    def test_valid_date_and_limits(self):
        for obj in [{'title':'','date':'2026-10-30','count':1},{'title':'A','date':'2026-02-30','count':1},
                    {'title':'A','date':'2026-10-30','count':11},{'title':'A','date':'2026-10-30','count':True}]:
            with self.assertRaises(ValueError):card.metadata(self.root,self.session,obj)
        with self.assertRaises(ValueError):store.submit(self.root,'alice','bad','A','English',[self.raw]*11)
    def test_retry_same_slot_and_metadata_are_immutable(self):
        self.prepare();card.image(self.root,self.session,0,self.raw)
        with self.assertRaises(review.Conflict):card.image(self.root,self.session,0,b'changed')
        with self.assertRaises(review.Conflict):card.metadata(self.root,self.session,{'title':'Changed','date':'2026-10-30','count':2})
    def test_missing_picture_never_starts(self):
        card.metadata(self.root,self.session,{'title':'A','date':'2026-10-30','count':2});card.image(self.root,self.session,0,self.raw)
        with self.assertRaises(ValueError):card.start(self.root,self.session)
        self.assertEqual(store.listing(self.root,'alice'),[])
    def test_concurrent_start_creates_one_job(self):
        self.prepare();ids=[];errors=[]
        def run():
            try:ids.append(card.start(self.root,self.session))
            except Exception as e:errors.append(e)
        threads=[threading.Thread(target=run) for _ in range(3)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(errors,[]);self.assertEqual(len(set(ids)),1);self.assertEqual(len(store.listing(self.root,'alice')),1)
        self.assertEqual(self.job(ids[0])['notes_date'],'2026-10-30')
        with self.assertRaises(review.Conflict):card.image(self.root,self.session,0,self.raw)
    def test_document_has_unique_ids_and_source_order(self):
        self.prepare();jid=card.start(self.root,self.session);doc=self.document(jid);validate_page(doc)
        self.assertEqual([b['id'] for b in all_blocks(doc)],['B000001','B000002'])
        self.assertEqual(len(store.view(self.root,jid,'alice')['sources']),2)
        self.assertEqual(store.original(self.root,jid,'alice',1)[1],self.raw)
        with self.assertRaises(KeyError):store.original(self.root,jid,'bob',1)
        with self.assertRaises(ValueError):store.original(self.root,jid,'alice',2)
        bad=copy.deepcopy(doc);bad['pages'][1]['blocks'][0]['id']='B000001'
        with self.assertRaises(ValueError):validate_page(bad)
    def test_combined_draft_one_ready_notice_and_approved_only_ingestion(self):
        self.prepare();jid=card.start(self.root,self.session)
        store.process_next(self.root,lambda *args:self.document(jid))
        self.assertEqual(store.view(self.root,jid,'alice')['job']['state'],'recap-queued')
        with review.connection(self.root) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM notices').fetchone()[0],0)
        def recap(job,stage,payload,work):
            return {'schema':'smartinis-notes-recap/1','page_sha256':fingerprint(payload['page']),
                'items':[{'kind':'open-question','text':b['text'],'evidence':[{'block_id':b['id'],'quote':b['text']}]} for b in all_blocks(payload['page'])]}
        store.process_next(self.root,recap);session=card.get(self.root,self.session['token']);status=card.status(self.root,session)
        self.assertIn('dashboard_path',status);self.assertNotIn('payload',status)
        self.assertIsNone(ingestion.document(store.folder(self.root,jid),self.root,'alice'))
        value=store.view(self.root,jid,'alice')
        self.assertIsNone(value['job']['approved'])
        self.assertFalse(store.process_next(self.root,recap))
        with review.connection(self.root) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM notices').fetchone()[0],1)
        store.act(self.root,jid,'alice',{'action':'approve','revision':value['job']['current'],'acknowledge_source_review':True})
        export=ingestion.document(store.folder(self.root,jid),self.root,'alice')
        self.assertIn(b'Date: 2026-10-30',export['raw'])
        source=store.source_pages(self.root,jid)[1];(store.folder(self.root,jid)/source['original']).write_bytes(b'tampered')
        with self.assertRaises(ValueError):ingestion.document(store.folder(self.root,jid),self.root,'alice')
    def test_sequential_extraction_retry_uses_completed_picture(self):
        self.prepare();jid=card.start(self.root,self.session);job=self.job(jid);work=self.root/'model-work';work.mkdir();calls=[]
        def infer(root,job,stage,payload,target,stop,source=None,**kwargs):
            calls.append(source['original'])
            if len(calls)==2:raise ValueError('Synthetic second-picture interruption')
            return page()
        with patch('notes_models._generate_single',side_effect=infer):
            with self.assertRaises(ValueError):models.generate(self.root,job,'extract',None,work)
            value=models.generate(self.root,job,'extract',None,work)
        self.assertEqual(calls,['original-001.png','original-002.png','original-002.png']);validate_page(value)
    def test_failure_has_recovery_link_not_ready_link(self):
        self.prepare();jid=card.start(self.root,self.session)
        def fail(*args):raise ValueError('Synthetic error')
        store.process_next(self.root,fail);status=card.status(self.root,card.get(self.root,self.session['token']))
        self.assertIn('recovery_path',status);self.assertNotIn('dashboard_path',status)

    def test_blank_drawing_response_gets_one_structural_retry(self):
        self.prepare();jid=card.start(self.root,self.session);job=self.job(jid)
        target=self.root/'blank-drawing';target.mkdir();source=store.source_pages(self.root,jid)[0]
        blank=page();blank['blocks'][0].update(kind='drawing',text='')
        with patch('notes_models._generate_single',side_effect=[blank,page()]) as infer:
            result=models._extracted_page(self.root,job,source,target)
        self.assertEqual(infer.call_count,2);self.assertEqual(result['blocks'][0]['text'],page()['blocks'][0]['text'])
        self.assertTrue((target/'validation-error.json').exists())
        self.assertTrue((target/'validation-retry-1').is_dir())
        self.assertEqual(models.BLOCK['properties']['text']['minLength'],1)

    def test_repeated_blank_drawings_fail_without_fabricating_text(self):
        self.prepare();jid=card.start(self.root,self.session);job=self.job(jid)
        blank=page();blank['blocks'][0].update(kind='drawing',text='')
        target=self.root/'repeat-blank';target.mkdir();source=store.source_pages(self.root,jid)[0]
        with patch('notes_models._generate_single',side_effect=lambda *a,**k:copy.deepcopy(blank)) as infer:
            with self.assertRaisesRegex(ValueError,'empty text/descriptions.*after one structural retry'):
                models._extracted_page(self.root,job,source,target)
        self.assertEqual(infer.call_count,2);self.assertFalse((target/'result.json').exists())

    def test_completed_invalid_response_is_preserved_and_only_retry_is_run(self):
        self.prepare();jid=card.start(self.root,self.session);job=self.job(jid)
        target=self.root/'completed-invalid';target.mkdir();source=store.source_pages(self.root,jid)[0]
        blank=page();blank['blocks'][0]['text']=''
        (target/'partial.txt').write_text(json.dumps(blank));(target/'metrics.json').write_text(json.dumps({'done_reason':'stop'}))
        (target/'request-metadata.json').write_text(json.dumps({'source_image_sha256':source['sha256']}))
        with patch('notes_models._generate_single',return_value=page()) as infer:
            models._extracted_page(self.root,job,source,target)
        self.assertEqual(infer.call_count,1);self.assertEqual(json.loads((target/'partial.txt').read_text())['blocks'][0]['text'],'')

    def test_recap_whitespace_quotes_resolve_to_exact_source_without_changing_words(self):
        payload={'page':page()};payload['page']['blocks'][0]['text']='FOR JCA, the NCG\nshould be responsible\nfor :'
        value={'schema':'smartinis-notes-recap/1','page_sha256':fingerprint(payload['page']),
            'items':[{'kind':'summary','text':'Responsibilities discussed.','evidence':[{'block_id':'B000001',
                'quote':'FOR JCA, the NCG should be responsible for :'}]}]}
        target=self.root/'quote-normalization';target.mkdir()
        with patch('notes_models._generate_single',return_value=value):
            result=models._recap_response(self.root,{},payload,target)
        self.assertEqual(result['items'][0]['evidence'][0]['quote'],payload['page']['blocks'][0]['text'])
        self.assertEqual(value['items'][0]['evidence'][0]['quote'],'FOR JCA, the NCG should be responsible for :')
        self.assertTrue((target/'evidence-whitespace-normalizations.json').exists())

    def test_recap_quote_changes_and_ambiguous_whitespace_matches_are_rejected(self):
        for source,quote in [('not approved','approval granted'),('alpha\nbeta and alpha beta','alpha\tbeta')]:
            payload={'page':page()};payload['page']['blocks'][0]['text']=source
            value={'schema':'smartinis-notes-recap/1','page_sha256':fingerprint(payload['page']),
                'items':[{'kind':'summary','text':'draft','evidence':[{'block_id':'B000001','quote':quote}]}]}
            target=self.root/'reject-quote';target.mkdir(exist_ok=True)
            with patch('notes_models._generate_single',return_value=value):
                with self.assertRaisesRegex(ValueError,'quote does not match'):
                    models._recap_response(self.root,{},payload,target)

    def test_completed_recap_response_can_be_revalidated_without_new_inference(self):
        payload={'page':page()};payload['page']['blocks'][0]['text']='alpha\nbeta'
        value={'schema':'smartinis-notes-recap/1','page_sha256':fingerprint(payload['page']),
            'items':[{'kind':'summary','text':'draft','evidence':[{'block_id':'B000001','quote':'alpha beta'}]}]}
        target=self.root/'saved-recap';target.mkdir()
        (target/'partial.txt').write_text(json.dumps(value));(target/'metrics.json').write_text(json.dumps({'done_reason':'stop'}))
        (target/'request-metadata.json').write_text(json.dumps({'page_sha256':fingerprint(payload['page'])}))
        with patch('notes_models._generate_single') as infer:
            result=models._recap_response(self.root,{},payload,target)
        infer.assert_not_called();self.assertEqual(result['items'][0]['evidence'][0]['quote'],'alpha\nbeta')

    def test_large_recap_is_chunked_without_losing_source_ids(self):
        self.prepare();jid=card.start(self.root,self.session);job=self.job(jid)
        document=page();document['blocks']=[]
        for i in range(40):
            block=copy.deepcopy(page()['blocks'][0]);block['id']='B%06d'%(i+1);block['text']=('source %d '%i)*70
            document['blocks'].append(block)
        work=self.root/'recap-work';work.mkdir();calls=[]
        def infer(root,job,stage,payload,target,stop,content_data=None,**kwargs):
            calls.append(content_data)
            if 'source_blocks' in content_data:
                b=content_data['source_blocks'][0]
                items=[{'kind':'summary','text':'draft','evidence':[{'block_id':b['id'],'quote':b['text'][:50]}]}]
            else:items=content_data['candidate_recaps_DATA']
            return {'schema':'smartinis-notes-recap/1','page_sha256':fingerprint(document),'items':items}
        with patch('notes_models._generate_single',side_effect=infer):
            value=models.generate(self.root,job,'recap',{'page':document},work)
        mapped=[b['id'] for call in calls if 'source_blocks' in call for b in call['source_blocks']]
        self.assertEqual(mapped,[b['id'] for b in document['blocks']])
        self.assertIn('candidate_recaps_DATA',calls[-1]);self.assertGreater(len(value['items']),1)


class CardHTTP(unittest.TestCase):
    setUp=http_fixture.NotesHTTP.setUp
    tearDown=http_fixture.NotesHTTP.tearDown
    # Exercise real worker card routing with the existing isolated HTTP fixture.
    def request(self,path,obj=None,headers=None):
        from urllib.request import Request
        data=None if obj is None else (obj if isinstance(obj,bytes) else json.dumps(obj).encode())
        with self.client.open(Request(self.base+path,data=data,headers=headers or {}),timeout=10) as response:
            return response.headers,response.read()
    def test_embedded_card_capability_upload_and_scoped_status(self):
        auth={'Authorization':'Bearer '+'x'*40,'X-Owner-Id':'alice','Content-Type':'application/json'}
        _,raw=self.request(card.API,{'request_key':'chat:one','language':'English'},auth);session=json.loads(raw)
        token=session['upload_token'];base=card.PREFIX
        headers,html=self.request(base+'/view/'+token)
        self.assertEqual(headers['Access-Control-Allow-Origin'],'*');self.assertNotIn(b'x'*40,html)
        self.assertIn(b'Confirm and process',html);self.assertIn(b'multiple',html)
        self.request(base+'/metadata/'+token,{'title':'Two pages','date':'2026-10-30','count':2},{'Content-Type':'application/json'})
        for i in range(2):self.request(base+'/image/'+token+'/'+str(i),image(),{'Content-Type':'image/png'})
        _,raw=self.request(base+'/start/'+token,{'confirmed':True},{'Content-Type':'application/json'})
        value=json.loads(raw);self.assertEqual(value['state'],'extract-queued');self.assertNotIn('dashboard_path',value)
        self.assertNotIn('owner',value);self.assertNotIn('payload',value)
        from urllib.error import HTTPError
        with self.assertRaises(HTTPError) as error:self.request(card.API+'/'+session['id'],headers={**auth,'X-Owner-Id':'bob'})
        self.assertEqual(error.exception.code,404)
        with self.assertRaises(HTTPError) as error:self.request(card.API,{'request_key':'no-auth'})
        self.assertEqual(error.exception.code,401)
        with self.assertRaises(HTTPError):self.request(base+'/approve/'+token,{'confirmed':True})


if __name__=='__main__':unittest.main()
