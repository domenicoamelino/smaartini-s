import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import test_notes_http as http_fixture
import notes_store as notes
import notes_presentation as presentation
import notes_ingestion as ingestion
import meeting_review as review
from notes_document import fingerprint,all_blocks
from test_notes_backend import image,page


class TwoStage(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'NOTES_TWO_STAGE':'1'});self.env.start();notes.init(self.root)
        self.jid=notes.submit(self.root,'alice','one','Diagram notes','English',image(),auto_recap=True)
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def extract(self):
        source=page();source['blocks'][0].update(kind='drawing',text='Client <script>alert(1)</script>')
        second=copy.deepcopy(source['blocks'][0]);second.update(id='B000002',kind='paragraph',text='API service')
        source['blocks'].append(second);source['relations']=[{'kind':'arrow','from':'B000001','to':'B000002','uncertainties':['Check direction'],'reviewed':False}]
        notes.process_next(self.root,lambda *args:source)
        return notes.view(self.root,self.jid,'alice')
    def action(self,name,**extra):
        value=notes.view(self.root,self.jid,'alice')
        return notes.act(self.root,self.jid,'alice',{'action':name,'revision':value['job']['current'],**extra})
    def generate(self):
        self.extract();self.action('approve-source',acknowledge_source_review=True)
        def model(job,stage,payload,work):
            self.assertEqual(stage,'final');b=all_blocks(payload['page'])[0]
            recap={'schema':'smartinis-notes-recap/1','page_sha256':fingerprint(payload['page']),
                'items':[{'kind':'summary','text':'Client and API discussed.','evidence':[{'block_id':b['id'],'quote':b['text']}]}]}
            return presentation.build(notes.folder(self.root,self.jid),payload,recap)
        notes.process_next(self.root,model)
        return notes.view(self.root,self.jid,'alice')
    def approve(self):return self.action('approve',acknowledge_source_review=True,acknowledge_final_review=True)
    def test_extraction_stops_for_first_approval_without_auto_recap(self):
        value=self.extract();self.assertEqual(value['job']['state'],'page-review');self.assertIsNone(notes.oldest(self.root))
        with self.assertRaises(review.Conflict):self.action('generate-recap')
        with self.assertRaises(review.Conflict):self.action('approve-source')
        self.assertIsNone(value['job']['approved'])
    def test_source_approval_is_audited_and_queues_only_final_generation(self):
        self.extract();value=self.action('approve-source',acknowledge_source_review=True)
        self.assertEqual(value['job']['state'],'final-queued');self.assertIsNone(value['job']['approved'])
        self.assertEqual(value['payload']['source_approval']['page_sha256'],fingerprint(value['payload']['page']))
        self.assertTrue(all(b['reviewed'] for b in all_blocks(value['payload']['page'])))
    def test_generated_result_requires_second_approval(self):
        value=self.generate();self.assertEqual(value['job']['state'],'recap-review')
        self.assertTrue(value['payload']['final_text']);self.assertEqual(len(value['payload']['diagrams']),1)
        self.assertIsNone(ingestion.document(notes.folder(self.root,self.jid),self.root,'alice'))
        with self.assertRaises(review.Conflict):self.action('approve',acknowledge_source_review=True)
        self.approve();export=ingestion.document(notes.folder(self.root,self.jid),self.root,'alice')
        self.assertIn(b'Client and API discussed.',export['raw']);self.assertIn(b'Diagram descriptions',export['raw'])
        self.assertNotIn(b'<svg',export['raw'])
    def test_final_text_edits_and_image_replacement_preserve_old_approval(self):
        value=self.generate();self.approve();old=ingestion.document(notes.folder(self.root,self.jid),self.root,'alice')
        value=self.action('save-final',final_text='User corrected final text.',diagram_descriptions=['User reviewed diagram description.'])
        self.assertNotEqual(value['job']['current'],value['job']['approved'])
        updated=notes.replace_diagram(self.root,self.jid,'alice',0,value['job']['current'],image())
        diagram=updated['payload']['diagrams'][0];self.assertEqual(diagram['origin'],'user-upload')
        self.assertEqual(notes.diagram_asset(self.root,self.jid,'alice',diagram['asset']['filename'])[0],'image/png')
        self.assertEqual(ingestion.document(notes.folder(self.root,self.jid),self.root,'alice')['sha256'],old['sha256'])
        self.approve();self.assertIn(b'User corrected final text.',ingestion.document(notes.folder(self.root,self.jid),self.root,'alice')['raw'])
    def test_source_edits_invalidate_final_generation_approval(self):
        value=self.generate();source=copy.deepcopy(value['payload']['page']);source['blocks'][0]['text']='Changed client'
        value=self.action('save-page',page=source)
        self.assertIsNone(value['payload']['recap']);self.assertNotIn('source_approval',value['payload'])
        with self.assertRaises(review.Conflict):self.approve()
    def test_svg_is_inert_and_preserves_uncertain_connections(self):
        value=self.generate();diagram=value['payload']['diagrams'][0]
        mime,raw=notes.diagram_asset(self.root,self.jid,'alice',diagram['asset']['filename'])
        self.assertEqual(mime,'image/svg+xml');tree=ET.fromstring(raw)
        self.assertEqual(tree.findall('.//{http://www.w3.org/2000/svg}script'),[])
        self.assertIn(b'&lt;script&gt;',raw);self.assertIn(b'stroke-dasharray',raw)
    def test_assets_are_owner_scoped_and_tampering_blocks_final_approval(self):
        value=self.generate();asset=value['payload']['diagrams'][0]['asset']
        with self.assertRaises(KeyError):notes.diagram_asset(self.root,self.jid,'bob',asset['filename'])
        (notes.folder(self.root,self.jid)/'assets'/asset['filename']).write_bytes(b'tamper')
        with self.assertRaises(ValueError):self.approve()
    def test_invalid_svg_upload_and_stale_revision_are_refused(self):
        value=self.generate()
        with self.assertRaises(Exception):notes.replace_diagram(self.root,self.jid,'alice',0,value['job']['current'],b'<svg onload="bad"/>')
        with self.assertRaises(review.Conflict):notes.replace_diagram(self.root,self.jid,'alice',0,0,image())
    def test_text_only_source_does_not_generate_invented_diagrams(self):
        source=page();source['blocks'][0]['reviewed']=True
        recap={'schema':'smartinis-notes-recap/1','page_sha256':fingerprint(source),
            'items':[{'kind':'summary','text':'Text recap','evidence':[{'block_id':'B000001','quote':source['blocks'][0]['text']}]}]}
        self.assertEqual(presentation.build(notes.folder(self.root,self.jid),{'page':source},recap)['diagrams'],[])


class TwoStageHTTP(unittest.TestCase):
    setUp=http_fixture.NotesHTTP.setUp
    tearDown=http_fixture.NotesHTTP.tearDown
    call=http_fixture.NotesHTTP.call
    session=http_fixture.NotesHTTP.session
    upload=http_fixture.NotesHTTP.upload
    def test_http_source_approval_final_preview_asset_replacement_and_final_approval(self):
        from urllib.error import HTTPError
        with patch.dict(os.environ,{'NOTES_TWO_STAGE':'1'}):
            jid=self.upload();source=page();source['blocks'][0]['kind']='drawing'
            notes.process_next(self.root,lambda *args:source)
            path='api/note/'+jid
            def action(obj):
                with self.call(path,body=json.dumps(obj).encode()) as response:return json.load(response)
            value=action({'action':'approve-source','revision':1,'acknowledge_source_review':True})
            self.assertEqual(value['job']['state'],'final-queued')
            def final(job,stage,payload,work):
                block=payload['page']['blocks'][0]
                recap={'schema':'smartinis-notes-recap/1','page_sha256':fingerprint(payload['page']),
                    'items':[{'kind':'summary','text':'Review this final text.','evidence':[{'block_id':block['id'],'quote':block['text']}]}]}
                return presentation.build(notes.folder(self.root,jid),payload,recap)
            notes.process_next(self.root,final);value=notes.view(self.root,jid,'alice')
            name=value['payload']['diagrams'][0]['asset']['filename']
            with self.call(path+'/asset/'+name) as response:
                self.assertEqual(response.headers['Content-Type'],'image/svg+xml');self.assertIn('sandbox',response.headers['Content-Security-Policy']);self.assertIn(b'<svg',response.read())
            with self.assertRaises(HTTPError) as error:self.call(path+'/asset/'+name,'bob')
            self.assertEqual(error.exception.code,404)
            with self.call(path+'/diagram/0',body=image(),extra={'Content-Type':'image/png','X-Notes-Revision':str(value['job']['current'])}) as response:value=json.load(response)
            value=action({'action':'save-final','revision':value['job']['current'],'final_text':'Edited final recap.',
                'diagram_descriptions':['Approved image description.']})
            value=action({'action':'approve','revision':value['job']['current'],'acknowledge_source_review':True,'acknowledge_final_review':True})
            self.assertEqual(value['job']['current'],value['job']['approved'])


if __name__=='__main__':unittest.main()
