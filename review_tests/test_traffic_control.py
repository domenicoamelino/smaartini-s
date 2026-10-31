import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.request import Request
from urllib.error import HTTPError
import test_notes_http as fixture
from test_notes_backend import image
import notes_store
import meeting_review as review
import traffic_control as traffic

class Traffic(unittest.TestCase):
    setUp=fixture.NotesHTTP.setUp
    tearDown=fixture.NotesHTTP.tearDown
    def audio(self,state='queued',owner='alice'):
        jid=('a' if owner=='alice' else 'b')*32;folder=self.root/('processed-fixture_'+jid);folder.mkdir()
        (folder/'source.wav').write_bytes(b'original')
        with self.worker.connect() as db:db.execute('INSERT INTO jobs(id,owner,request_key,created,updated,state,filename,folder) VALUES (?,?,?,?,?,?,?,?)',(jid,owner,'fixture',1,1,state,'Fixture audio',str(folder)))
        return jid,folder
    def note(self):
        jid=notes_store.submit(self.root,'alice','note','Fixture notes','English',image())
        with review.connection(self.root) as db:key=db.execute('SELECT key FROM notes_tasks WHERE id=?',(jid,)).fetchone()[0]
        return jid,key
    def recap(self):
        jid='c'*32;folder=self.root/'recap';folder.mkdir();(folder/'review.json').write_text(json.dumps({'pending':'recap-one','last_approved':{'revision':1}}))
        with review.connection(self.root) as db:
            db.execute('INSERT INTO meetings VALUES (?,?,?,?,?,?)',(jid,'alice',str(folder),1,'recap-one',None))
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',('recap-one',jid,1,'fixture','{}','queued',2))
        return jid,folder
    def call(self,body=None,owner='alice',csrf=True):
        headers={'Cookie':'token='+owner,'X-Meeting-Origin':self.base}
        if body is not None:
            if csrf:
                with self.client.open(Request(self.base+'/meeting-ui/dashboard/api/session',headers=headers)) as r:headers['X-Meeting-CSRF']=json.load(r)['csrf']
            headers.update({'Content-Type':'application/json','Origin':self.base})
        return self.client.open(Request(self.base+'/meeting-ui/dashboard/api/traffic',data=json.dumps(body).encode() if body is not None else None,headers=headers))
    def test_audio_cancel_atomic_persistent_and_preserves_source(self):
        jid,folder=self.audio();traffic.cancel(self.worker,'alice','audio',jid);traffic.cancel(self.worker,'alice','audio',jid)
        self.worker.recover();self.assertEqual(self.worker.get_job(jid)['state'],'cancelled');self.assertEqual((folder/'source.wav').read_bytes(),b'original')
        with self.worker.connect() as db:
            self.assertIsNone(db.execute("SELECT id FROM jobs WHERE state='queued'").fetchone())
            self.assertEqual(db.execute('SELECT count(*) FROM traffic_events').fetchone()[0],1)
    def test_running_audio_cannot_be_cancelled(self):
        jid,_=self.audio('transcribing')
        with self.assertRaises(ValueError):traffic.cancel(self.worker,'alice','audio',jid)
        self.assertEqual(self.worker.get_job(jid)['state'],'transcribing')
    def test_worker_claim_wins_race(self):
        jid,_=self.audio()
        with self.worker.connect() as db:db.execute("UPDATE jobs SET state='transcribing' WHERE id=?",(jid,))
        with self.assertRaises(ValueError):traffic.cancel(self.worker,'alice','audio',jid)
    def test_owner_cannot_cancel_other_audio(self):
        jid,_=self.audio(owner='bob')
        with self.assertRaises(KeyError):traffic.cancel(self.worker,'alice','audio',jid)
        self.assertEqual(self.worker.get_job(jid)['state'],'queued')
    def test_notes_cancel_retains_image_and_does_not_run(self):
        jid,key=self.note();original=notes_store.original(self.root,jid,'alice')
        traffic.cancel(self.worker,'alice','notes',key)
        self.assertFalse(notes_store.process_next(self.root,lambda *args:self.fail('Cancelled stage started')))
        notes_store.recover(self.root)
        with review.connection(self.root) as db:
            self.assertEqual(db.execute('SELECT status FROM notes_tasks WHERE key=?',(key,)).fetchone()[0],'cancelled')
            self.assertEqual(db.execute('SELECT state FROM notes_jobs WHERE id=?',(jid,)).fetchone()[0],'cancelled')
        self.assertEqual(notes_store.original(self.root,jid,'alice'),original)
    def test_other_owner_notes_and_recap_refused(self):
        jid,key=self.note();self.recap()
        for kind,key in [('notes',key),('meeting-recap','recap-one')]:
            with self.assertRaises(KeyError):traffic.cancel(self.worker,'bob',kind,key)
    def test_running_notes_refused(self):
        jid,key=self.note()
        with review.connection(self.root) as db:db.execute("UPDATE notes_tasks SET status='running' WHERE key=?",(key,))
        with self.assertRaises(ValueError):traffic.cancel(self.worker,'alice','notes',key)
    def test_recap_cancel_clears_pending_retains_approval(self):
        jid,folder=self.recap();traffic.cancel(self.worker,'alice','meeting-recap','recap-one')
        self.assertFalse(review.process_next(self.root,lambda *args:self.fail('Cancelled recap started')))
        state=json.loads((folder/'review.json').read_text());self.assertIsNone(state['pending']);self.assertEqual(state['last_approved']['revision'],1)
    def test_running_recap_refused(self):
        self.recap()
        with review.connection(self.root) as db:db.execute("UPDATE tasks SET status='running'")
        with self.assertRaises(ValueError):traffic.cancel(self.worker,'alice','meeting-recap','recap-one')
    def test_owner_only_rows_and_position(self):
        jid,_=self.audio(owner='bob');self.note();data=traffic.snapshot(self.worker,'alice')
        self.assertEqual(len(data['jobs']),1);self.assertNotIn(jid,json.dumps(data));self.assertEqual(data['jobs'][0]['position'],2)
    def test_no_fake_heartbeat_for_recap(self):
        self.recap();self.assertIsNone(traffic.snapshot(self.worker,'alice')['jobs'][0]['activity'])
    def test_memory_wait_explanation(self):
        self.audio()
        with patch.object(traffic,'memory',return_value={'available_mb':100,'total_mb':30000}),patch.object(traffic,'slot_busy',return_value=False):
            self.assertIn('memory',traffic.snapshot(self.worker,'alice')['jobs'][0]['reason'])
    def test_http_auth_csrf_and_acknowledgement(self):
        jid,_=self.audio();body={'action':'cancel-waiting','kind':'audio','key':jid,'acknowledge':True}
        for owner,csrf,code in [('bob',True,404),('alice',False,403)]:
            with self.assertRaises(HTTPError) as error:self.call(body,owner,csrf)
            self.assertEqual(error.exception.code,code)
        with self.call(body) as response:self.assertEqual(response.status,200)
    def test_http_running_conflict_and_no_action(self):
        jid,_=self.audio('transcribing')
        with self.assertRaises(HTTPError) as error:self.call({'action':'cancel-waiting','kind':'audio','key':jid,'acknowledge':True})
        self.assertEqual(error.exception.code,409)
    def test_view_has_restrictive_policy(self):
        with self.client.open(self.base+'/meeting-ui/dashboard/?view=traffic') as response:
            self.assertIn('Traffic Control',response.read().decode());self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])

if __name__=='__main__':unittest.main()
