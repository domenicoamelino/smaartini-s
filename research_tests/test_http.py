import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import research_jobs as jobs
import research_routes


class HTTP(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);jobs.init(self.root)
        worker=SimpleNamespace(ROOT=self.root)
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def auth(self): return self.headers.get('Authorization')=='Bearer fixture-key'
            def length(self,limit):
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=limit: raise ValueError()
                return n
            def send(self,status,value):
                raw=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def do_GET(self): research_routes.route(self,worker,'GET')
            def do_POST(self): research_routes.route(self,worker,'POST')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.env=patch.dict('os.environ',{'RESEARCH_ALLOWED_OWNERS':'alice,bob'});self.env.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.env.stop();self.tmp.cleanup()
    def request(self,suffix='',owner='alice',body=None,key='fixture-key'):
        request=Request('http://127.0.0.1:'+str(self.server.server_port)+research_routes.PREFIX+suffix,
            data=json.dumps(body).encode() if body else None,
            headers={'Authorization':'Bearer '+key,'X-Owner-Id':owner})
        with urlopen(request,timeout=2) as r:return json.load(r)
    def test_status_remains_responsive_during_inference(self):
        job=self.request(body={'question':'public API practices','mode':'web','request_key':'one'})
        entered=threading.Event();release=threading.Event()
        def blocked(*args): entered.set();release.wait(3);raise TimeoutError()
        processing=threading.Thread(target=jobs.tick,args=(self.root,blocked,None,SimpleNamespace()),daemon=True)
        processing.start()
        try:
            self.assertTrue(entered.wait(2));start=time.monotonic()
            status=self.request('/'+job['id'])
            self.assertLess(time.monotonic()-start,1)
            self.assertEqual(status['status'],'running');self.assertIn('Planning',status['stage'])
            with self.assertRaises(HTTPError) as error:self.request('/'+job['id'],owner='bob')
            self.assertEqual(error.exception.code,404)
            with self.assertRaises(HTTPError) as error:self.request('/'+job['id'],key='wrong')
            self.assertEqual(error.exception.code,401)
        finally:release.set();processing.join(4)
        self.assertEqual(self.request('/'+job['id'])['status'],'failed')
    def test_query_approval_endpoint_requires_owner_and_exact_preview(self):
        job=self.request(body={'question':'public research','mode':'web','request_key':'review'})
        queries=['Power BI Excel import tutorial'];jid=job['id']
        digest=hashlib.sha256(json.dumps(['alice',jid,queries],ensure_ascii=False).encode()).hexdigest()
        payload={'review':{'queries':queries,'digest':digest,'expires':time.time()+60},
                 'checkpoint':{'queries':queries,'routing':{'knowledge':False,'web':True},'brief':'Power BI Excel'},'user_approved':False}
        jobs.update(self.root,jid,'Waiting for review','needs_review',payload)
        with self.assertRaises(HTTPError) as error:self.request('/'+jid+'/review',owner='bob',body={'decision':'approve','proof':digest[:12]})
        self.assertEqual(error.exception.code,404)
        with self.assertRaises(HTTPError) as error:self.request('/'+jid+'/review',body={'decision':'approve','proof':'0'*12})
        self.assertEqual(error.exception.code,400)
        self.assertEqual(self.request('/'+jid+'/review',body={'decision':'approve','proof':digest[:12]})['status'],'queued')


if __name__=='__main__': unittest.main()
