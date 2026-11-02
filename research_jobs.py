"""Durable owner-scoped bounded research queue. HTTP handlers never run inference."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from research_question import answer_style

import heavy_gate
from research_privacy import Guard, PrivacyBlocked, QueryReviewRequired, plan, route, private_intent, contains, normalized

TERMINAL = ('completed', 'failed', 'cancelled')
STAGES = {'queued': 'Waiting for the shared processing slot', 'planning': 'Planning research locally',
          'knowledge': 'Retrieving approved private Knowledge', 'searching': 'Searching public sources',
          'reading': 'Reading public sources', 'comparing': 'Comparing evidence and source reliability',
          'drafting': 'Drafting answer with separate citations', 'privacy':'Checking public-query privacy locally', 'abstracting':'Preparing a public research brief locally'}
STAGES['search_wait']='Waiting for public search provider; retrying within the search limit'
STAGES['verifying']='Checking dates and factual claims against sources'


def connect(root):
    db = sqlite3.connect(Path(root)/'research.sqlite3', timeout=5)
    db.row_factory = sqlite3.Row
    return db


def init(root):
    with closing(connect(root)) as db, db:
        db.execute('''CREATE TABLE IF NOT EXISTS research_jobs(
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, request_key TEXT NOT NULL,
            fingerprint TEXT NOT NULL, question TEXT NOT NULL, mode TEXT NOT NULL,
            status TEXT NOT NULL, stage TEXT NOT NULL, created REAL NOT NULL,
            updated REAL NOT NULL, result TEXT, UNIQUE(owner,request_key))''')
        db.execute('CREATE TABLE IF NOT EXISTS research_events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,job TEXT NOT NULL,stage TEXT NOT NULL,status TEXT NOT NULL,created REAL NOT NULL)')
        if 'ready_at' not in {r[1] for r in db.execute('PRAGMA table_info(research_jobs)')}:
            db.execute('ALTER TABLE research_jobs ADD COLUMN ready_at REAL')
        db.execute('UPDATE research_jobs SET ready_at=created WHERE ready_at IS NULL')
        db.execute("UPDATE research_jobs SET status='failed',stage='Server restarted; submit a new request to retry',updated=? WHERE status='running'", (time.time(),))


def submit(root, owner, key, question, mode):
    if (not isinstance(owner, str) or not 1 <= len(owner) <= 200 or
            not isinstance(key, str) or not 1 <= len(key) <= 250 or
            not isinstance(question, str) or not 1 <= len(question.strip()) <= 4000 or
            mode not in ('knowledge', 'web', 'auto')): raise ValueError('Invalid research request')
    fingerprint = hashlib.sha256(json.dumps([question, mode]).encode()).hexdigest()
    with closing(connect(root)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT * FROM research_jobs WHERE owner=? AND request_key=?', (owner,key)).fetchone()
        if old:
            if old['fingerprint'] != fingerprint: raise ValueError('Request identity already used for different content')
            return old['id']
        if db.execute("SELECT count(*) FROM research_jobs WHERE status IN ('queued','running','needs_review')").fetchone()[0] >= 8:
            raise ValueError('Research queue full; retry later')
        jid = secrets.token_hex(16); now = time.time()
        db.execute('INSERT INTO research_jobs(id,owner,request_key,fingerprint,question,mode,status,stage,created,updated,result) VALUES (?,?,?,?,?,?,?,?,?,?,NULL)',
                   (jid,owner,key,fingerprint,question,mode,'queued',STAGES['queued'],now,now))
        db.execute('UPDATE research_jobs SET ready_at=? WHERE id=?',(now,jid))
        db.execute('INSERT INTO research_events(job,stage,status,created) VALUES (?,?,?,?)',(jid,STAGES['queued'],'queued',now))
        return jid


def get(root, owner, jid):
    with closing(connect(root)) as db:
        row = db.execute('SELECT * FROM research_jobs WHERE owner=? AND id=?',(owner,jid)).fetchone()
        if not row:raise KeyError('Research not found')
        events=[dict(e) for e in db.execute('SELECT sequence,stage,status,created FROM research_events WHERE job=? ORDER BY sequence DESC LIMIT 64',(jid,))][::-1]
    if not row: raise KeyError('Research not found')
    return {**{k: (json.loads(row[k]) if row[k] and k == 'result' else row[k])
            for k in ('id','status','stage','created','updated','ready_at','result')},'events':events}


def active(root):
    if not (Path(root)/'research.sqlite3').exists(): return []
    with closing(connect(root)) as db:
        return [dict(r) for r in db.execute("SELECT * FROM research_jobs WHERE status IN ('queued','running','needs_review','cancelled') ORDER BY created")]


def review_queries(root,owner,jid,decision,proof=''):
    if decision not in ('approve','reject'):raise ValueError('Invalid query review decision')
    with closing(connect(root)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM research_jobs WHERE id=? AND owner=?',(jid,owner)).fetchone()
        if not row:raise KeyError('Research not found')
        if row['status']!='needs_review':raise ValueError('This query review is no longer pending')
        payload=json.loads(row['result']);review=payload['review']
        digest=hashlib.sha256(json.dumps([owner,jid,review['queries']],ensure_ascii=False).encode()).hexdigest()
        if digest!=review['digest'] or payload.get('checkpoint',{}).get('queries')!=review['queries']:raise ValueError('Query review changed')
        if decision=='approve':
            if review['expires']<time.time():raise ValueError('Query review expired; submit a new question')
            if not isinstance(proof,str) or len(proof)!=12 or proof!=digest[:12]:raise ValueError('Approve the exact query preview shown in chat')
            payload['user_approved']=True;status='queued';stage='Queries approved by you; waiting for the shared processing slot'
        else:status='cancelled';stage='Public searches rejected by you; nothing sent'
        db.execute('UPDATE research_jobs SET status=?,stage=?,updated=?,ready_at=?,result=? WHERE id=?',
            (status,stage,time.time(),time.time(),json.dumps(payload),jid))
        db.execute('INSERT INTO research_events(job,stage,status,created) VALUES (?,?,?,?)',(jid,stage,status,time.time()))
    return get(root,owner,jid)


def cancel(root, owner, jid):
    with closing(connect(root)) as db, db:
        row = db.execute('SELECT status FROM research_jobs WHERE id=? AND owner=?',(jid,owner)).fetchone()
        if not row: raise KeyError('Research not found')
        if row['status'] == 'cancelled': return
        if row['status'] != 'queued': raise ValueError('Research already started; cancellation refused')
        db.execute("UPDATE research_jobs SET status='cancelled',stage='Cancelled before processing',updated=? WHERE id=?",(time.time(),jid))


def update(root, jid, stage, status='running', result=None):
    with closing(connect(root)) as db, db:
        previous=db.execute('SELECT stage,status FROM research_jobs WHERE id=?',(jid,)).fetchone()
        if previous and (previous['stage']!=stage or previous['status']!=status):
            db.execute('INSERT INTO research_events(job,stage,status,created) VALUES (?,?,?,?)',(jid,stage,status,time.time()))
        db.execute('UPDATE research_jobs SET stage=?,status=?,updated=?,result=? WHERE id=?',
                   (stage,status,time.time(),json.dumps(result) if result else None,jid))


def waiting(root, detail):
    with closing(connect(root)) as db, db:
        for r in db.execute("SELECT id FROM research_jobs WHERE status='queued' AND stage!=?",(detail,)).fetchall():
            db.execute('INSERT INTO research_events(job,stage,status,created) VALUES (?,?,?,?)',(r['id'],detail,'queued',time.time()))
        db.execute("UPDATE research_jobs SET stage=?,updated=? WHERE status='queued' AND stage!=?",
                   (detail,time.time(),detail))


def busy_reason(root):
    path=Path(root)/'jobs.sqlite3'
    if path.exists():
        try:
            with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
                row=db.execute("SELECT state,detail FROM jobs WHERE state IN ('transcribing','analyzing') LIMIT 1").fetchone()
            if row:
                action='audio speaker identification on CPU' if str(row[1]).startswith('Identifying speakers') else 'audio transcription' if row[0]=='transcribing' else 'audio analysis'
                return 'Waiting for shared processing slot: '+action+' is running'
        except sqlite3.Error:pass
    return 'Waiting for shared processing slot: another protected workload is running'


def validate_answer(value, evidence):
    # Structured output prevents fabricated URLs, HTML or model-authored citations.
    ids = {s['id'] for s in evidence}
    if not isinstance(value, dict) or set(value) != {'findings','uncertainties'}: raise ValueError('Invalid answer')
    if not isinstance(value['findings'], list) or len(value['findings']) > 10: raise ValueError('Invalid findings')
    for row in value['findings']:
        if not isinstance(row, dict) or set(row) != {'text','sources','type'}: raise ValueError('Invalid finding')
        if row['type'] not in ('internal','public','inference'): raise ValueError('Invalid evidence type')
        if not isinstance(row['text'],str) or not 1 <= len(row['text']) <= 1800: raise ValueError('Invalid claim')
        refs = row['sources']
        if not isinstance(refs,list) or not refs or any(not isinstance(r,str) or r not in ids for r in refs): raise ValueError('Unresolved citation')
        if row['type']=='internal' and any(not r.startswith('K') for r in refs): raise ValueError('Internal citation mismatch')
        if row['type']=='public' and any(not r.startswith('W') for r in refs): raise ValueError('Public citation mismatch')
    if not isinstance(value['uncertainties'],str) or len(value['uncertainties']) > 2000: raise ValueError('Invalid uncertainty')
    return value


def run(root, row, model, knowledge, web, clock=time.monotonic):
    deadline = clock()+600; warnings = []; evidence = []
    web.deadline = deadline
    web.job_id=row['id']
    saved=json.loads(row['result']) if row.get('result') else {}
    approved=saved.get('checkpoint') if saved.get('user_approved') is True else None
    if approved:
        expected=hashlib.sha256(json.dumps([row['owner'],row['id'],approved['queries']],ensure_ascii=False).encode()).hexdigest()
        if expected!=saved['review']['digest'] or approved['queries']!=saved['review']['queries']:
            raise PrivacyBlocked('Approved queries changed')
    def infer(task, payload):
        payload['current_date']=datetime.now(ZoneInfo(os.environ.get('RESEARCH_TIMEZONE','Europe/Amsterdam'))).date().isoformat()
        payload['_budget_seconds'] = deadline-clock()
        return model(task,payload)
    def stage(name):
        if clock() >= deadline: raise TimeoutError('Research time budget exhausted')
        update(root,row['id'],STAGES[name])
    stage('planning')
    identifiers=[]
    if row['mode']!='knowledge':
        stage('privacy')
        if hasattr(knowledge,'identifiers'):
            try:identifiers=knowledge.identifiers(row['owner'])
            except Exception:raise PrivacyBlocked('Local privacy index unavailable') from None
    sensitive=private_intent(row['question'],identifiers)
    if approved:routing=dict(approved['routing'])
    elif row['mode']=='knowledge':routing={'knowledge':True,'web':False}
    elif row['mode']=='web':routing={'knowledge':False,'web':True}
    else:
        stage('planning')
        routing=route(infer('route',{'question':row['question']}))
        if sensitive:routing['knowledge']=True
        if not routing['knowledge'] and not routing['web']:routing['web']=True
    private=[]
    if routing['knowledge']:
        stage('knowledge');private=knowledge(row['owner'],row['question'])
        evidence.extend(private)
        if not private:warnings.append('No matching indexed approved Knowledge found; private facts cannot be established.')
    queries=[]
    if routing['web']:
        guard=Guard(row['question'],private,identifiers,sensitive=sensitive)
        try:
            if approved:
                brief=approved['brief'];proposed=approved['queries']
                queries=guard.approve(proposed,{'decision':'safe'},user_approved=True)
            else:
                brief=None
            if not approved and (guard.sensitive or len(row['question'])>600):
                stage('abstracting')
                material=row['question']+' '+' '.join(s['text'] for s in private[:3])
                forbidden=sorted((name for name in guard.identifiers if contains(normalized(material),name)),
                    key=lambda name:(not contains(normalized(row['question']),name),-len(name)))[:80]
                abstract=infer('abstract',{'question':row['question'],'private_evidence':[s['text'][:1800] for s in private[:3]],'private_identifiers':forbidden})
                if not isinstance(abstract,dict) or set(abstract)!={'brief'}:raise PrivacyBlocked('Invalid public brief')
                brief=guard.check(abstract['brief'],allow_identifiers=True)
            elif not approved:brief=guard.check(row['question'],allow_identifiers=True)
            if not approved:
                stage('planning')
                proposed=plan(infer('plan',{'public_brief':brief}))
                for q in proposed:guard.check(q,allow_identifiers=True)
                stage('privacy')
                verdict=infer('privacy',{'queries':proposed,'public_brief':brief,
                    'original_request':row['question'],'private_request':guard.sensitive,
                    'private_evidence':[s['text'][:1200] for s in private[:3]]})
                queries=guard.approve(proposed,verdict)
        except QueryReviewRequired as request:
            request.checkpoint={'routing':routing,'brief':brief,'queries':request.queries}
            raise
        except PrivacyBlocked as exc:
            from research_web import audit
            audit('privacy_block',job=row['id'],category=str(exc),policy='general-0.2')
            if not evidence:raise
            warnings.append('Public search was stopped by the local privacy check. Only approved private evidence is used; rephrase the public portion without private identifiers to retry.')
    seen=set();search_calls=0
    for query in queries[:3]:
        if search_calls>=3:
            warnings.append('The public-search request limit was reached; some planned queries were not run.');break
        urls=[]
        for attempt in range(2):
            if search_calls>=3:break
            stage('searching');search_calls+=1
            try:
                urls=web.search(query)
                if getattr(web,'last_warning',None):warnings.append(web.last_warning)
            except Exception:warnings.append('A public search failed or timed out; no substitute source was invented.')
            if urls:break
            if attempt==0 and search_calls<3:
                stage('search_wait');time.sleep(min(2,max(0,deadline-clock())))
        for url in urls[:2]:
            if url in seen or len(seen)>=6:continue
            seen.add(url);stage('reading')
            try:text=web.read(url)
            except Exception:
                warnings.append('A discovered public page was unavailable, oversized or blocked by source policy.');continue
            if text:
                meta=getattr(web,'source_meta',lambda u:{})(url)
                if meta.get('partial'):warnings.append('A public page exceeded the read limit; only a bounded excerpt was used.')
                evidence.append({'kind':'web','url':url,'title':str(meta.get('title') or urlsplit_host(url))[:200],
                    'text':text[:4500],'retrieved_at':time.time(),
                    'excerpt_limited':bool(meta.get('partial')),
                    'recipe':bool(meta.get('recipe')),
                    'recipe_complete':bool(meta.get('recipe_complete')),
                    'date':'Publication date unverified'})
    routing={**routing,'queries':[q.text for q in queries]}
    # Use one complete recipe; mixing recipes can silently change quantities/timings.
    recipes=[s for s in evidence if s.get('recipe')]
    if recipes and answer_style(row['question'])=='instructions':
        chosen=max(recipes,key=lambda s:(s.get('recipe_complete',False),len(s['text'])))
        evidence=[s for s in evidence if s['kind']=='knowledge']+[chosen]
        if not chosen.get('recipe_complete'):warnings.append('No complete structured recipe fit the source limit; any missing steps must remain explicit.')
    # Bound total evidence by characters before heavy synthesis calls.
    remaining = 16000;recipe_taken=False
    for s in evidence:
        size=6000 if s.get('recipe') and not recipe_taken else 1800
        if s.get('recipe'):recipe_taken=True
        s['text'] = s['text'][:min(size,remaining)]
        remaining -= len(s['text'])
    evidence = [s for s in evidence if s['text']]
    counts = {'knowledge':0,'web':0}
    for s in evidence:
        counts[s['kind']] += 1; s['id'] = ('K' if s['kind']=='knowledge' else 'W')+str(counts[s['kind']])
    if not evidence: raise NoEvidence('No usable evidence; research stopped without inventing an answer')
    domains = {urlsplit_host(s['url']) for s in evidence if s['kind']=='web'}
    if queries and len(domains)<2:
        warnings.append('Fewer than two independent public domains were available; public corroboration is limited.')
    stage('comparing')
    comparison = infer('compare', {'question':row['question'], 'evidence':evidence})
    if recipes and isinstance(comparison,dict) and isinstance(comparison.get('steps'),list):
        comparison={**comparison,'steps':[{**s,'instruction':str(s.get('instruction',''))[:160]} for s in comparison['steps']]}
    stage('drafting')
    answer = validate_answer(infer('draft', {'question':row['question'], 'evidence':evidence,
        'comparison':json.dumps(comparison)[:4000]}), evidence)
    if answer_style(row['question']) in ('dates','person'):
        stage('verifying')
        answer=validate_answer(infer('verify',{'question':row['question'],'evidence':evidence,'draft':answer}),evidence)
    if clock() >= deadline: raise TimeoutError('Research time budget exhausted')
    return {'answer':answer,'sources':[{k:v for k,v in s.items() if k!='text'} for s in evidence],
            'warnings':list(dict.fromkeys(warnings)), 'plan':routing,
            'query_review':{'user_approved':bool(approved),'digest':saved.get('review',{}).get('digest') if approved else None},
            'limits':'One planning pass; at most 3 searches and 6 pages. Citations are structurally checked; claims require human review.'}


def urlsplit_host(url):
    from urllib.parse import urlsplit
    return urlsplit(url).hostname


class NoEvidence(ValueError):
    pass




def tick(root, model, knowledge, web):
    with closing(connect(root)) as db, db:
        db.execute("UPDATE research_jobs SET status='failed',stage='Query review expired; no public search was sent',updated=? WHERE status='needs_review' AND updated<?",(time.time(),time.time()-3600))
        db.execute("UPDATE research_jobs SET status='failed',stage='Queue wait timed out',updated=? WHERE status='queued' AND ready_at<?",(time.time(),time.time()-1800))
    # Claim only while holding the SAME lock used by Audio/Notes/ingestion.
    heavy_root=os.environ.get('RESEARCH_HEAVY_ROOT',root)
    with heavy_gate.slot(heavy_root) as acquired:
        if not acquired:
            waiting(root,busy_reason(heavy_root)); return False
        from traffic_control import memory
        available = memory()['available_mb']
        if available is not None and available < 8192:
            waiting(root,'Waiting for memory: less than 8 GiB is available'); return False
        with closing(connect(root)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM research_jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if not row: return False
            if time.time()-row['ready_at'] > 1800:
                db.execute("UPDATE research_jobs SET status='failed',stage='Queue wait timed out',updated=? WHERE id=?",(time.time(),row['id'])); return True
            db.execute("UPDATE research_jobs SET status='running',updated=? WHERE id=?",(time.time(),row['id']))
            row = dict(row)
        try:
            result = run(root,row,model,knowledge,web)
            update(root,row['id'],'Research completed; review evidence and uncertainty','completed',result)
        except TimeoutError:
            update(root,row['id'],'Research timed out; submit a new request to retry','failed')
        except QueryReviewRequired as request:
            digest=hashlib.sha256(json.dumps([row['owner'],row['id'],request.queries],ensure_ascii=False).encode()).hexdigest()
            payload={'review':{'queries':request.queries,'reason':request.reason,'digest':digest,'expires':time.time()+3600},
                     'checkpoint':request.checkpoint,'user_approved':False}
            update(root,row['id'],'Waiting for your decision: are these exact proposed public queries safe to send?','needs_review',payload)
        except NoEvidence:
            update(root,row['id'],'Research failed: no usable evidence was retrieved. Search, source access or matching approved Knowledge was unavailable; no answer published','failed')
        except PrivacyBlocked:
            update(root,row['id'],'Privacy check stopped public search. No query was sent. Rephrase the question as a public research question without private names, quotations or sensitive details.','failed')
        except Exception as exc:
            # Do not expose provider responses, private prompts, credentials or raw exceptions.
            import traceback
            safe={'Invalid answer','Invalid findings','Invalid finding','Invalid evidence type','Invalid claim',
                  'Unresolved citation','Internal citation mismatch','Public citation mismatch','Invalid uncertainty',
                  'Invalid research plan','Invalid research routing','Unsupported public topic; no search was sent'}
            diagnostic={'job':row['id'],'category':type(exc).__name__,
                        'validation':str(exc) if str(exc) in safe else None,
                        'frames':[{'function':f.name,'line':f.lineno} for f in traceback.extract_tb(exc.__traceback__)]}
            with (Path(root)/'research-errors.jsonl').open('a',encoding='utf-8') as log:log.write(json.dumps(diagnostic)+'\n')
            update(root,row['id'],'Research failed: evidence, configuration or model output unavailable; no answer published','failed')
        return True
