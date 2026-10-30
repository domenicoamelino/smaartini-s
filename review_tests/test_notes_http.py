import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request,build_opener,ProxyHandler
from http.server import ThreadingHTTPServer

import meeting_dashboard as dashboard
import notes_store as notes
from test_notes_backend import image


class NotesHTTP(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'SMARTINIS_NOTES_ENABLED':'1','MEETING_ROOT':str(self.root),'MEETING_API_KEY':'x'*40});self.env.start()
        name='notes_http_worker_fixture'
        spec=importlib.util.spec_from_file_location(name,Path(__file__).resolve().parents[1]/'meeting_worker.py')
        self.worker=importlib.util.module_from_spec(spec);sys.modules[name]=self.worker;spec.loader.exec_module(self.worker);self.worker.init()
        def identity(headers):
            cookie=headers.get('Cookie','')
            if cookie not in ('token=alice','token=bob'):raise dashboard.AccessError(401,'Sign in')
            owner=cookie.split('=')[1];return {'id':owner,'name':'Fixture owner'},owner
        self.identity=patch('meeting_dashboard.identity',side_effect=identity);self.identity.start()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),self.worker.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
        self.client=build_opener(ProxyHandler({}));self.csrf={}
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.identity.stop();self.env.stop();self.tmp.cleanup()
    def call(self,path,owner='alice',body=None,csrf=True,extra=None):
        headers={'Cookie':'token='+owner,'X-Notes-Origin':self.base}
        if body is not None:
            headers.update({'Origin':self.base,'Content-Type':'application/json'})
            if csrf:headers['X-Meeting-CSRF']=self.csrf.get(owner,'')
        headers.update(extra or {})
        return self.client.open(Request(self.base+'/meeting-ui/notes/'+path,data=body,headers=headers),timeout=5)
    def session(self,owner='alice'):
        with self.call('api/session',owner) as r:self.csrf[owner]=json.load(r)['csrf']
    def upload(self):
        self.session()
        with self.call('api/upload',body=image(),extra={'X-Notes-Title':'Page','X-Notes-Language':'English','X-Request-Key':'one','X-Owner-Id':'bob'}) as r:
            return json.load(r)['job']['id']
    def test_upload_get_and_owner_spoofing(self):
        jid=self.upload()
        self.assertEqual(len(notes.listing(self.root,'alice')),1);self.assertEqual(notes.listing(self.root,'bob'),[])
        self.session('bob')
        for suffix in ['', '/original']:
            with self.assertRaises(HTTPError) as error:self.call('api/note/'+jid+suffix,'bob')
            self.assertEqual(error.exception.code,404)
        with self.call('api/note/'+jid+'/original') as response:
            self.assertEqual(response.read(),image());self.assertEqual(response.headers['Cross-Origin-Resource-Policy'],'same-origin')
    def test_csrf_missing_and_wrong_owner_rejected(self):
        self.session()
        with self.assertRaises(HTTPError) as error:self.call('api/upload',body=image(),csrf=False)
        self.assertEqual(error.exception.code,403)
        self.session('bob');self.csrf['alice']=self.csrf['bob']
        with self.assertRaises(HTTPError) as error:self.call('api/upload',body=image())
        self.assertEqual(error.exception.code,403)
        self.assertEqual(notes.listing(self.root,'alice'),[])
    def test_host_origin_and_cross_origin_options(self):
        with self.assertRaises(HTTPError) as error:self.call('api/session',extra={'X-Notes-Origin':'https://other.invalid'})
        self.assertEqual(error.exception.code,403)
        with self.assertRaises(HTTPError) as error:
            self.client.open(Request(self.base+'/meeting-ui/notes/api/upload',method='OPTIONS'),timeout=5)
        self.assertEqual(error.exception.code,405)
    def test_assets_have_restrictive_policy_and_no_worker_secret(self):
        with self.call('') as r:
            self.assertIn("script-src 'self'",r.headers['Content-Security-Policy']);self.assertNotIn('Access-Control-Allow-Origin',r.headers)
            self.assertNotIn('x'*40,r.read().decode())
    def test_failed_auth_and_stale_revision(self):
        with self.assertRaises(HTTPError) as error:self.call('api/notes','unknown')
        self.assertEqual(error.exception.code,401)
        jid=self.upload()
        with self.assertRaises(HTTPError) as error:self.call('api/note/'+jid,body=json.dumps({'action':'retry','revision':99}).encode())
        self.assertEqual(error.exception.code,409)
    def test_owner_only_pilot(self):
        with patch.dict(os.environ,{'NOTES_ALLOWED_OWNERS':'alice'}):
            self.session('alice')
            with self.assertRaises(HTTPError) as error:self.call('api/notes','bob')
            self.assertEqual(error.exception.code,403)


if __name__=='__main__':unittest.main()
