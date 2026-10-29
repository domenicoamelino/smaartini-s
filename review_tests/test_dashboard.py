"""Owner authentication, CSRF, atomic edits and approval/indexing state; no live WebUI/bot."""
import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import test_workflow as fixture
import test_review
import meeting_dashboard as dashboard
import configure_meeting_notifications as configure_notifications


class AuthHandler(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *_):
        pass

    def do_GET(self):
        self.requests.append(dict(self.headers))
        cookie = self.headers.get('Cookie')
        owner = {'token=alice-session': 'alice', 'token=bob-session': 'bob', 'token=pending-session': 'pending'}.get(cookie)
        if owner is None:
            self.send_response(401)
            self.end_headers()
            return
        value = {'id': owner, 'name': owner.title(), 'role': 'pending' if owner == 'pending' else 'user',
                 'token': 'THIS-MUST-NOT-REACH-THE-BROWSER'}
        raw = json.dumps(value).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class DashboardTests(unittest.TestCase):
    action = test_review.ReviewTests.action
    # Do not repeat inherited tests here; this class adds HTTP checks using their setup.
    def setUp(self):
        test_review.ReviewTests.setUp(self)
        self.auth = ThreadingHTTPServer(('127.0.0.1', 0), AuthHandler)
        self.auth.daemon_threads = True
        threading.Thread(target=self.auth.serve_forever, daemon=True).start()
        self.addCleanup(self.auth.server_close)
        self.addCleanup(self.auth.shutdown)
        self.stack.enter_context(patch.dict(os.environ, {'MEETING_WEBUI_URL': f'http://127.0.0.1:{self.auth.server_port}',
                                                       'MEETING_INGESTION_HOME': str(self.root/'ingestion')}))
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), fixture.worker.Handler)
        self.server.daemon_threads = True
        self.server.worker_thread = threading.current_thread()
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.host = f'127.0.0.1:{self.server.server_port}'
        self.base = '/meeting-ui/dashboard/'

    def request(self, route, body=None, cookie='alice-session', csrf=None, origin=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=15)
        supplied = {'Cookie': 'token=' + cookie} if cookie else {}
        supplied['X-Meeting-Origin'] = 'http://' + self.host
        supplied.update(headers or {})
        if body is not None:
            supplied.update({'Content-Type': 'application/json', 'Origin': origin or 'http://' + self.host})
            if csrf:
                supplied['X-Meeting-CSRF'] = csrf
        try:
            connection.request('POST' if body is not None else 'GET', self.base + route,
                               json.dumps(body) if body is not None else None, supplied)
            response = connection.getresponse()
            raw = response.read().decode()
            value = json.loads(raw) if 'application/json' in response.getheader('Content-Type', '') else raw
            return response.status, value, dict(response.getheaders())
        finally:
            connection.close()

    def session(self, owner='alice-session'):
        status, value, _ = self.request('api/session', cookie=owner)
        self.assertEqual(status, 200)
        return value['csrf']

    def test_dashboard_auth_and_owner_isolation(self):
        self.assertEqual(self.request('api/meetings', cookie=None)[0], 401)
        self.assertEqual(self.request('api/session', cookie='pending-session')[0], 403)
        _, session, _ = self.request('api/session')
        self.assertNotIn('THIS-MUST-NOT-REACH-THE-BROWSER', json.dumps(session))
        self.assertEqual(self.request('api/meetings/' + self.job['id'], cookie='bob-session')[0], 404)
        _, bob, _ = self.request('api/meetings', cookie='bob-session', headers={'X-Owner-Id': 'alice', 'Authorization': 'Bearer ' + fixture.worker.API_KEY})
        self.assertEqual(bob['total'], 0)
        _, alice, _ = self.request('api/meetings')
        self.assertEqual(alice['total'], 1)
        self.assertEqual(alice['meetings'][0]['id'], self.job['id'])

    def test_expired_unused_card_is_not_an_expired_meeting(self):
        session=fixture.worker.create_session('alice','unused-card')
        with fixture.worker.connect() as connection:
            connection.execute('UPDATE jobs SET created=? WHERE id=?',(time.time()-1801,session['id']))
        _,value,_=self.request('api/meetings')
        card=next(row for row in value['meetings'] if row['id']==session['id'])
        self.assertEqual(card['status'],'Unused upload request — expired')
        self.assertEqual(card['state'],'waiting_upload')
        self.assertIsNone(card['revision'])
        self.assertIsNotNone(fixture.worker.get_job(session['id']))

    def test_public_origin_survives_proxy_host_rewriting(self):
        headers={'Host':'internal-worker.local:8765','X-Meeting-Origin':'https://meetings.example'}
        status, session, _ = self.request('api/session',headers=headers)
        self.assertEqual(status,200)
        csrf=session['csrf']
        route='api/meetings/'+self.job['id']
        action={'action':'approve','revision':1}
        self.assertEqual(self.request(route,action,csrf=csrf,origin='https://meetings.example',headers=headers)[0],200)
        self.assertEqual(self.request(route,action,csrf=csrf,origin='https://evil.example',headers=headers)[0],403)
        self.assertEqual(self.request(route,action,origin='https://meetings.example',headers=headers)[0],403)

    def test_no_dashboard_cors_and_static_assets_have_csp(self):
        for name in ('', 'dashboard.js', 'dashboard.css', 'api/session'):
            status, _, headers = self.request(name)
            self.assertEqual(status, 200)
            self.assertNotIn('Access-Control-Allow-Origin', headers)
            self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
            self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(self.request('../view/' + self.job['token'] if 'token' in self.job else 'api/nope')[0], 404)

    def test_csrf_is_bound_to_owner_cookie_and_origin(self):
        csrf = self.session()
        action = {'action': 'approve', 'revision': 1}
        route = 'api/meetings/' + self.job['id']
        self.assertEqual(self.request(route, action)[0], 403)
        self.assertEqual(self.request(route, action, csrf=csrf, origin='https://evil.example')[0], 403)
        self.assertEqual(self.request(route, action, csrf=self.session('bob-session'))[0], 403)
        with patch.object(dashboard.time, 'time', return_value=time.time() + 7200):
            self.assertEqual(self.request(route, action, csrf=csrf)[0], 403)
        self.assertEqual(self.request(route, action, csrf=csrf)[0], 200)

    def test_save_close_preserves_approval_and_stale_edits_fail(self):
        csrf = self.session()
        route = 'api/meetings/' + self.job['id']
        self.assertEqual(self.request(route, {'action': 'approve', 'revision': 1}, csrf=csrf)[0], 200)
        body = {'action': 'dashboard-save', 'revision': 1, 'content': '# Reviewed\n\nNo role document exists.',
                'metadata': {'meeting_title': 'Reviewed meeting', 'meeting_date': '2026-10-01', 'participants': ['Alice']},
                'mapping': {'SPEAKER_00': 'Alice', 'SPEAKER_01': 'Bob'}}
        status, value, _ = self.request(route, body, csrf=csrf)
        self.assertEqual(status, 200)
        self.assertEqual(value['meeting']['revision'], 2)
        self.assertEqual(value['meeting']['approved_revision'], 1)
        self.assertEqual(value['meeting']['status'], 'Transcript awaiting review')
        self.assertEqual(value['review']['speaker_mapping']['SPEAKER_00'], 'Alice')
        self.assertEqual(value['review']['metadata']['meeting_title'], 'Reviewed meeting')
        self.assertEqual(len(value['history']), 2)
        self.assertEqual(self.request(route, body, csrf=csrf)[0], 409)
        self.assertEqual(self.request(route, {'action':'approve','revision':1}, csrf=csrf)[0], 409)
        self.assertEqual(self.request(route, {'action':'approve','revision':2}, csrf=csrf)[0], 409)
        self.assertEqual(self.request(route+'/revisions/1')[1]['report'], '# Draft\n\nThere is no role document.\n')
        self.assertEqual(self.request(route+'/revisions/3')[0], 404)
        self.assertEqual(self.request(route+'/revisions/1', cookie='bob-session')[0], 404)

    def test_invalid_atomic_save_does_not_create_revision(self):
        csrf = self.session()
        body = {'action':'dashboard-save','revision':1,'content':'Changed text','metadata':{
            'meeting_title':'Changed title','meeting_date':'2026-02-30','participants':[]},'mapping':{}}
        self.assertEqual(self.request('api/meetings/'+self.job['id'], body, csrf=csrf)[0], 400)
        value = fixture.review.view(self.root, self.job['id'], 'alice')
        self.assertEqual(value['revision'], 1)
        self.assertEqual(value['metadata']['meeting_title'], fixture.BASE['meeting_title'])

    def test_indexing_never_inferred_from_approval(self):
        self.action('approve')
        _, value, _ = self.request('api/meetings/'+self.job['id'])
        self.assertIsNone(value['meeting']['indexed_revision'])
        directory = self.folder/'review/r000001'
        approval = json.loads((directory/'approval.json').read_text())
        home = self.root/'ingestion'
        home.mkdir()
        committed = {'approval_revision':1,'approval_sha256':approval['knowledge_sha256'],
                     'file_id':'remote-file', 'indexed_at':'2026-10-25T10:00:00Z'}
        fixture.report.save(home/'state.json', {'meetings':{self.folder.name:{'committed':committed}}})
        _, value, _ = self.request('api/meetings/'+self.job['id'])
        self.assertEqual(value['meeting']['status'], 'In knowledge base')
        self.assertEqual(value['meeting']['indexed_revision'], 1)
        committed['approval_sha256'] = 'bad'
        fixture.report.save(home/'state.json', {'meetings':{self.folder.name:{'committed':committed}}})
        _, value, _ = self.request('api/meetings/'+self.job['id'])
        self.assertIsNone(value['meeting']['indexed_revision'])

    def test_search_and_pagination_are_owner_scoped(self):
        _, value, _ = self.request('api/meetings?q=Language&limit=1&offset=0')
        self.assertEqual(value['total'],1)
        self.assertEqual(len(value['meetings']),1)
        _, value, _ = self.request('api/meetings?q=Language&limit=1&offset=1')
        self.assertEqual(value['meetings'], [])

    def test_auth_backend_receives_only_session_cookie(self):
        self.request('api/session', headers={'Authorization': 'Bearer DO-NOT-FORWARD', 'X-Owner-Id': 'bob'})
        headers = AuthHandler.requests[-1]
        self.assertEqual(headers['Cookie'], 'token=alice-session')
        self.assertNotIn('Authorization', headers)
        self.assertNotIn('X-Owner-Id', headers)

    def test_configure_link_preserves_existing_bot_binding(self):
        home = self.root/'ai-platform/ingestion-monitor'
        home.mkdir(parents=True)
        binding = {'enabled':True,'owner_chats':{'alice':123,'bob':456},'other_setting':'keep'}
        fixture.report.save(home/'meeting-notifications.json', binding)
        with patch.object(configure_notifications.Path,'home',return_value=self.root), patch('sys.argv', [
                'configure_meeting_notifications.py','--update-url','--openwebui-url','https://meetings.example']):
            configure_notifications.main()
        result = json.loads((home/'meeting-notifications.json').read_text())
        self.assertEqual(result['owner_chats'],binding['owner_chats'])
        self.assertEqual(result['other_setting'],'keep')
        self.assertEqual(result['openwebui_url'],'https://meetings.example')
        self.assertEqual(len(list(home.glob('meeting-notifications.pre-dashboard-*.json'))),1)



class AudioTests(DashboardTests):
    def test_audio_ranges_and_owner(self):
        (self.folder/'audio.wav').write_bytes(b'0123456789')
        path='api/meetings/'+self.job['id']+'/audio'
        status,value,headers=self.request(path,headers={'Range':'bytes=2-5'})
        self.assertEqual(status,206);self.assertEqual(value,'2345')
        self.assertEqual(headers['Content-Range'],'bytes 2-5/10')
        self.assertEqual(self.request(path,cookie='bob-session')[0],404)
        self.assertEqual(self.request(path,headers={'Range':'bytes=99-100'})[0],416)
