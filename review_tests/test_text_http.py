import json
import os
from urllib.request import Request
from urllib.error import HTTPError
import unittest
from unittest.mock import patch
import test_notes_http as fixture
from test_text_backend import VALUE
import text_store as store
import text_web

class TextHTTP(unittest.TestCase):
    def setUp(self):
        self.text_env=patch.dict(os.environ,{'SMARTINIS_TEXT_ENABLED':'1'});self.text_env.start();fixture.NotesHTTP.setUp(self)
    def tearDown(self):fixture.NotesHTTP.tearDown(self);self.text_env.stop()
    def req(self,path,obj=None,headers=None):
        supplied={'Cookie':'token=alice','X-Meeting-Origin':self.base}
        if obj is not None:supplied.update({'Content-Type':'application/json','Origin':self.base})
        supplied.update(headers or {})
        with self.client.open(Request(self.base+path,data=None if obj is None else json.dumps(obj).encode(),headers=supplied),timeout=5) as response:
            raw=response.read();return response.headers,(json.loads(raw) if response.headers.get_content_type()=='application/json' else raw.decode())
    def create(self,key='one'):
        return self.req('/v1/text/sessions',{'request_key':key},{'Authorization':'Bearer '+'x'*40,'X-Owner-Id':'alice'})[1]
    def save_card(self,session):return self.req('/meeting-ui/write/submit/'+session['upload_token'],{'confirmed':True,'payload':VALUE})[1]
    def test_card_submit_no_approval_and_dashboard_visible_with_exact_text(self):
        s=self.create();_,markup=self.req('/meeting-ui/write/view/'+s['upload_token']);self.assertIn('Save draft &amp; open review',markup);self.assertNotIn('x'*40,markup)
        status=self.save_card(s);jid=status['doc_id'];self.assertIn('?view=text#',status['dashboard_path'])
        self.assertEqual(self.save_card(s)['doc_id'],jid)
        _,data=self.req('/meeting-ui/text/api/doc/'+jid);self.assertEqual(data['payload'],VALUE);self.assertIsNone(data['job']['approved'])
        _,listing=self.req('/meeting-ui/dashboard/api/meetings?kind=text');self.assertEqual(listing['total'],1);self.assertEqual(listing['meetings'][0]['id'],jid)
        _,html=self.req('/meeting-ui/dashboard/?view=text');self.assertIn('Review your text',html)
    def test_session_reconnect_and_other_owner_or_missing_worker_auth_refused(self):
        s=self.create();self.assertEqual(self.create()['id'],s['id'])
        for headers in [{},{'Authorization':'Bearer '+'x'*40,'X-Owner-Id':'bob'}]:
            with self.assertRaises(HTTPError) as error:self.req('/v1/text/sessions/'+s['id'],headers=headers)
            self.assertIn(error.exception.code,(401,404))
    def test_capability_cannot_read_or_approve_and_owner_spoofing_ignored(self):
        s=self.create();jid=self.save_card(s)['doc_id']
        for path in ['/meeting-ui/write/approve/'+s['upload_token'],'/meeting-ui/write/doc/'+s['upload_token']]:
            with self.assertRaises(HTTPError):self.req(path,{'action':'approve','revision':1})
        with self.assertRaises(HTTPError) as error:self.req('/meeting-ui/text/api/doc/'+jid,headers={'Cookie':'token=bob','X-Owner-Id':'alice'})
        self.assertEqual(error.exception.code,404)
    def test_csrf_required_for_save_and_final_approval_and_origin_is_bound(self):
        jid=self.save_card(self.create())['doc_id'];path='/meeting-ui/text/api/doc/'+jid
        with self.assertRaises(HTTPError) as error:self.req(path,{'action':'approve','revision':1,'acknowledge_review':True})
        self.assertEqual(error.exception.code,403)
        _,s=self.req('/meeting-ui/text/api/session');csrf=s['csrf']
        with self.assertRaises(HTTPError) as error:self.req(path,{'action':'approve','revision':1},headers={'X-Meeting-CSRF':csrf})
        self.assertEqual(error.exception.code,409)
        _,approved=self.req(path,{'action':'approve','revision':1,'acknowledge_review':True},headers={'X-Meeting-CSRF':csrf})
        self.assertEqual(approved['job']['approved'],1)
        with self.assertRaises(HTTPError) as error:self.req(path,{'action':'save','revision':1,'payload':VALUE},headers={'X-Meeting-CSRF':csrf,'Origin':'https://evil.example'})
        self.assertEqual(error.exception.code,403)
    def test_public_origin_pilot_and_opaque_card_options(self):
        with patch.dict(os.environ,{'TEXT_PUBLIC_ORIGIN':'https://trusted.example','TEXT_ALLOWED_OWNERS':'alice'}):
            _,s=self.req('/meeting-ui/text/api/session',headers={'X-Meeting-Origin':'https://trusted.example'});self.assertTrue(s['csrf'])
            for headers in [{'Cookie':'token=bob'},{'X-Meeting-Origin':'https://evil.example','X-Forwarded-Host':'evil.example'}]:
                with self.assertRaises(HTTPError) as error:self.req('/meeting-ui/text/api/session',headers=headers)
                self.assertEqual(error.exception.code,403)
        s=self.create()
        with self.client.open(Request(self.base+'/meeting-ui/write/submit/'+s['upload_token'],method='OPTIONS'),timeout=5) as response:
            self.assertEqual(response.headers['Access-Control-Allow-Origin'],'*')
        with self.assertRaises(HTTPError) as error:self.client.open(Request(self.base+'/meeting-ui/text/api/session',method='OPTIONS'),timeout=5)
        self.assertEqual(error.exception.code,405)
    def test_review_identity_and_asset_security_and_no_ai_queue(self):
        jid=self.save_card(self.create())['doc_id']
        with self.assertRaises(HTTPError) as error:self.req('/meeting-ui/text/api/doc/'+jid,headers={'Cookie':'token=unknown'})
        self.assertEqual(error.exception.code,401)
        headers,script=self.req('/meeting-ui/text/text_markdown.js');self.assertIn("script-src 'self'",headers['Content-Security-Policy'])
        self.assertIn("case 'html':target.append(document.createTextNode",script)
        self.assertIn("case 'image':target.append(document.createTextNode",script)
        with self.worker.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
        with store.connection(self.root) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM notes_tasks').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM notices').fetchone()[0],0)
    def test_historical_text_is_read_only_and_owner_scoped(self):
        jid=self.save_card(self.create())['doc_id']
        store.act(self.root,jid,'alice',{'action':'save','revision':1,'payload':{**VALUE,'markdown':'New draft'}})
        _,old=self.req('/meeting-ui/text/api/doc/'+jid+'/revision/1')
        self.assertEqual(old['payload'],VALUE);self.assertTrue(old['read_only'])
        with self.assertRaises(HTTPError) as error:self.req('/meeting-ui/text/api/doc/'+jid+'/revision/1',headers={'Cookie':'token=bob'})
        self.assertEqual(error.exception.code,404)

if __name__=='__main__':unittest.main()
