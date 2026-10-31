"""Same-origin meeting dashboard. Open WebUI verifies identities; no worker key in browser."""
import base64
from contextlib import closing
import hashlib
import hmac
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

import meeting_report as report
import meeting_review as review
import meeting_flow as flow
import knowledge_lifecycle as lifecycle
import traffic_control

PREFIX = '/meeting-ui/dashboard'
VERSION = '2.7.1'
JID = re.compile(r'[a-f0-9]{32}\Z')
ASSETS = {'': ('dashboard.html', 'text/html'),
          'dashboard.js': ('dashboard.js', 'text/javascript'),
          'dashboard.css': ('dashboard.css', 'text/css'),
          'traffic.js': ('traffic.js','text/javascript')}


class AccessError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def is_path(path):
    path = urlsplit(path).path
    return path == PREFIX or path.startswith(PREFIX + '/')


def read_json(path, limit=8 * 1024 * 1024):
    with Path(path).open('rb') as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Dashboard input too large')
    return json.loads(raw)


def identity(headers):
    """Forward only the session cookie to a fixed loopback WebUI endpoint."""
    cookies = SimpleCookie()
    raw = headers.get('Cookie', '')
    if len(raw) > 16384:
        raise AccessError(401, 'Sign in to Open WebUI first.')
    try:
        cookies.load(raw)
        token = cookies['token'].value
    except (KeyError, ValueError):
        raise AccessError(401, 'Sign in to Open WebUI first, then reopen this dashboard.') from None
    if not token or any(char in token for char in '\r\n'):
        raise AccessError(401, 'Sign in to Open WebUI first.')
    origin = os.environ.get('MEETING_WEBUI_URL', 'http://127.0.0.1:8080').rstrip('/')
    parsed = urlsplit(origin)
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1')
            or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
        raise AccessError(503, 'Dashboard authentication needs a loopback Open WebUI URL.')
    request = Request(origin + '/api/v1/auths/', headers={'Cookie': 'token=' + token, 'Accept': 'application/json'})
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=10) as response:
            payload = response.read(65537)
        if len(payload) > 65536:
            raise ValueError('Oversized identity response')
        value = json.loads(payload)
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise AccessError(401, 'Session expired. Sign in to Open WebUI again.') from None
        raise AccessError(503, 'Open WebUI authentication is unavailable.') from None
    except (URLError, OSError, ValueError):
        raise AccessError(503, 'Open WebUI authentication is unavailable.') from None
    if (not isinstance(value, dict) or value.get('role') not in ('admin', 'user')
            or not isinstance(value.get('id'), str) or not 1 <= len(value['id']) <= 200):
        raise AccessError(403, 'This Open WebUI account is not enabled for meetings.')
    # Never return WebUI's token/email/permission payload to the browser.
    return {'id': value['id'], 'name': str(value.get('name') or 'Your account')[:200]}, token


def browser_origin(value):
    parsed = urlsplit(value)
    if (not isinstance(value, str) or len(value) > 2048 or parsed.scheme not in ('http', 'https')
            or not parsed.netloc or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment):
        raise AccessError(403, 'Refresh the dashboard from your Open WebUI address.')
    return value


def csrf_token(owner, cookie, key, origin):
    body = json.dumps([owner, int(time.time()) + 3600, hashlib.sha256(cookie.encode()).hexdigest(),
                       secrets.token_hex(16), browser_origin(origin)], separators=(',', ':')).encode()
    value = base64.urlsafe_b64encode(body).decode().rstrip('=')
    signature = hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()
    return value + '.' + signature


def check_csrf(headers, owner, cookie, key):
    origin = browser_origin(headers.get('Origin', ''))
    try:
        encoded, signature = headers.get('X-Meeting-CSRF', '').split('.')
        expected = hmac.new(key.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError('Bad signature')
        account, expiry, digest, nonce, expected_origin = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
        if (origin != expected_origin or account != owner or type(expiry) is not int or expiry < time.time()
                or expiry > time.time() + 3610 or not nonce
                or not hmac.compare_digest(digest, hashlib.sha256(cookie.encode()).hexdigest())):
            raise ValueError('Expired or mismatched token')
    except (ValueError, TypeError, UnicodeError):
        raise AccessError(403, 'Page session expired. Refresh before saving.') from None


def ingestion_record(root, folder):
    home = Path(os.environ.get('MEETING_INGESTION_HOME', str(Path(root).parent / 'ingestion'))).expanduser()
    output = {'indexed_revision': None, 'indexed_at': None, 'indexing_pending': False,
              'indexing_error': None, 'indexing_known': True}
    path = home / 'state.json'
    if not path.exists():
        output['indexing_known'] = False
        return output
    try:
        entry = read_json(path).get('meetings', {}).get(Path(folder).name, {})
        output['indexing_pending'] = bool(entry.get('pending'))
        committed = entry.get('committed') or {}
        revision = committed.get('approval_revision')
        if type(revision) is int and revision > 0:
            directory = Path(folder) / 'review' / f'r{revision:06d}'
            approval = read_json(directory / 'approval.json')
            raw = (directory / 'knowledge.md').read_bytes()
            if (committed.get('file_id') and committed.get('indexed_at')
                    and approval.get('revision') == revision
                    and approval.get('knowledge_sha256') == hashlib.sha256(raw).hexdigest()
                    and committed.get('approval_sha256') == approval['knowledge_sha256']):
                output.update(indexed_revision=revision, indexed_at=committed['indexed_at'])
        latest = home / 'last-run.json'
        if latest.exists():
            for item in read_json(latest).get('errors', []):
                if item.get('meeting') == Path(folder).name:
                    output['indexing_error'] = str(item.get('error', 'Indexing failed'))[:1000]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        output['indexing_known'] = False
    return output


def summary(root, job, meeting=None):
    value = {key: job.get(key) for key in ('id', 'created', 'updated', 'state', 'detail', 'percent', 'filename', 'error')}
    value.update(title=job.get('filename') or 'Recording not uploaded', meeting_date='',
                 revision=None, approved_revision=None, review_pending=False)
    if job.get('folder'):
        folder = Path(job['folder'])
        try:
            metadata = read_json(folder / 'meeting_metadata.json', 65536)
            if meeting:
                metadata = read_json(folder / 'review' / f"r{meeting['current']:06d}" / 'meeting_metadata.json', 65536)
                state = read_json(folder / 'review.json', 65536)
                approved = state.get('last_approved') or {}
                value.update(revision=meeting['current'], approved_revision=approved.get('revision'),
                             review_pending=bool(meeting['pending']), review_error=meeting['error'])
                payload = read_json(folder / 'review' / f"r{meeting['current']:06d}" / 'revision.json')
                value.update(transcript_reviewed=payload.get('transcript_reviewed', True), recap_ready=payload.get('recap_ready', True))
            value.update(title=metadata.get('meeting_title') or value['title'], meeting_date=metadata.get('meeting_date') or '')
        except (OSError, ValueError, TypeError, AttributeError):
            value['review_error'] = 'Some meeting metadata could not be read.'
        value.update(ingestion_record(root, folder))
    else:
        value.update(indexed_revision=None, indexed_at=None, indexing_pending=False,
                     indexing_error=None, indexing_known=True)
    current, approved, indexed = value['revision'], value['approved_revision'], value['indexed_revision']
    if job['state']=='cancelled':
        status='Cancelled before processing'
    elif job['state'] == 'waiting_upload':
        status = 'Unused upload request — expired' if time.time() - job['created'] > 1800 else 'Waiting for upload'
    elif job['state'] == 'failed':
        status = 'Processing failed'
    elif job['state'] != 'completed':
        status = 'Processing'
    elif value.get('review_pending'):
        status = 'Recap generation in progress'
    elif not value.get('transcript_reviewed', True):
        status = 'Transcript awaiting review'
    elif not value.get('recap_ready', True):
        status = 'Recap generation needs attention'
    elif not current or approved != current:
        status = 'Update awaiting review' if approved else 'Ready for review'
    elif indexed == approved:
        status = 'In knowledge base'
    elif value.get('indexing_error'):
        status = 'Indexing needs attention'
    else:
        status = 'Approved · awaiting ingestion'
    value['status'] = status
    if job.get('folder'):
        value.update(knowledge_source=Path(job['folder']).name,knowledge_owner=job['owner'])
        lifecycle.decorate(root,[value])
    return value


def owned_job(worker, jid, owner):
    if not JID.fullmatch(jid):
        raise AccessError(404, 'Meeting not found.')
    job = worker.get_job(jid)
    if not job or job['owner'] != owner:
        raise AccessError(404, 'Meeting not found.')
    return job


def detail(worker, job):
    if job['state'] != 'completed':
        return {'meeting': summary(worker.ROOT, job), 'review': None, 'history': []}
    review.ensure(worker.ROOT, job)
    value = review.view(worker.ROOT, job['id'], job['owner'])
    with review.connection(worker.ROOT) as connection:
        meeting = dict(connection.execute('SELECT * FROM meetings WHERE id=? AND owner=?', (job['id'], job['owner'])).fetchone())
        history = [json.loads(row['payload']) for row in connection.execute(
            'SELECT payload FROM revisions WHERE id=? ORDER BY revision DESC', (job['id'],))]
    metadata = summary(worker.ROOT, job, meeting)
    # Return only history fields needed by the UI; no file paths or private approval objects.
    history = [{key: row.get(key) for key in ('revision', 'created', 'kind')} for row in history]
    directory, _ = review._checked_files(job['folder'], value['revision'])
    transcript = read_json(directory / 'transcript.json')
    value['speakers'] = sorted({row.get('speaker') for row in transcript['segments'] if row.get('speaker')})
    value.pop('last_approved', None)
    value.pop('turns',None)
    value.pop('transcript',None)
    for block in value['document_blocks']:block.pop('indices',None)
    value['audio_url'] = PREFIX + '/api/meetings/' + job['id'] + '/audio'
    return {'meeting': metadata, 'review': value, 'history': history}


def download_response(handler,worker,job,name):
    review.ensure(worker.ROOT,job)
    value=review.view(worker.ROOT,job['id'],job['owner'])
    directory,_=review._checked_files(job['folder'],value['revision'])
    if name=='transcript.json':
        raw=(directory/'transcript.json').read_bytes();mime='application/json'
    elif name in ('transcript.txt','transcript.md'):
        transcript=read_json(directory/'transcript.json')
        raw=flow.document_text(transcript,value['metadata'].get('meeting_title') or 'Transcript').encode('utf-8');mime='text/plain; charset=utf-8'
    elif name=='recovered.md':
        raw=value['recovered_draft'].encode('utf-8');mime='text/plain; charset=utf-8'
    elif name=='generation-log.json':
        raw=json.dumps(value['generation_attempts'],ensure_ascii=False,indent=2).encode('utf-8');mime='application/json'
    else:raise AccessError(404,'Download not found.')
    handler.send_response(200);handler.send_header('Content-Type',mime)
    handler.send_header('Content-Disposition',f'attachment; filename="{job["id"]}-r{value["revision"]}-{name}"')
    handler.send_header('Content-Length',str(len(raw)));handler.send_header('Cache-Control','private, no-store')
    handler.send_header('X-Content-Type-Options','nosniff');handler.end_headers();handler.wfile.write(raw)


def audio_response(handler, worker, job):
    folder = Path(job['folder'])
    path = folder / ('audio' + Path(job['filename']).suffix.lower())
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(Path(worker.ROOT).resolve()):
        raise AccessError(404, 'Recording unavailable.')
    size = path.stat().st_size
    start, end, status = 0, size - 1, 200
    requested = handler.headers.get('Range')
    if requested:
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
        if not match or not any(match.groups()):
            raise AccessError(416, 'Unsupported audio range.')
        a, b = match.groups()
        if a:
            start, end = int(a), min(int(b), end) if b else end
        else:
            start = max(0, size - int(b))
        if start > end or start >= size:
            raise AccessError(416, 'Audio range is outside the recording.')
        status = 206
    import mimetypes
    handler.send_response(status)
    handler.send_header('Content-Type', mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
    handler.send_header('Content-Length', str(end - start + 1))
    handler.send_header('Accept-Ranges', 'bytes')
    handler.send_header('Cache-Control', 'private, no-store')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    if status == 206:
        handler.send_header('Content-Range', f'bytes {start}-{end}/{size}')
    handler.end_headers()
    with path.open('rb') as stream:
        stream.seek(start)
        remaining = end - start + 1
        while remaining:
            block = stream.read(min(65536, remaining))
            if not block: break
            handler.wfile.write(block)
            remaining -= len(block)


def route(handler, worker, method):
    """Return True for dashboard requests, including handled failures."""
    if not is_path(handler.path):
        return False
    try:
        path = urlsplit(handler.path)
        suffix = path.path[len(PREFIX):].strip('/')
        if method == 'GET' and suffix in ASSETS:
            filename, mime = ASSETS[suffix]
            if filename=='dashboard.html' and os.environ.get('SMARTINIS_NOTES_ENABLED')=='1' and parse_qs(path.query).get('view')==['notes']:
                filename='notes.html'
            if filename=='dashboard.html' and os.environ.get('SMARTINIS_TEXT_ENABLED')=='1' and parse_qs(path.query).get('view')==['text']:
                filename='text.html'
            if filename=='dashboard.html' and parse_qs(path.query).get('view')==['traffic']:filename='traffic.html'
            handler.send(200, (Path(__file__).parent / filename).read_text(encoding='utf-8'), mime)
            return True
        if not suffix.startswith('api/'):
            raise AccessError(404, 'Page not found.')
        user, cookie = identity(handler.headers)
        owner = user['id']
        if method == 'POST':
            check_csrf(handler.headers, owner, cookie, worker.API_KEY)
            if handler.headers.get_content_type() != 'application/json':
                raise AccessError(415, 'Use JSON for dashboard changes.')
        if method == 'GET' and suffix == 'api/session':
            handler.send(200, {'user': user, 'csrf': csrf_token(owner, cookie, worker.API_KEY, handler.headers.get('X-Meeting-Origin', ''))})
        elif suffix=='api/traffic' and method=='GET':
            handler.send(200,traffic_control.snapshot(worker,owner))
        elif suffix=='api/traffic' and method=='POST':
            obj=json.loads(handler.rfile.read(handler.length(4096)))
            if not isinstance(obj,dict) or obj.get('action')!='cancel-waiting' or obj.get('acknowledge') is not True:raise AccessError(400,'Confirm cancellation of a waiting job.')
            if not isinstance(obj.get('key'),str) or not 1<=len(obj['key'])<=200:raise AccessError(400,'Invalid task identity.')
            try:traffic_control.cancel(worker,owner,obj.get('kind'),obj['key'])
            except KeyError:raise AccessError(404,'Job not found.') from None
            except ValueError as exc:raise AccessError(409,str(exc)) from None
            handler.send(200,{'message':'Waiting job cancelled. Source and previous revisions retained.'})
        elif method == 'GET' and suffix == 'api/meetings':
            query = parse_qs(path.query)
            offset = max(0, int(query.get('offset', ['0'])[0]))
            limit = min(100, max(1, int(query.get('limit', ['50'])[0])))
            search = query.get('q', [''])[0][:200].casefold()
            selected_status = query.get('status', [''])[0]
            with worker.connect() as connection:
                jobs = [dict(row) for row in connection.execute('SELECT * FROM jobs WHERE owner=? ORDER BY updated DESC', (owner,))]
            with review.connection(worker.ROOT) as connection:
                meetings = {row['id']: dict(row) for row in connection.execute('SELECT * FROM meetings WHERE owner=?', (owner,))}
            rows = [summary(worker.ROOT, job, meetings.get(job['id'])) for job in jobs]
            for row in rows:
                row['kind']='audio';row.setdefault('knowledge_source','')
            if os.environ.get('SMARTINIS_NOTES_ENABLED')=='1':
                import notes_library
                rows+=notes_library.summaries(worker.ROOT,owner)
                rows.sort(key=lambda row:(row.get('updated') or row.get('created') or 0,row['id']),reverse=True)
            if os.environ.get('SMARTINIS_TEXT_ENABLED')=='1':
                import text_store,text_web
                if text_web.allowed(owner):rows+=text_store.summaries(worker.ROOT,owner)
                rows.sort(key=lambda row:(row.get('updated') or row.get('created') or 0,row['id']),reverse=True)
            for row in rows:
                if row['kind']=='notes':row['knowledge_source']='notes-'+row['id'][5:]
                elif row['kind']=='text':row['knowledge_source']=row['id']
                row['knowledge_owner']=owner
            lifecycle.decorate(worker.ROOT,rows)
            counts = {'total': len(rows), 'processing': sum(row['state'] in ('uploading', 'queued', 'transcribing', 'analyzing') for row in rows),
                      'review': sum(row['status'] in ('Ready for review', 'Update awaiting review', 'Transcript awaiting review', 'Transcription awaiting review', 'Notes generation needs attention', 'Recap generation needs attention') for row in rows),
                      'indexed': sum(row.get('indexed_revision') is not None for row in rows)}
            counts['processing']+=sum(row['kind']=='notes' and row['state'].endswith(('-queued','-running')) for row in rows)
            selected_kind=query.get('kind',[''])[0]
            filtered = [row for row in rows if (not search or search in (row['title'] + ' ' + row['id'] + ' ' + row['meeting_date']).casefold())
                        and (not selected_status or row['status'] == selected_status) and (not selected_kind or row['kind']==selected_kind)]
            handler.send(200, {'meetings': filtered[offset:offset+limit], 'total': len(filtered), 'counts': counts,
                               'statuses': sorted({row['status'] for row in rows}), 'offset': offset, 'limit': limit})
        elif method=='POST' and suffix.startswith('api/knowledge/'):
            parts=suffix.split('/')
            if len(parts)!=4:raise AccessError(404,'Source not found.')
            kind,jid=parts[2:]
            if kind=='audio':
                job=owned_job(worker,jid,owner)
                if not job.get('folder') or job['state']!='completed':raise AccessError(409,'Wait for processing to finish.')
                with review.connection(worker.ROOT) as db:
                    meeting=db.execute('SELECT * FROM meetings WHERE id=? AND owner=?',(jid,owner)).fetchone()
                row=summary(worker.ROOT,job,dict(meeting) if meeting else None)
                source=Path(job['folder']).name
            elif kind=='notes' and os.environ.get('SMARTINIS_NOTES_ENABLED')=='1':
                import notes_library
                row=next((r for r in notes_library.summaries(worker.ROOT,owner) if r['id']==jid),None)
                source='notes-'+jid[5:]
            elif kind=='text' and os.environ.get('SMARTINIS_TEXT_ENABLED')=='1':
                import text_store,text_web
                row=next((r for r in text_store.summaries(worker.ROOT,owner) if r['id']==jid),None) if text_web.allowed(owner) else None
                source=jid
            else:raise AccessError(404,'Source not found.')
            if not row:raise AccessError(404,'Source not found.')
            obj=json.loads(handler.rfile.read(handler.length(4096)))
            if not isinstance(obj,dict) or obj.get('acknowledge') is not True:raise AccessError(400,'Confirm the Knowledge change.')
            if (obj.get('revision') is not None and type(obj['revision']) is not int) or obj.get('revision')!=row.get('approved_revision') or (obj.get('action')=='restore' and not row.get('approved_revision')):raise AccessError(409,'Approved revision changed or missing. Open, review and approve it before restoring.')
            def verify_approval(db):
                if kind=='audio':
                    approval=read_json(Path(job['folder'])/'review.json').get('last_approved') if (Path(job['folder'])/'review.json').exists() else None
                    latest=approval.get('revision') if approval else None
                else:
                    table='notes_jobs' if kind=='notes' else 'text_docs'
                    record=db.execute('SELECT approved FROM '+table+' WHERE id=? AND owner=?',(jid,owner)).fetchone()
                    latest=record['approved'] if record else None
                if latest!=obj.get('revision'):raise ValueError('Approved revision changed. Refresh and review it again.')
            try:result=lifecycle.change(worker.ROOT,source,owner,obj.get('action'),obj.get('generation'),verify=verify_approval)
            except ValueError as exc:raise AccessError(409,str(exc)) from None
            handler.send(200,{'knowledge_status':result['status'],'message':'Removal queued for the next scheduled ingestion. Source retained.' if result['status']=='pending' else 'Restoration approved for the next scheduled ingestion.'})
        elif suffix.startswith('api/meetings/'):
            parts = suffix.split('/')
            job = owned_job(worker, parts[2], owner)
            if method == 'GET' and len(parts) == 3:
                handler.send(200, detail(worker, job))
            elif method == 'GET' and len(parts) == 4 and parts[3] == 'audio':
                audio_response(handler, worker, job)
            elif method == 'GET' and len(parts) == 4 and parts[3] in ('transcript.txt','transcript.md','transcript.json','recovered.md','generation-log.json'):
                if job['state']!='completed':raise AccessError(409,'Transcript is not ready.')
                download_response(handler,worker,job,parts[3])
            elif method == 'GET' and len(parts) == 5 and parts[3] == 'revisions':
                number = int(parts[4])
                if job['state'] != 'completed':
                    raise AccessError(409, 'The meeting is still processing.')
                review.ensure(worker.ROOT, job)
                with review.connection(worker.ROOT) as connection:
                    exists = connection.execute('SELECT 1 FROM revisions WHERE id=? AND revision=?', (job['id'], number)).fetchone()
                if not exists:
                    raise AccessError(404, 'Revision not found.')
                directory, _ = review._checked_files(job['folder'], number)
                handler.send(200, {'revision': number, 'report': (directory/'report.md').read_text(encoding='utf-8')})
            elif method == 'POST' and len(parts) == 3:
                if job['state'] != 'completed':
                    raise AccessError(409, 'Wait for meeting processing to finish.')
                review.ensure(worker.ROOT, job)
                obj = json.loads(handler.rfile.read(handler.length(2 * 1024 * 1024)))
                if not isinstance(obj, dict) or obj.get('action') not in ('dashboard-save', 'approve', 'transcript-save', 'transcript-confirm', 'retry'):
                    raise AccessError(400, 'Choose Save draft or Approve this revision.')
                result = review.act(worker.ROOT, job['id'], owner, obj)
                handler.send(200, {**detail(worker, job), 'message': result['message']})
            else:
                raise AccessError(404, 'Page not found.')
        else:
            raise AccessError(404, 'Page not found.')
    except AccessError as exc:
        handler.send(exc.status, {'error': exc.message})
    except review.Conflict as exc:
        handler.send(409, {'error': str(exc)})
    except (ValueError, KeyError, TypeError):
        handler.send(400, {'error': 'Invalid dashboard request.'})
    except Exception:
        handler.send(503, {'error': 'Dashboard data is temporarily unavailable. Refresh before retrying.'})
    return True
