import json
import os
import unittest
from unittest.mock import patch
from urllib.request import Request
from urllib.error import HTTPError
import test_notes_http as fixture
from test_notes_backend import image
import notes_store as notes


class SharedDashboard(unittest.TestCase):
    setUp=fixture.NotesHTTP.setUp
    tearDown=fixture.NotesHTTP.tearDown
    call=fixture.NotesHTTP.call
    def request(self,path,owner='alice'):
        with self.client.open(Request(self.base+path,headers={'Cookie':'token='+owner}),timeout=5) as response:
            return json.load(response)
    def seed(self):
        self.one=notes.submit(self.root,'alice','notes-one','Architecture notes','English',image(),notes_date='2026-10-30')
        self.two=notes.submit(self.root,'alice','notes-two','Planning notes','English',image(),notes_date='2026-10-29')
        notes.submit(self.root,'bob','other','Private other owner','English',image())
        with self.worker.connect() as db:
            db.execute('INSERT INTO jobs(id,owner,request_key,created,updated,state,filename) VALUES (?,?,?,?,?,?,?)',
                ('a'*32,'alice','audio',1,1,'waiting_upload','Audio meeting'))
    def test_combined_list_pagination_source_filter_and_owner_isolation(self):
        self.seed();data=self.request('/meeting-ui/dashboard/api/meetings?limit=2')
        self.assertEqual(data['total'],3);self.assertEqual(data['counts']['total'],3)
        self.assertEqual(data['counts']['processing'],2);self.assertEqual(len(data['meetings']),2)
        self.assertTrue(all(row['kind']=='notes' for row in data['meetings']))
        nextpage=self.request('/meeting-ui/dashboard/api/meetings?limit=2&offset=2')
        self.assertEqual(nextpage['meetings'][0]['kind'],'audio')
        only_audio=self.request('/meeting-ui/dashboard/api/meetings?kind=audio')
        self.assertEqual(only_audio['total'],1)
        only_notes=self.request('/meeting-ui/dashboard/api/meetings?kind=notes&q=Architecture')
        self.assertEqual(only_notes['total'],1);self.assertEqual(only_notes['meetings'][0]['id'],self.one)
        self.assertNotIn('Private other owner',json.dumps(data)+json.dumps(nextpage))
    def test_disabled_feature_retains_audio_only(self):
        self.seed()
        with patch.dict(os.environ,{'SMARTINIS_NOTES_ENABLED':'0'}):
            data=self.request('/meeting-ui/dashboard/api/meetings')
        self.assertEqual(data['total'],1);self.assertEqual(data['meetings'][0]['kind'],'audio')
    def test_notes_allowlist_does_not_hide_existing_audio(self):
        self.seed()
        with patch.dict(os.environ,{'NOTES_ALLOWED_OWNERS':'bob'}):
            data=self.request('/meeting-ui/dashboard/api/meetings')
        self.assertEqual(data['total'],1)
    def test_notes_detail_uses_same_dashboard_route_and_security_policy(self):
        with self.client.open(self.base+'/meeting-ui/dashboard/?view=notes',timeout=5) as response:
            markup=response.read().decode()
            self.assertIn('picture-select',markup);self.assertIn('All recaps',markup)
            self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
        with self.client.open(self.base+'/meeting-ui/dashboard/',timeout=5) as response:
            markup=response.read().decode();self.assertIn('kind-filter',markup);self.assertIn('All sources',markup)
    def test_configured_public_origin_works_behind_rewritten_host(self):
        public='https://trusted.example'
        with patch.dict(os.environ,{'NOTES_PUBLIC_ORIGIN':public}):
            with self.call('api/session',extra={'X-Notes-Origin':public}) as response:
                session=json.load(response)
            self.assertTrue(session['csrf']);self.assertEqual(session['user']['id'],'alice')
            # Existing signed origin-bound CSRF protection remains active on writes.
            jid=notes.submit(self.root,'alice','one','A','English',image())
            headers={'Cookie':'token=alice','Content-Type':'application/json','Origin':public,'X-Meeting-CSRF':session['csrf']}
            body=json.dumps({'action':'retry','revision':99}).encode()
            with self.assertRaises(HTTPError) as error:
                self.client.open(Request(self.base+'/meeting-ui/notes/api/note/'+jid,data=body,headers=headers),timeout=5)
            self.assertEqual(error.exception.code,409)
            headers['Origin']='https://untrusted.example'
            with self.assertRaises(HTTPError) as error:
                self.client.open(Request(self.base+'/meeting-ui/notes/api/note/'+jid,data=body,headers=headers),timeout=5)
            self.assertEqual(error.exception.code,403)
    def test_forwarded_header_alone_cannot_authorize_an_origin(self):
        with patch.dict(os.environ,{'NOTES_PUBLIC_ORIGIN':'https://trusted.example'}):
            with self.assertRaises(HTTPError) as error:
                self.call('api/session',extra={'X-Notes-Origin':'https://evil.example','X-Forwarded-Host':'evil.example'})
            self.assertEqual(error.exception.code,403)


if __name__=='__main__':unittest.main()
