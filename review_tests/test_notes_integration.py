import copy
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import ingest_meetings as ingestion
from test_ingestion import FakeClient
from test_notes_backend import image,page,recap
import meeting_review as review
import notes_store as notes
import notes_dispatch
import notes_models
from heavy_gate import slot


class Client(FakeClient):
    def __init__(self):
        super().__init__();self.owner='alice';self.account='alice';self.grants=[];self.write_access=True
    def request(self,method,path,obj=None):
        if path=='/api/v1/knowledge/kb':
            return {'id':'kb','name':'Private Notes','write_access':self.write_access,'user_id':self.owner,'access_grants':self.grants}
        if path=='/api/v1/auths/':return {'id':self.account}
        return super().request(method,path,obj)


class Integration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);notes.init(self.root)
        self.jid=notes.submit(self.root,'alice','request','Synthetic','English',image())
        self.config={'base_url':'http://127.0.0.1:8080','collection_id':'kb','meetings_root':str(self.root),
            'include_notes':True,'notes_owner_id':'alice','notes_only':True}
        self.client=Client();self.state=ingestion.State(self.root/'ledger.json',self.config)
    def tearDown(self):self.tmp.cleanup()
    def draft(self):
        notes.process_next(self.root,lambda *args:page())
        notes.act(self.root,self.jid,'alice',{'action':'generate-recap','revision':1})
        notes.process_next(self.root,lambda job,stage,payload,work:recap(payload))
        return notes.view(self.root,self.jid,'alice')
    def approve(self,value):
        return notes.act(self.root,self.jid,'alice',{'action':'approve','revision':value['job']['current'],'acknowledge_source_review':True})
    def sync(self):return ingestion.sync(self.client,self.config,self.state,apply=True,busy=lambda root:False)

    def test_approved_only_replacement_and_repeat_noop(self):
        value=self.draft();result=self.sync();self.assertEqual(result['uploaded'],0)
        self.approve(value);first=self.sync();self.assertEqual(first['newly_ingested'],1);self.assertEqual(len(self.client.members),1)
        repeat=self.sync();self.assertEqual(repeat['unchanged'],1)
        changed=copy.deepcopy(value['payload']['recap']);changed['items'][0]['text']='No approval was recorded.'
        updated=notes.act(self.root,self.jid,'alice',{'action':'save-recap','revision':2,'recap':changed})
        self.assertEqual(self.sync()['unchanged'],1)
        self.approve(updated);self.assertEqual(self.sync()['updated'],1);self.assertEqual(len(self.client.members),1)

    def test_collection_owner_sharing_and_write_access_are_enforced(self):
        for field,value in [('owner','bob'),('write_access',False),('grants',[{'principal_id':'*','permission':'read'}])]:
            with self.subTest(field=field):
                old=getattr(self.client,field);setattr(self.client,field,value)
                with self.assertRaises(ingestion.IngestionError):self.sync()
                self.assertEqual(self.client.uploads,0);setattr(self.client,field,old)

    def test_existing_restricted_key_needs_no_profile_permission(self):
        original=self.client.request
        def scoped(method,path,obj=None):
            if path=='/api/v1/auths/':raise ingestion.APIError(403,path)
            return original(method,path,obj)
        self.client.request=scoped
        self.approve(self.draft());self.assertEqual(self.sync()['uploaded'],1)

    def test_ingestion_cannot_race_heavy_processing(self):
        self.approve(self.draft())
        with slot(self.root) as acquired:
            self.assertTrue(acquired);self.assertTrue(self.sync()['deferred']);self.assertEqual(self.client.uploads,0)
        self.assertEqual(self.sync()['uploaded'],1)

    def test_gate_is_cross_process(self):
        code='from heavy_gate import slot; import sys\nwith slot(sys.argv[1]) as ok: print(int(ok))'
        with slot(self.root):
            child=subprocess.run([sys.executable,'-c',code,str(self.root)],capture_output=True,text=True,check=True)
            self.assertEqual(child.stdout.strip(),'0')

    def test_disabled_notes_queue_does_not_block_meeting_rollback(self):
        with patch.dict(os.environ,{'SMARTINIS_NOTES_ENABLED':'0'}):
            self.assertFalse(ingestion.worker_busy(self.root))
        with patch.dict(os.environ,{'SMARTINIS_NOTES_ENABLED':'1'}):
            self.assertTrue(ingestion.worker_busy(self.root))

    def test_failed_remove_resumes_the_pinned_approved_snapshot(self):
        value=self.draft();self.approve(value);self.sync()
        changed=copy.deepcopy(value['payload']['recap']);changed['items'][0]['text']='Still awaiting approval in the source.'
        newer=notes.act(self.root,self.jid,'alice',{'action':'save-recap','revision':2,'recap':changed});self.approve(newer)
        self.client.fail_remove=True;self.assertTrue(self.sync()['errors'])
        changed['items'][0]['text']='Later unapproved edit.'
        notes.act(self.root,self.jid,'alice',{'action':'save-recap','revision':3,'recap':changed})
        self.client.fail_remove=False;self.assertFalse(self.sync()['errors']);self.assertEqual(len(self.client.members),1)

    def test_parallel_dispatch_never_runs_two_heavy_stages(self):
        notes.submit(self.root,'bob','other','Other','English',image())
        @contextmanager
        def connect():
            db=sqlite3.connect(self.root/'jobs.sqlite3');db.row_factory=sqlite3.Row
            try:
                with db:yield db
            finally:db.close()
        with connect() as db:db.execute('CREATE TABLE jobs(id TEXT,created REAL,state TEXT)')
        worker=SimpleNamespace(ROOT=self.root,connect=connect,STOP=threading.Event())
        active=[0];maximum=[0];guard=threading.Lock();entered=threading.Event()
        def generate(*args):
            with guard:active[0]+=1;maximum[0]=max(maximum[0],active[0])
            entered.set();time.sleep(.05)
            with guard:active[0]-=1
            return page()
        with patch('notes_models.available_mb',return_value=20000),patch('notes_models.generate',side_effect=generate):
            first=threading.Thread(target=lambda:notes_dispatch.step(worker));first.start();self.assertTrue(entered.wait(2))
            self.assertFalse(notes_dispatch.step(worker));first.join();self.assertTrue(notes_dispatch.step(worker))
        self.assertEqual(maximum[0],1)

    def test_truncated_model_output_is_rejected_and_partial_retained(self):
        with review.connection(self.root) as db:job=dict(db.execute('SELECT * FROM notes_jobs WHERE id=?',(self.jid,)).fetchone())
        model={'name':'qwen3.5:4b','capabilities':['vision'],'digest':'synthetic'}
        class Opener:
            def open(self,request,timeout):
                if isinstance(request,str):return io.BytesIO(json.dumps({'models':[model]}).encode())
                return io.BytesIO(b'{"message":{"content":"{broken"}}\n{"done":true,"done_reason":"length"}\n')
        work=self.root/'model-work';work.mkdir()
        with patch('notes_models.build_opener',return_value=Opener()):
            with self.assertRaisesRegex(ValueError,'did not finish'):
                notes_models.generate(self.root,job,'extract',None,work)
        self.assertEqual((work/'partial.txt').read_text(),'{broken')
        self.assertEqual(json.loads((work/'metrics.json').read_text())['done_reason'],'length')

    def test_remote_model_is_never_used(self):
        with review.connection(self.root) as db:job=dict(db.execute('SELECT * FROM notes_jobs').fetchone())
        class Opener:
            def open(self,request,timeout):
                return io.BytesIO(json.dumps({'models':[{'name':'qwen3.5:4b','remote_host':'https://example.invalid'}]}).encode())
        with patch('notes_models.build_opener',return_value=Opener()):
            with self.assertRaisesRegex(ValueError,'cloud fallback'):
                notes_models.generate(self.root,job,'extract',None,self.root)

    def test_audio_and_notes_use_the_same_slot(self):
        @contextmanager
        def connect():
            db=sqlite3.connect(self.root/'jobs.sqlite3');db.row_factory=sqlite3.Row
            try:
                with db:yield db
            finally:db.close()
        with connect() as db:
            db.execute('CREATE TABLE jobs(id TEXT,created REAL,state TEXT)')
            db.execute("INSERT INTO jobs VALUES ('audio',1,'queued')")
        entered=threading.Event();release=threading.Event();order=[]
        def audio(job):
            order.append('audio');entered.set();release.wait(2)
            with connect() as db:db.execute("UPDATE jobs SET state='completed' WHERE id='audio'")
        worker=SimpleNamespace(ROOT=self.root,connect=connect,STOP=threading.Event(),process=audio)
        def generate(*args):order.append('notes');return page()
        with patch('notes_models.available_mb',return_value=20000),patch('notes_models.generate',side_effect=generate):
            first=threading.Thread(target=lambda:notes_dispatch.step(worker));first.start();self.assertTrue(entered.wait(2))
            self.assertFalse(notes_dispatch.step(worker));self.assertEqual(order,['audio'])
            release.set();first.join();self.assertTrue(notes_dispatch.step(worker))
        self.assertEqual(order,['audio','notes'])


if __name__=='__main__':unittest.main()
