import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.request import Request
from urllib.error import HTTPError
import knowledge_lifecycle as life
import test_ingestion as baseline
import ingest_meetings as ingest
import test_notes_http as fixture
import text_store
from test_text_backend import VALUE

class RemovalSync(unittest.TestCase):
    setUp=baseline.SyncTests.setUp
    run_sync=baseline.SyncTests.run_sync
    modify=baseline.SyncTests.modify
    def private(self):
        original=self.client.request
        def request(method,path,obj=None):
            result=original(method,path,obj)
            if path=='/api/v1/knowledge/kb':result.update(user_id='synthetic-test-owner',access_grants=[])
            return result
        self.client.request=request
    def remove(self):
        return life.change(self.root,self.folder.name,'synthetic-test-owner','remove',0)
    def test_detach_keeps_source_global_file_and_approval_and_blocks_future_runs(self):
        self.private();self.run_sync();self.remove();before=(self.folder/'review.json').read_bytes()
        result=self.run_sync();self.assertEqual(result['removed'],1);self.assertEqual(self.client.members,set())
        self.assertIn('file1',self.client.storage);self.assertEqual((self.folder/'review.json').read_bytes(),before)
        self.modify();self.run_sync();self.assertEqual(self.client.uploads,1)
        self.assertEqual(life.all_states(self.root)[self.folder.name]['status'],'removed')
        self.assertNotIn('committed',self.state.data['meetings'][self.folder.name])
    def test_explicit_restore_allows_approved_revision_again(self):
        self.private();self.run_sync();self.remove();self.run_sync()
        life.change(self.root,self.folder.name,'synthetic-test-owner','restore',1)
        self.assertFalse(self.run_sync()['errors']);self.assertEqual(len(self.client.members),1)
    def test_remove_before_initial_index_never_uploads(self):
        self.private();self.remove();self.run_sync();self.assertEqual(self.client.writes,[])
        self.assertEqual(life.all_states(self.root)[self.folder.name]['status'],'removed')
    def test_dry_run_never_detaches_or_changes_ledger_or_request(self):
        self.private();self.run_sync();self.remove();before=copy.deepcopy(self.state.data);writes=list(self.client.writes)
        result=self.run_sync(False);self.assertEqual(result['removal_planned'],1)
        self.assertEqual(self.state.data,before);self.assertEqual(self.client.writes,writes)
        self.assertEqual(life.all_states(self.root)[self.folder.name]['status'],'pending')
    def test_failed_removal_stays_pending_no_reingestion(self):
        self.private();self.run_sync();self.remove();self.client.fail_remove=True
        self.assertTrue(self.run_sync()['errors']);self.assertEqual(self.client.members,{'file1'})
        self.assertEqual(life.all_states(self.root)[self.folder.name]['status'],'pending')
        self.client.fail_remove=False;self.assertFalse(self.run_sync()['errors'])
    def test_lost_detach_response_reconciles_membership(self):
        self.private();self.run_sync();self.remove()
        def lost(kb,fid):self.client.members.discard(fid);raise ingest.IngestionError('Lost response')
        self.client.remove=lost;self.assertFalse(self.run_sync()['errors'])
    def test_wrong_destination_owner_refused(self):
        self.run_sync();self.remove();self.assertTrue(self.run_sync()['errors']);self.assertEqual(self.client.members,{'file1'})
    def test_shared_identity_refused(self):
        self.private();self.run_sync();self.remove();self.state.data['meetings']['another']=copy.deepcopy(self.state.data['meetings'][self.folder.name])
        self.assertTrue(self.run_sync()['errors']);self.assertEqual(self.client.members,{'file1'})
    def test_pending_and_historical_memberships_are_removed(self):
        self.private();self.run_sync();self.modify();self.client.fail_remove=True;self.run_sync()
        self.client.fail_remove=False;self.remove();self.assertFalse(self.run_sync()['errors']);self.assertFalse(self.client.members)
        self.assertEqual(self.client.uploads,2)
    def test_new_removal_during_upload_is_reconciled_before_run_finishes(self):
        self.private();original=self.client.add
        def add(kb,fid):original(kb,fid);self.remove()
        self.client.add=add;self.assertFalse(self.run_sync()['errors']);self.assertFalse(self.client.members)
    def test_stale_and_cross_owner_actions_refused_and_restore_waits(self):
        self.remove()
        for owner,action,generation in [('other','remove',1),('synthetic-test-owner','restore',1),('synthetic-test-owner','remove',0)]:
            with self.assertRaises(ValueError):life.change(self.root,self.folder.name,owner,action,generation)
    def test_rollback_cannot_restore_withdrawn_material(self):
        self.private();self.run_sync();self.remove()
        with self.assertRaises(ingest.IngestionError):ingest.rollback(self.client,self.config,self.state,self.folder.name,apply=True)
    def test_audit_and_idempotent_repeated_request(self):
        self.remove();life.change(self.root,self.folder.name,'synthetic-test-owner','remove',1)
        with life.connect(self.root) as db:self.assertEqual(db.execute('SELECT count(*) FROM knowledge_events').fetchone()[0],1)

class RemovalHTTP(unittest.TestCase):
    setUp=fixture.NotesHTTP.setUp
    tearDown=fixture.NotesHTTP.tearDown
    def seed(self):
        os.environ['SMARTINIS_TEXT_ENABLED']='1';text_store.init(self.root)
        self.jid=text_store.submit(self.root,'alice','removal',VALUE)
        text_store.act(self.root,self.jid,'alice',{'action':'approve','revision':1,'acknowledge_review':True})
    def request(self,owner='alice',body=None,csrf=True,kind='text',jid=None):
        headers={'Cookie':'token='+owner,'X-Meeting-Origin':self.base}
        if body is not None:
            if csrf:
                with self.client.open(Request(self.base+'/meeting-ui/dashboard/api/session',headers=headers)) as r:token=json.load(r)['csrf']
                headers['X-Meeting-CSRF']=token
            headers.update(Origin=self.base,**{'Content-Type':'application/json'})
        return self.client.open(Request(self.base+'/meeting-ui/dashboard/api/knowledge/'+kind+'/'+(jid or self.jid),headers=headers,data=json.dumps(body).encode() if body is not None else None))
    def body(self,**extra):return dict(action='remove',revision=1,generation=0,acknowledge=True,**extra)
    def test_owner_only_and_csrf_required(self):
        with patch.dict(os.environ):
            self.seed()
            for owner,csrf,code in [('bob',True,404),('alice',False,403)]:
                with self.assertRaises(HTTPError) as e:self.request(owner,self.body(),csrf)
                self.assertEqual(e.exception.code,code)
            self.assertEqual(life.all_states(self.root),{})
    def test_remove_decorates_list_and_stale_revision_refused(self):
        with patch.dict(os.environ):
            self.seed();body=self.body();body['revision']=2
            with self.assertRaises(HTTPError) as e:self.request(body=body)
            self.assertEqual(e.exception.code,409)
            with self.request(body=self.body()) as r:self.assertEqual(json.load(r)['knowledge_status'],'pending')
            with self.client.open(Request(self.base+'/meeting-ui/dashboard/api/meetings?kind=text',headers={'Cookie':'token=alice'})) as r:
                row=json.load(r)['meetings'][0];self.assertEqual(row['status'],'Removal queued');self.assertNotIn('knowledge_owner',row)
            self.assertEqual(text_store.view(self.root,self.jid,'alice')['job']['approved'],1)
    def test_approval_race_is_checked_inside_lifecycle_transaction(self):
        with patch.dict(os.environ):
            self.seed();original=life.change
            def race(*args,**kwargs):
                with text_store.connection(self.root) as db:db.execute('UPDATE text_docs SET approved=2 WHERE id=?',(self.jid,))
                return original(*args,**kwargs)
            with patch.object(life,'change',side_effect=race):
                with self.assertRaises(HTTPError) as error:self.request(body=self.body())
            self.assertEqual(error.exception.code,409);self.assertEqual(life.all_states(self.root),{})
    def test_audio_and_notes_have_owner_scoped_removal(self):
        import notes_store
        from test_notes_backend import image
        note=notes_store.submit(self.root,'alice','remove-note','Fixture','English',image())
        audio='c'*32;folder=self.root/('processed-test_'+audio);folder.mkdir()
        (folder/'meeting_metadata.json').write_text('{}')
        with self.worker.connect() as db:db.execute('INSERT INTO jobs(id,owner,request_key,created,updated,state,folder) VALUES (?,?,?,?,?,?,?)',(audio,'alice','audio',1,1,'completed',str(folder)))
        for kind,jid,key in [('notes',note,'notes-'+note[5:]),('audio',audio,folder.name)]:
            body=self.body();body['revision']=None
            with self.assertRaises(HTTPError) as error:self.request('bob',body,kind=kind,jid=jid)
            self.assertEqual(error.exception.code,404)
            with self.request(body=body,kind=kind,jid=jid) as response:self.assertEqual(response.status,200)
            self.assertEqual(life.all_states(self.root)[key]['owner'],'alice')
    def test_unapproved_text_can_be_excluded_but_cannot_be_restored_until_approved(self):
        with patch.dict(os.environ):
            os.environ['SMARTINIS_TEXT_ENABLED']='1';text_store.init(self.root)
            self.jid=text_store.submit(self.root,'alice','unapproved',VALUE)
            body=self.body();body['revision']=None
            with self.request(body=body) as r:self.assertEqual(r.status,200)
            life.finish(self.root,self.jid,'alice',1)
            body.update(action='restore',generation=1)
            with self.assertRaises(HTTPError) as e:self.request(body=body)
            self.assertEqual(e.exception.code,409)

if __name__=='__main__':unittest.main()
