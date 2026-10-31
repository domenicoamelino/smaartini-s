import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import text_store as store
import text_web
import text_ingestion
import ingest_meetings as ingestion
from test_notes_integration import Client

VALUE={'title':'Personal recap','date':'2026-10-30','markdown':'# Heading\r\n\r\n**Literal** text, café.\tKeep spaces.  \r\n- one\r\n'}

class TextBackend(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);store.init(self.root)
        self.jid=store.submit(self.root,'alice','one',copy.deepcopy(VALUE))
    def tearDown(self):self.tmp.cleanup()
    def value(self):return store.view(self.root,self.jid,'alice')
    def act(self,action,**extra):return store.act(self.root,self.jid,'alice',{'action':action,'revision':self.value()['job']['current'],**extra})
    def approve(self):return self.act('approve',acknowledge_review=True)
    def test_exact_text_original_and_idempotent_submit(self):
        self.assertEqual(self.value()['payload'],VALUE)
        self.assertEqual((store.folder(self.root,self.jid)/'original.json').read_bytes(),store.encoded(VALUE))
        self.assertEqual(store.submit(self.root,'alice','one',VALUE),self.jid)
        with self.assertRaises(store.Conflict):store.submit(self.root,'alice','one',{**VALUE,'markdown':'different'})
    def test_invalid_date_empty_oversized_or_wrong_type_refused(self):
        for key,value in [('date','2026-02-30'),('markdown',''),('markdown','x'*(store.MAX_CHARS+1)),('markdown',True),('title','x\nY')]:
            with self.assertRaises((ValueError,TypeError)):store.submit(self.root,'alice','bad',dict(VALUE,**{key:value}))
    def test_owner_isolation_and_path_refusal(self):
        with self.assertRaises(KeyError):store.view(self.root,self.jid,'bob')
        with self.assertRaises(KeyError):store.act(self.root,self.jid,'bob',{'action':'approve','revision':1,'acknowledge_review':True})
        self.assertEqual(store.summaries(self.root,'bob'),[])
        with self.assertRaises(ValueError):store.folder(self.root,'../outside')
    def test_separate_approval_required_and_draft_is_not_ingestible(self):
        self.assertIsNone(store.approved_document(store.folder(self.root,self.jid),self.root,'alice'))
        with self.assertRaises(store.Conflict):self.act('approve')
        self.approve();doc=store.approved_document(store.folder(self.root,self.jid),self.root,'alice')
        self.assertIn(b'**Literal**',doc['raw']);self.assertNotIn(b'\r',doc['raw'])
        self.assertEqual(self.value()['payload']['markdown'],VALUE['markdown'])
    def test_save_preserves_approval_and_stale_write_is_refused(self):
        self.approve();old=store.approved_document(store.folder(self.root,self.jid),self.root,'alice')
        self.act('save',payload={**VALUE,'markdown':'Edited draft'})
        self.assertEqual(self.value()['job']['approved'],1);self.assertEqual(old['sha256'],store.approved_document(store.folder(self.root,self.jid),self.root,'alice')['sha256'])
        with self.assertRaises(store.Conflict):store.act(self.root,self.jid,'alice',{'action':'save','revision':1,'payload':VALUE})
        self.approve();self.assertEqual(self.value()['job']['approved'],2)
    def test_edit_back_to_old_content_has_new_revision_identity(self):
        self.approve();old=store.approved_document(store.folder(self.root,self.jid),self.root,'alice')
        self.act('save',payload={**VALUE,'markdown':'Other'});self.act('save',payload=VALUE);self.approve()
        self.assertNotEqual(old['sha256'],store.approved_document(store.folder(self.root,self.jid),self.root,'alice')['sha256'])
    def test_immutable_snapshot_or_original_tamper_refused(self):
        self.approve();directory=store.folder(self.root,self.jid)
        path=directory/'approved/r000001/knowledge.md';raw=path.read_bytes();path.write_bytes(b'changed')
        with self.assertRaises(store.Conflict):store.approved_document(directory,self.root,'alice')
        path.write_bytes(raw);(directory/'original.json').write_text('{}')
        with self.assertRaises(store.Conflict):store.approved_document(directory,self.root,'alice')
    def test_orphan_files_never_imply_approval(self):
        self.approve()
        with store.connection(self.root) as db:db.execute('DELETE FROM text_approvals')
        with self.assertRaises(store.Conflict):store.approved_document(store.folder(self.root,self.jid),self.root,'alice')
    def test_concurrent_submission_creates_only_one_draft(self):
        ids=[];errors=[]
        def run():
            try:ids.append(store.submit(self.root,'alice','concurrent',VALUE))
            except Exception as e:errors.append(e)
        threads=[threading.Thread(target=run) for _ in range(3)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(errors,[]);self.assertEqual(len(set(ids)),1)
    def test_submit_save_approve_never_calls_models(self):
        with patch('notes_models.generate',side_effect=AssertionError('No AI')),patch('notes_dispatch.step',side_effect=AssertionError('No heavy queue')):
            self.act('save',payload={**VALUE,'markdown':'No AI'});self.approve()

class TextIngestion(unittest.TestCase):
    tearDown=TextBackend.tearDown
    value=TextBackend.value
    act=TextBackend.act
    approve=TextBackend.approve
    def setUp(self):
        TextBackend.setUp(self);self.client=Client();self.config={'base_url':'http://127.0.0.1:8080','collection_id':'kb','meetings_root':str(self.root),
            'include_text':True,'text_owner_id':'alice'};self.state=ingestion.State(self.root/'ledger.json',self.config)
    def sync(self,apply=True):return ingestion.sync(self.client,self.config,self.state,apply=apply,busy=lambda root:False)
    def notices(self):
        with store.connection(self.root) as db:return [dict(r) for r in db.execute('SELECT * FROM notices')]
    def test_approved_only_and_after_commit_notification_once(self):
        self.assertEqual(self.sync()['uploaded'],0);self.assertEqual(self.notices(),[])
        self.approve();self.assertEqual(self.sync(False)['uploaded'],0);self.assertEqual(self.notices(),[])
        self.assertEqual(self.sync()['newly_ingested'],1);self.assertEqual(len(self.notices()),1)
        self.assertEqual(self.state.data['meetings'][self.jid]['committed']['approval_revision'],1)
        self.assertEqual(self.sync()['unchanged'],1);self.assertEqual(len(self.notices()),1)
    def test_replace_reapprove_retains_single_collection_entry(self):
        self.approve();self.sync();self.act('save',payload={**VALUE,'markdown':'New user text'})
        self.assertEqual(self.sync()['unchanged'],1);self.assertEqual(len(self.notices()),1)
        self.approve();self.assertEqual(self.sync()['updated'],1);self.assertEqual(len(self.client.members),1);self.assertEqual(len(self.notices()),2)
    def test_failed_replacement_has_no_new_success_notice(self):
        self.approve();self.sync();self.act('save',payload={**VALUE,'markdown':'New version'});self.approve()
        self.client.fail_remove=True;result=self.sync();self.assertTrue(result['errors']);self.assertEqual(len(self.notices()),1)
        self.client.fail_remove=False;self.assertFalse(self.sync()['errors']);self.assertEqual(len(self.notices()),2)
    def test_notification_reconciles_after_committed_state_on_next_run(self):
        self.approve()
        with patch('text_ingestion.notify',side_effect=ValueError('Outbox temporarily unavailable')):self.assertTrue(self.sync()['errors'])
        self.assertTrue(self.state.data['meetings'][self.jid].get('committed'));self.assertEqual(self.notices(),[])
        self.assertEqual(self.sync()['unchanged'],1);self.assertEqual(len(self.notices()),1);self.assertEqual(self.client.uploads,1)
    def test_private_owner_and_grants_required(self):
        for field,value in [('owner','bob'),('grants',[{'permission':'read'}]),('write_access',False)]:
            previous=getattr(self.client,field);setattr(self.client,field,value)
            with self.assertRaises(ingestion.IngestionError):self.sync()
            setattr(self.client,field,previous)
    def test_missing_owner_is_refused(self):
        self.config.pop('text_owner_id')
        with self.assertRaises(ingestion.IngestionError):self.sync()
    def test_notes_upload_staging_is_not_an_ingestion_document(self):
        (self.root/'notes-upload-fixture').mkdir();self.config.update(include_notes=True,notes_owner_id='alice')
        self.approve();result=self.sync();self.assertFalse(result['errors']);self.assertEqual(result['newly_ingested'],1)
    def test_monitor_style_loading_resolves_helpers_without_pythonpath(self):
        runtime=self.root/'runtime';runtime.mkdir();data=self.root/'loader-data';data.mkdir()
        source=Path(__file__).resolve().parents[1]
        shutil.copy2(source/'ingestion/ingest_meetings.py',runtime/'ingest_meetings.py')
        for name in ['knowledge_lifecycle.py','text_store.py','text_ingestion.py','heavy_gate.py']:shutil.copy2(source/name,runtime/name)
        code='''import importlib.util,json,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('monitor_style_ingestion',sys.argv[1]);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
import text_store
root=Path(sys.argv[2]);text_store.init(root)
jid=text_store.submit(root,'alice','one',{'title':'Fixture','date':'2026-10-30','markdown':'No model.'})
text_store.act(root,jid,'alice',{'action':'approve','revision':1,'acknowledge_review':True})
class Client:
    def version(self):return 'fixture'
    def request(self,*args):return {'id':'kb','user_id':'alice','write_access':True,'access_grants':[]}
    def files(self,*args):return []
config={'base_url':'http://127.0.0.1','collection_id':'kb','meetings_root':str(root),'include_text':True,'text_owner_id':'alice'}
result=module.sync(Client(),config,module.State(root/'ledger.json',config),apply=False,busy=lambda root:False)
assert result['planned']==1 and not result['errors'] and not (root/'ledger.json').exists()
print('MONITOR_LOADER_OK')
'''
        child=subprocess.run([sys.executable,'-I','-c',code,str(runtime/'ingest_meetings.py'),str(data)],cwd=self.root,capture_output=True,text=True)
        self.assertEqual(child.returncode,0,child.stdout+child.stderr);self.assertIn('MONITOR_LOADER_OK',child.stdout)

if __name__=='__main__':unittest.main()
