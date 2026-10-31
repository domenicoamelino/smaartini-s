"""Text card and dashboard routes. Scoped submit-only capabilities; owner/CSRF review."""
import json
import os
from pathlib import Path
import secrets
import time
from urllib.parse import urlsplit
import meeting_dashboard as dashboard
import text_store as store

PREFIX='/meeting-ui/text'
CARD='/meeting-ui/write'
API='/v1/text/sessions'
ASSETS={'text.js':'text/javascript','text_markdown.js':'text/javascript'}

def enabled():return os.environ.get('SMARTINIS_TEXT_ENABLED')=='1'
def allowed(owner):
    values=os.environ.get('TEXT_ALLOWED_OWNERS',os.environ.get('NOTES_ALLOWED_OWNERS',''))
    return bool(owner) and (not values or owner in {x.strip() for x in values.split(',')})

def session(root,identifier,owner=None):
    with store.connection(root) as db:
        row=db.execute('SELECT * FROM text_sessions WHERE '+('id=? AND owner=?' if owner else 'token=?'),
            (identifier,owner) if owner else (identifier,)).fetchone()
    if not row:raise KeyError('Text card not found')
    row=dict(row)
    if not allowed(row['owner']):raise dashboard.AccessError(403,'Text is not enabled for this account')
    if not row['doc_id'] and time.time()-row['created']>1800:raise ValueError('Text card expired; start a new request')
    if not owner and time.time()-row['created']>86400:raise ValueError('Text card expired; open the dashboard')
    return row

def create(root,owner,key):
    if not isinstance(key,str) or not 1<=len(key)<=250:raise ValueError('Use a saved chat request identity')
    with store.connection(root) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM text_sessions WHERE owner=? AND request_key=?',(owner,key)).fetchone()
        if row:return dict(row)
        count=db.execute('SELECT count(*) FROM text_sessions WHERE owner=? AND doc_id IS NULL AND created>?',(owner,time.time()-1800)).fetchone()[0]
        if count>=10:raise ValueError('Too many open text cards; use an existing card or retry later')
        sid=secrets.token_hex(16);token=secrets.token_urlsafe(32)
        db.execute('INSERT INTO text_sessions VALUES (?,?,?,?,?,NULL)',(sid,owner,key,token,time.time()))
    return session(root,sid,owner)

def status(value):
    result={'id':value['id'],'created':value['created'],'state':'draft-saved' if value['doc_id'] else 'waiting_text','doc_id':value['doc_id']}
    if value['doc_id']:result['dashboard_path']='/meeting-ui/dashboard/?view=text#'+value['doc_id']
    return result

def route(handler,worker,method):
    path=urlsplit(handler.path).path
    if not (path.startswith(PREFIX+'/') or path.startswith(CARD+'/') or path==API or path.startswith(API+'/')):return False
    try:
        if path==API or path.startswith(API+'/'):
            if not handler.auth():raise dashboard.AccessError(401,'Unauthorized')
            owner=handler.headers.get('X-Owner-Id','')
            if not allowed(owner):raise dashboard.AccessError(403,'Text is not enabled for this account')
            if path==API and method=='POST':
                obj=json.loads(handler.rfile.read(handler.length(4096)))
                if not isinstance(obj,dict):raise ValueError('Use a text card request')
                value=create(worker.ROOT,owner,obj.get('request_key'))
                handler.send(201,{'id':value['id'],'upload_token':value['token']})
            elif path.startswith(API+'/') and method=='GET':handler.send(200,status(session(worker.ROOT,path[len(API)+1:],owner)))
            else:raise KeyError()
            return True
        if path.startswith(CARD+'/'):
            parts=path[len(CARD)+1:].split('/')
            if len(parts)!=2:raise KeyError()
            action,token=parts;value=session(worker.ROOT,token)
            if method=='GET' and action=='view':
                template=(Path(__file__).parent/'text_card.html').read_text()
                # The iframe has an opaque origin, matching the existing audio card pattern.
                handler.send(200,template.replace('__TOKEN__',value['token']),'text/html')
            elif method=='GET' and action=='status':handler.send(200,status(value))
            elif method=='POST' and action=='submit':
                if handler.headers.get_content_type()!='application/json':raise ValueError('Use JSON text content')
                obj=json.loads(handler.rfile.read(handler.length(store.MAX_BODY)))
                if not isinstance(obj,dict) or set(obj)!= {'confirmed','payload'} or obj['confirmed'] is not True:raise ValueError('Confirm before saving this draft')
                jid=store.submit(worker.ROOT,value['owner'],'text-card:'+value['id'],obj['payload'])
                with store.connection(worker.ROOT) as db:db.execute('UPDATE text_sessions SET doc_id=? WHERE id=? AND doc_id IS NULL',(jid,value['id']))
                handler.send(201,status(session(worker.ROOT,token)))
            else:raise KeyError()
            return True
        suffix=path[len(PREFIX)+1:]
        if method=='GET' and suffix in ASSETS:
            handler.send(200,(Path(__file__).parent/suffix).read_text(),ASSETS[suffix]);return True
        user,cookie=dashboard.identity(handler.headers);owner=user['id']
        if not allowed(owner):raise dashboard.AccessError(403,'Text is not enabled for this account')
        if method=='POST':dashboard.check_csrf(handler.headers,owner,cookie,worker.API_KEY)
        if suffix=='api/session' and method=='GET':
            origin=dashboard.browser_origin(handler.headers.get('X-Meeting-Origin',''))
            public=os.environ.get('TEXT_PUBLIC_ORIGIN',os.environ.get('NOTES_PUBLIC_ORIGIN','')).rstrip('/')
            if public:public=dashboard.browser_origin(public)
            if urlsplit(origin).netloc!=handler.headers.get('Host','') and origin!=public:raise dashboard.AccessError(403,'Open Text through the configured WebUI address')
            handler.send(200,{'user':user,'csrf':dashboard.csrf_token(owner,cookie,worker.API_KEY,origin)})
        elif suffix.startswith('api/doc/'):
            parts=suffix.split('/');jid=parts[2]
            if len(parts)==5 and parts[3]=='revision' and method=='GET':
                handler.send(200,store.historical(worker.ROOT,jid,owner,int(parts[4])));return True
            if len(parts)!=3:raise KeyError()
            value=store.view(worker.ROOT,jid,owner)
            if method=='GET':handler.send(200,value)
            elif method=='POST':
                if handler.headers.get_content_type()!='application/json':raise ValueError('Use JSON text actions')
                obj=json.loads(handler.rfile.read(handler.length(store.MAX_BODY+4096)))
                handler.send(200,store.act(worker.ROOT,jid,owner,obj))
            else:raise KeyError()
        else:raise KeyError()
    except dashboard.AccessError as exc:handler.send(exc.status,{'error':exc.message})
    except KeyError:handler.send(404,{'error':'Text/card not found for this account'})
    except store.Conflict as exc:handler.send(409,{'error':str(exc)})
    except (ValueError,TypeError) as exc:handler.send(400,{'error':str(exc)[:200] or 'Invalid text request'})
    except Exception:handler.send(503,{'error':'Text temporarily unavailable; saved material is retained'})
    return True
