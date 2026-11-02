"""Worker-key protected owner-scoped research API; no browser capabilities."""
import json
import os
import re
from urllib.parse import urlsplit
import research_jobs as jobs

PREFIX='/v1/research/jobs'


def route(handler, worker, method):
    path=urlsplit(handler.path).path
    if path!=PREFIX and not path.startswith(PREFIX+'/'): return False
    try:
        if not handler.auth():
            handler.send(401,{'error':'Unauthorized'}); return True
        owner=handler.headers.get('X-Owner-Id','')
        allowed={x.strip() for x in os.environ.get('RESEARCH_ALLOWED_OWNERS','').split(',') if x.strip()}
        if not owner or owner not in allowed:
            handler.send(403,{'error':'Research not enabled for this account'}); return True
        if method=='POST' and path==PREFIX:
            value=json.loads(handler.rfile.read(handler.length(20000)))
            if not isinstance(value,dict) or set(value)!={'request_key','question','mode'}: raise ValueError()
            jid=jobs.submit(worker.ROOT,owner,value['request_key'],value['question'],value['mode'])
            handler.send(202,jobs.get(worker.ROOT,owner,jid))
        elif method=='GET' and re.fullmatch(PREFIX+r'/[a-f0-9]{32}',path):
            handler.send(200,jobs.get(worker.ROOT,owner,path.rsplit('/',1)[1]))
        elif method=='POST' and re.fullmatch(PREFIX+r'/[a-f0-9]{32}/review',path):
            value=json.loads(handler.rfile.read(handler.length(4096)))
            if not isinstance(value,dict) or set(value)-{'decision','proof'}:raise ValueError()
            jid=path.split('/')[-2]
            handler.send(200,jobs.review_queries(worker.ROOT,owner,jid,value.get('decision'),value.get('proof','')))
        else: raise KeyError()
    except KeyError: handler.send(404,{'error':'Research not found'})
    except (ValueError,TypeError): handler.send(400,{'error':'Invalid research request or queue full'})
    return True
