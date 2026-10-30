"""Scoped upload capabilities. No capability can approve or read source/revisions."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import time
from urllib.parse import urlsplit

import meeting_review as review
import notes_store as store

PREFIX='/meeting-ui/note-upload'
API='/v1/notes/sessions'


def init(root):
    with review.connection(root) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS notes_upload_sessions(
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, request_key TEXT NOT NULL,
          token TEXT UNIQUE NOT NULL, language TEXT NOT NULL, created REAL NOT NULL,
          metadata TEXT, job_id TEXT, UNIQUE(owner,request_key))''')


def create(root,owner,key,language):
    if (not isinstance(owner,str) or not 1<=len(owner)<=200 or not isinstance(key,str) or
        not 1<=len(key)<=250 or language not in ('English','Dutch','Italian')):
        raise ValueError('Invalid authenticated upload request')
    init(root)
    with review.connection(root) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM notes_upload_sessions WHERE owner=? AND request_key=?',(owner,key)).fetchone()
        if row:return dict(row)
        pending=db.execute('SELECT count(*) FROM notes_upload_sessions WHERE owner=? AND job_id IS NULL AND created>?',
            (owner,time.time()-1800)).fetchone()[0]
        if pending>=10:raise ValueError('Too many open upload cards; use an existing card or retry later')
        sid=secrets.token_hex(16);token=secrets.token_urlsafe(32)
        db.execute('INSERT INTO notes_upload_sessions VALUES (?,?,?,?,?,?,NULL,NULL)',(sid,owner,key,token,language,time.time()))
        return dict(db.execute('SELECT * FROM notes_upload_sessions WHERE id=?',(sid,)).fetchone())


def get(root,identifier,owner=None):
    init(root)
    with review.connection(root) as db:
        row=db.execute('SELECT * FROM notes_upload_sessions WHERE '+('id=? AND owner=?' if owner else 'token=?'),
            (identifier,owner) if owner else (identifier,)).fetchone()
    if not row:raise KeyError('Upload session not found')
    row=dict(row)
    if not row['job_id'] and time.time()-row['created']>1800:
        raise ValueError('Upload card expired; start a new request')
    # After commitment capabilities expose progress only, for at most 24 hours.
    if not owner and time.time()-row['created']>86400:
        raise ValueError('Upload card expired; use the dashboard')
    return row


def status(root,session):
    result={'id':session['id'],'state':'waiting_upload','job_id':session['job_id'],'created':session['created']}
    if session['job_id']:
        job=store.view(root,session['job_id'],session['owner'])['job']
        result['state']=job['state']
        if job['state'] in ('page-review','recap-review','approved'):
            result['dashboard_path']='/meeting-ui/notes#'+job['id']
        elif job['state']=='failed':
            result['recovery_path']='/meeting-ui/notes#'+job['id']
    return result


def upload_directory(root,session):
    target=Path(root)/('notes-upload-'+session['id'])
    if target.is_symlink() or target.resolve().parent!=Path(root).resolve():
        raise ValueError('Unsafe upload directory')
    target.mkdir(mode=0o700,exist_ok=True)
    return target


def metadata(root,session,obj):
    from datetime import date
    if not isinstance(obj,dict) or set(obj)!= {'title','date','count'}:
        raise ValueError('Provide title, date and picture count')
    if (not isinstance(obj['title'],str) or not obj['title'].strip() or len(obj['title'])>150 or
        any(ord(c)<32 for c in obj['title']) or type(obj['count']) is not int or not 1<=obj['count']<=store.MAX_PICTURES or
        not isinstance(obj['date'],str) or len(obj['date'])!=10 or date.fromisoformat(obj['date']).isoformat()!=obj['date']):
        raise ValueError('Use a title, valid notes date and 1–10 pictures')
    encoded=json.dumps(obj,sort_keys=True)
    with review.connection(root) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM notes_upload_sessions WHERE id=?',(session['id'],)).fetchone()
        if row['job_id']:raise review.Conflict('This card has already started processing')
        if row['metadata'] and row['metadata']!=encoded:
            raise review.Conflict('Upload already started with different details; open a new card')
        db.execute('UPDATE notes_upload_sessions SET metadata=? WHERE id=?',(encoded,session['id']))


def image(root,session,index,raw):
    # SQLite serializes metadata, file writes and commitment across HTTP threads.
    with review.connection(root) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM notes_upload_sessions WHERE id=?',(session['id'],)).fetchone()
        if row['job_id']:raise review.Conflict('Pictures cannot change after processing starts')
        meta=json.loads(row['metadata']) if row['metadata'] else None
        if not meta or not 0<=index<meta['count'] or not 0<len(raw)<=store.MAX_BYTES:
            raise ValueError('Invalid picture slot or size')
        directory=upload_directory(root,session);target=directory/('%03d.upload'%index)
        if target.is_symlink():raise ValueError('Unsafe picture slot')
        if target.exists():
            if target.read_bytes()!=raw:raise review.Conflict('This picture slot contains a different file')
            return
        if sum(p.stat().st_size for p in directory.glob('*.upload'))+len(raw)>store.MAX_TOTAL_BYTES:
            raise ValueError('The pictures exceed 48 MiB in total')
        if __import__('shutil').disk_usage(root).free<256*1024*1024+2*len(raw):
            raise ValueError('Insufficient free space for this upload')
        # Decode before preserving a staged file; no model work happens here.
        store._decode(raw)
        temporary=target.with_suffix('.pending')
        with temporary.open('wb') as handle:
            handle.write(raw);handle.flush();os.fsync(handle.fileno())
        os.replace(temporary,target)


def start(root,session):
    # submit is itself idempotent. Do not hold a DB write transaction while it writes.
    current=get(root,session['id'],session['owner'])
    if current['job_id']:return current['job_id']
    if not current['metadata']:raise ValueError('Confirm the card details first')
    meta=json.loads(current['metadata']);directory=upload_directory(root,current)
    raws=[]
    for index in range(meta['count']):
        target=directory/('%03d.upload'%index)
        if target.is_symlink() or not target.is_file():raise ValueError('Upload all pictures before starting')
        raws.append(target.read_bytes())
    jid=store.submit(root,current['owner'],'notes-card:'+current['id'],meta['title'],current['language'],raws,
        notes_date=meta['date'],auto_recap=True)
    with review.connection(root) as db:
        db.execute('UPDATE notes_upload_sessions SET job_id=? WHERE id=? AND job_id IS NULL',(jid,current['id']))
    return jid


def route(handler,worker,method):
    path=urlsplit(handler.path).path
    if not (path==API or path.startswith(API+'/') or path.startswith(PREFIX+'/')):return False
    try:
        if path==API or path.startswith(API+'/'):
            if not handler.auth():
                handler.send(401,{'error':'Unauthorized'});return True
            owner=handler.headers.get('X-Owner-Id','')
            allowed=os.environ.get('NOTES_ALLOWED_OWNERS','')
            if not owner or (allowed and owner not in {v.strip() for v in allowed.split(',')}):
                handler.send(403,{'error':'Notes is not enabled for this account'});return True
            if path==API and method=='POST':
                obj=json.loads(handler.rfile.read(handler.length(4096)))
                if not isinstance(obj,dict):raise ValueError('Use an upload request object')
                session=create(worker.ROOT,owner,obj.get('request_key'),obj.get('language','English'))
                handler.send(201,{'id':session['id'],'upload_token':session['token']})
            elif method=='GET' and path.startswith(API+'/'):
                handler.send(200,status(worker.ROOT,get(worker.ROOT,path[len(API)+1:],owner)))
            else:handler.send(404,{'error':'Not found'})
            return True
        parts=path[len(PREFIX)+1:].split('/')
        if len(parts) not in (2,3):raise KeyError('Not found')
        action,token=parts[:2];session=get(worker.ROOT,token)
        if action=='view' and method=='GET' and len(parts)==2:
            html=(Path(__file__).parent/'notes_upload.html').read_text()
            handler.send(200,html.replace('__TOKEN__',session['token']),'text/html')
        elif action=='status' and method=='GET' and len(parts)==2:
            handler.send(200,status(worker.ROOT,session))
        elif action=='metadata' and method=='POST' and len(parts)==2:
            metadata(worker.ROOT,session,json.loads(handler.rfile.read(handler.length(4096))))
            handler.send(200,{'saved':True})
        elif action=='image' and method=='POST' and len(parts)==3:
            image(worker.ROOT,session,int(parts[2]),handler.rfile.read(handler.length(store.MAX_BYTES)))
            handler.send(200,{'saved':True})
        elif action=='start' and method=='POST' and len(parts)==2:
            # Require a small explicit POST body; neither GET nor polling starts jobs.
            obj=json.loads(handler.rfile.read(handler.length(256)))
            if obj!={'confirmed':True}:raise ValueError('Confirm before processing')
            start(worker.ROOT,session)
            handler.send(202,status(worker.ROOT,get(worker.ROOT,token)))
        else:handler.send(404,{'error':'Not found'})
    except KeyError:handler.send(404,{'error':'Upload session not found'})
    except review.Conflict as exc:handler.send(409,{'error':str(exc)})
    except (ValueError,TypeError,OverflowError) as exc:handler.send(400,{'error':str(exc)[:200] or 'Invalid upload request'})
    return True
