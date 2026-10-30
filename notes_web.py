"""Notes dashboard routes reuse authenticated WebUI identity and CSRF helpers."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit,parse_qs

import meeting_dashboard as dashboard
import meeting_review as review
import notes_store as notes
import notes_models

PREFIX='/meeting-ui/notes'
ASSETS={'':('notes.html','text/html'),'notes.js':('notes.js','text/javascript'),
    'notes.css':('notes.css','text/css')}


def route(handler,worker,method):
    path=urlsplit(handler.path).path
    if path!=PREFIX and not path.startswith(PREFIX+'/'):
        return False
    suffix=path[len(PREFIX):].strip('/')
    try:
        if method=='GET' and suffix in ASSETS:
            name,mime=ASSETS[suffix]
            handler.send(200,(Path(__file__).parent/name).read_text(encoding='utf-8'),mime)
            return True
        user,cookie=dashboard.identity(handler.headers)
        owner=user['id']
        allowed=os.environ.get('NOTES_ALLOWED_OWNERS','')
        if allowed and owner not in {x.strip() for x in allowed.split(',') if x.strip()}:
            raise dashboard.AccessError(403,'Notes pilot is not enabled for this account')
        if method=='POST':
            dashboard.check_csrf(handler.headers,owner,cookie,worker.API_KEY)
        if suffix=='api/session' and method=='GET':
            origin=dashboard.browser_origin(handler.headers.get('X-Notes-Origin',''))
            public=os.environ.get('NOTES_PUBLIC_ORIGIN','').rstrip('/')
            if public:
                public=dashboard.browser_origin(public)
            if urlsplit(origin).netloc != handler.headers.get('Host','') and origin!=public:
                raise dashboard.AccessError(403,'Notes origin does not match this host')
            handler.send(200,{'user':user,'csrf':dashboard.csrf_token(owner,cookie,worker.API_KEY,
                origin)})
        elif suffix=='api/notes' and method=='GET':
            available=notes_models.available_mb()
            handler.send(200,{'notes':notes.listing(worker.ROOT,owner),
                'resource_wait':available is None or available<int(os.environ.get('NOTES_MIN_AVAILABLE_MB','8192'))})
        elif suffix=='api/upload' and method=='POST':
            from urllib.parse import unquote
            title=unquote(handler.headers.get('X-Notes-Title',''))
            language=handler.headers.get('X-Notes-Language','English')
            key=handler.headers.get('X-Request-Key','')
            raw=handler.rfile.read(handler.length(notes.MAX_BYTES))
            jid=notes.submit(worker.ROOT,owner,key,title,language,raw)
            handler.send(202,notes.view(worker.ROOT,jid,owner))
        elif suffix=='api/corrections' and method=='GET':
            handler.send(200,{'corrections':notes.corrections(worker.ROOT,owner)})
        else:
            parts=suffix.split('/')
            if len(parts) not in (3,4,5) or parts[:2]!=['api','note']:
                raise dashboard.AccessError(404,'Notes page not found')
            jid=parts[2]
            value=notes.view(worker.ROOT,jid,owner)
            if len(parts)==5 and parts[3]=='diagram' and method=='POST':
                handler.send(200,notes.replace_diagram(worker.ROOT,jid,owner,int(parts[4]),
                    int(handler.headers.get('X-Notes-Revision','-1')),handler.rfile.read(handler.length(notes.MAX_BYTES))))
            elif ((len(parts)==4 and parts[3]=='original') or (len(parts)==5 and parts[3]=='asset')) and method=='GET':
                if parts[3]=='asset':mime,raw=notes.diagram_asset(worker.ROOT,jid,owner,parts[4])
                else:
                    index=int(parse_qs(urlsplit(handler.path).query).get('page',['0'])[0])
                    mime,raw=notes.original(worker.ROOT,jid,owner,index)
                handler.send_response(200)
                for k,v in {'Content-Type':mime,
                    'Content-Length':str(len(raw)),'Cache-Control':'no-store',
                    'X-Content-Type-Options':'nosniff','Cross-Origin-Resource-Policy':'same-origin',
                    'Referrer-Policy':'no-referrer'}.items():
                    handler.send_header(k,v)
                handler.send_header('Content-Security-Policy',"default-src 'none'; style-src 'none'; sandbox")
                handler.end_headers()
                handler.wfile.write(raw)
            elif len(parts)==3 and method=='GET':
                handler.send(200,value)
            elif len(parts)==3 and method=='POST':
                if handler.headers.get_content_type()!='application/json':
                    raise ValueError('Use a JSON Notes action')
                obj=json.loads(handler.rfile.read(handler.length(1024*1024)))
                handler.send(200,notes.act(worker.ROOT,jid,owner,obj))
            else:
                raise dashboard.AccessError(404,'Notes page not found')
    except dashboard.AccessError as exc:
        handler.send(exc.status,{'error':exc.message})
    except KeyError:
        handler.send(404,{'error':'Note not found'})
    except review.Conflict as exc:
        handler.send(409,{'error':str(exc)})
    except ValueError as exc:
        handler.send(400,{'error':str(exc)[:250] or 'Invalid Notes input'})
    except TypeError:
        handler.send(400,{'error':'Invalid Notes request. Check the saved revision and input.'})
    except Exception:
        handler.send(503,{'error':'Notes data temporarily unavailable; source retained'})
    return True
