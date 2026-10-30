import copy
from contextlib import contextmanager
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
import meeting_review as review
import notes_store as notes
import notes_ingestion
import notes_dispatch
from notes_document import fingerprint
from heavy_gate import slot


def image():
    buf=io.BytesIO()
    Image.new('RGB',(200,250),'white').save(buf,format='PNG')
    return buf.getvalue()


def page(flagged=True):
    return {'schema':'smartinis-notes-page/1','image_sha256':'0'*64,'edge_clipping':False,
        'blocks':[{'id':'B000001','kind':'paragraph','bbox':[0,0,1,1],
            'text':'Aster proposed Friday. Not approved.','uncertainties':['Check name'] if flagged else [],
            'reviewed':True,'excluded':False}],'relations':[]}


def recap(payload):
    return {'schema':'smartinis-notes-recap/1','page_sha256':fingerprint(payload['page']),
        'items':[{'kind':'open-question','text':'Proposal remains unapproved.',
            'evidence':[{'block_id':'B000001','quote':'Not approved.' if 'Not approved.' in payload['page']['blocks'][0]['text'] else payload['page']['blocks'][0]['text']}]}]}


class NotesBackend(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        notes.init(self.root)
        self.raw=image()
        self.jid=notes.submit(self.root,'alice','request-1','Page','English',self.raw)

    def tearDown(self):
        self.tmp.cleanup()

    def run_extract(self,flagged=True):
        notes.process_next(self.root,lambda *args:page(flagged))
        return notes.view(self.root,self.jid,'alice')

    def draft(self):
        value=self.run_extract()
        notes.act(self.root,self.jid,'alice',{'action':'generate-recap','revision':value['job']['current']})
        notes.process_next(self.root,lambda job,stage,payload,work:recap(payload))
        return notes.view(self.root,self.jid,'alice')

    def approve(self,value):
        return notes.act(self.root,self.jid,'alice',{'action':'approve',
            'revision':value['job']['current'],'acknowledge_source_review':True})

    def test_original_hash_derivative_and_idempotency(self):
        directory=notes.folder(self.root,self.jid)
        self.assertEqual((directory/'original.png').read_bytes(),self.raw)
        self.assertTrue((directory/'inference.png').exists())
        self.assertEqual(notes.submit(self.root,'alice','request-1','Page','English',self.raw),self.jid)
        other=io.BytesIO();Image.new('RGB',(200,250),'black').save(other,format='PNG')
        with self.assertRaises(review.Conflict):notes.submit(self.root,'alice','request-1','Page','English',other.getvalue())

    def test_invalid_image_and_path(self):
        with self.assertRaises(Exception):notes.submit(self.root,'alice','bad','Page','English',b'not an image')
        with self.assertRaises(ValueError):notes.folder(self.root,'../outside')

    def test_owner_isolation(self):
        with self.assertRaises(KeyError):notes.view(self.root,self.jid,'bob')
        with self.assertRaises(KeyError):notes.act(self.root,self.jid,'bob',{'action':'retry','revision':0})
        self.assertEqual(notes.listing(self.root,'bob'),[])

    def test_extract_does_not_trust_model_review_flags(self):
        value=self.run_extract()
        self.assertFalse(value['payload']['page']['blocks'][0]['reviewed'])
        self.assertIsNone(value['job']['approved'])
        self.assertIsNone(notes.oldest(self.root))

    def test_clear_page_queues_only_an_unapproved_draft(self):
        clear=page(False);clear['blocks'][0]['text']='the discussion remains open.'
        notes.process_next(self.root,lambda *args:clear)
        value=notes.view(self.root,self.jid,'alice')
        self.assertFalse(value['payload']['page']['blocks'][0]['reviewed'])
        self.assertIsNotNone(notes.oldest(self.root))
        notes.process_next(self.root,lambda job,stage,payload,work:recap(payload))
        self.assertIsNone(notes.view(self.root,self.jid,'alice')['job']['approved'])

    def test_approval_is_separate_and_bound_to_revision(self):
        value=self.draft()
        with self.assertRaises(review.Conflict):notes.act(self.root,self.jid,'alice',{'action':'approve','revision':value['job']['current']})
        approved=self.approve(value)
        self.assertEqual(approved['job']['approved'],value['job']['current'])
        self.assertIsNotNone(notes_ingestion.document(notes.folder(self.root,self.jid),self.root,'alice'))
        self.assertIsNone(notes_ingestion.document(notes.folder(self.root,self.jid),self.root,'bob'))

    def test_source_edit_retains_old_approval_and_refuses_stale_action(self):
        value=self.draft();self.approve(value)
        old=notes_ingestion.document(notes.folder(self.root,self.jid),self.root,'alice')
        changed=copy.deepcopy(value['payload']['page']);changed['blocks'][0]['text']='Astra proposed Monday. Not approved.'
        updated=notes.act(self.root,self.jid,'alice',{'action':'save-page','revision':value['job']['current'],'page':changed})
        self.assertIsNone(updated['payload']['recap'])
        self.assertEqual(notes_ingestion.document(notes.folder(self.root,self.jid),self.root,'alice')['sha256'],old['sha256'])
        with self.assertRaises(review.Conflict):self.approve(value)

    def test_reapprove_replaces_stable_identity(self):
        value=self.draft();self.approve(value)
        old=notes_ingestion.document(notes.folder(self.root,self.jid),self.root,'alice')
        changed=copy.deepcopy(value['payload']['recap']);changed['items'][0]['text']='Friday was only proposed.'
        newer=notes.act(self.root,self.jid,'alice',{'action':'save-recap','revision':value['job']['current'],'recap':changed})
        self.approve(newer)
        new=notes_ingestion.document(notes.folder(self.root,self.jid),self.root,'alice')
        self.assertEqual(new['identity'],old['identity']);self.assertNotEqual(new['sha256'],old['sha256'])
        self.assertEqual(notes_ingestion.document(notes.folder(self.root,self.jid),self.root,'alice',old['approval_revision'])['sha256'],old['sha256'])

    def test_tamper_rejected(self):
        value=self.draft();self.approve(value)
        doc=notes_ingestion.document(notes.folder(self.root,self.jid),self.root,'alice')
        Path(doc['source']).write_text('changed')
        with self.assertRaises(ValueError):notes_ingestion.document(notes.folder(self.root,self.jid),self.root,'alice')
        with self.assertRaises(review.Conflict):self.approve(value)

    def test_bad_evidence_is_refused(self):
        value=self.draft();changed=copy.deepcopy(value['payload']['recap']);changed['items'][0]['evidence'][0]['quote']='decision accepted'
        with self.assertRaises(ValueError):notes.act(self.root,self.jid,'alice',{'action':'save-recap','revision':value['job']['current'],'recap':changed})

    def test_recovery_adopts_completed_cache_without_model_rerun(self):
        with review.connection(self.root) as db:
            task=dict(db.execute('SELECT * FROM notes_tasks').fetchone())
            db.execute("UPDATE notes_tasks SET status='running'")
            db.execute("UPDATE notes_jobs SET state='extract-running'")
        directory=notes.folder(self.root,self.jid)/'work'/task['key'];directory.mkdir(parents=True)
        (directory/'result.json').write_text(json.dumps(page()))
        notes.recover(self.root)
        called=[]
        notes.process_next(self.root,lambda *args:called.append(True))
        self.assertFalse(called);self.assertEqual(notes.view(self.root,self.jid,'alice')['job']['current'],1)

    def test_edit_during_generation_does_not_overwrite(self):
        value=self.run_extract();notes.act(self.root,self.jid,'alice',{'action':'generate-recap','revision':1})
        def generation(job,stage,payload,work):
            changed=copy.deepcopy(payload['page']);changed['blocks'][0]['text']='Newer wording. Not approved.'
            notes.act(self.root,self.jid,'alice',{'action':'save-page','revision':1,'page':changed})
            return recap(payload)
        notes.process_next(self.root,generation)
        latest=notes.view(self.root,self.jid,'alice')
        self.assertEqual(latest['payload']['page']['blocks'][0]['text'],'Newer wording. Not approved.')
        self.assertEqual(latest['job']['state'],'page-review')

    def test_interrupted_stage_requeues(self):
        def interrupted(*args):raise InterruptedError()
        notes.process_next(self.root,interrupted)
        self.assertIsNotNone(notes.oldest(self.root));self.assertEqual(notes.view(self.root,self.jid,'alice')['job']['state'],'extract-queued')

    def test_manual_transcription_after_failed_extraction(self):
        def fail(*args):raise ValueError('synthetic extraction failure')
        notes.process_next(self.root,fail)
        value=notes.view(self.root,self.jid,'alice');manual=page()
        manual['image_sha256']=value['job']['image_sha256']
        saved=notes.act(self.root,self.jid,'alice',{'action':'save-page','revision':0,'page':manual})
        self.assertEqual(saved['job']['current'],1);self.assertIsNone(saved['job']['approved'])

    def test_failure_manual_recap_and_retry(self):
        value=self.run_extract();notes.act(self.root,self.jid,'alice',{'action':'generate-recap','revision':1})
        def fail(*args):raise ValueError('synthetic timeout')
        notes.process_next(self.root,fail)
        failed=notes.view(self.root,self.jid,'alice');self.assertEqual(failed['job']['state'],'failed')
        manual=notes.act(self.root,self.jid,'alice',{'action':'save-recap','revision':1,'recap':recap(failed['payload'])})
        self.assertEqual(self.approve(manual)['job']['state'],'approved')

    def test_corrections_require_explicit_confirmation_and_are_owner_scoped(self):
        value=self.run_extract();changed=copy.deepcopy(value['payload']['page']);changed['blocks'][0]['text']='Astra proposed Friday. Not approved.'
        changed['blocks'][0]['uncertainties']=[]
        saved=notes.act(self.root,self.jid,'alice',{'action':'save-page','revision':1,'page':changed})
        self.assertEqual(notes.corrections(self.root,'alice'),[])
        notes.act(self.root,self.jid,'alice',{'action':'confirm-page','revision':saved['job']['current'],'remember_corrections':True})
        memory=notes.corrections(self.root,'alice');self.assertEqual(len(memory),1);self.assertEqual(notes.corrections(self.root,'bob'),[])
        current=notes.view(self.root,self.jid,'alice')
        notes.act(self.root,self.jid,'alice',{'action':'forget-correction','revision':current['job']['current'],'key':memory[0]['key']})
        self.assertEqual(notes.corrections(self.root,'alice'),[])

    def test_queue_fairness_and_gate(self):
        self.assertEqual(notes_dispatch.choose(30,10,20),'meeting-recap')
        self.assertEqual(notes_dispatch.choose(30,40,20),'notes')
        with slot(self.root) as first:
            self.assertTrue(first)
            with slot(self.root) as second:self.assertFalse(second)
        with slot(self.root) as after:self.assertTrue(after)

    def test_dispatch_does_not_claim_when_memory_low(self):
        @contextmanager
        def connection():
            db=sqlite3.connect(self.root/'jobs.sqlite3');db.row_factory=sqlite3.Row
            try:
                with db:yield db
            finally:db.close()
        with connection() as db:db.execute('CREATE TABLE jobs(id TEXT,created REAL,state TEXT)')
        worker=SimpleNamespace(ROOT=self.root,connect=connection)
        with patch('notes_models.available_mb',return_value=100):
            self.assertFalse(notes_dispatch.step(worker))
        self.assertEqual(notes.view(self.root,self.jid,'alice')['job']['state'],'extract-queued')


if __name__=='__main__':unittest.main()
