"""Observe durable processing queues; cancel only unclaimed work, owner scoped."""
import json
import os
from pathlib import Path
import time
import meeting_review as review

VERSION='0.1.0'

def memory():
    try:
        values={k:int(v.split()[0]) for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())}
        return {'available_mb':values['MemAvailable']//1024,'total_mb':values['MemTotal']//1024}
    except (OSError,ValueError,KeyError):return {'available_mb':None,'total_mb':None}

def slot_busy(root):
    try:
        inode=str((Path(root)/'.smartinis-heavy.lock').stat().st_ino)
        return any(len(parts:=line.split())>5 and parts[5].endswith(':'+inode) for line in Path('/proc/locks').read_text().splitlines())
    except OSError:return None

def snapshot(worker,owner):
    rows=[]
    with worker.connect() as db:
        for r in db.execute("SELECT id,owner,state,detail,percent,created,updated,filename,folder FROM jobs WHERE state IN ('queued','transcribing','analyzing','cancelled')"):
            r=dict(r);title=r['filename'] or 'Audio recording'
            if r['owner']==owner and r['folder']:
                try:title=json.loads((Path(r['folder'])/'meeting_metadata.json').read_text()).get('meeting_title') or title
                except (OSError,ValueError):pass
            rows.append(dict(id=r['id'],key=r['id'],kind='audio',owner=r['owner'],title=title,
                status='running' if r['state'] in ('transcribing','analyzing') else r['state'],stage=r['detail'] or 'Audio transcription',percent=r['percent'],created=r['created'],activity=r['updated']))
    with review.connection(worker.ROOT) as db:
        for r in db.execute("SELECT t.key,t.id,t.status,t.created,m.owner,m.folder FROM tasks t JOIN meetings m ON m.id=t.id WHERE t.status IN ('queued','running','cancelled')"):
            r=dict(r);title='Audio recap'
            if r['owner']==owner:
                try:title=json.loads((Path(r['folder'])/'meeting_metadata.json').read_text()).get('meeting_title') or title
                except (OSError,ValueError):pass
            stage='Recap generation'
            if r['owner']==owner and r['status']=='queued':
                try:
                    waiting=json.loads((Path(r['folder'])/'review-work'/r['key']/'resource-wait.json').read_text())
                    if waiting.get('waiting'):stage=str(waiting.get('message') or 'Waiting for safe RAM headroom')[:160]
                except (OSError,ValueError,TypeError):pass
            if r['owner']==owner and r['status']=='running':
                path=Path(r['folder'])/'review-work'/r['key']/'events.jsonl'
                try:
                    with path.open('rb') as stream:
                        stream.seek(max(0,path.stat().st_size-8000))
                        for line in stream.read().decode('utf-8',errors='replace').splitlines():
                            try:
                                event=json.loads(line)
                                if event.get('stage'):stage=str(event['stage'])[:160]
                            except ValueError:pass
                except OSError:pass
            rows.append(dict(id=r['id'],key=r['key'],kind='meeting-recap',owner=r['owner'],title=title,status=r['status'],stage=stage,percent=None,created=r['created'],activity=None))
        if os.environ.get('SMARTINIS_NOTES_ENABLED')=='1' and db.execute("SELECT 1 FROM sqlite_master WHERE name='notes_tasks'").fetchone():
            for r in db.execute("SELECT t.key,t.id,t.status,t.stage,t.created,j.owner,j.title FROM notes_tasks t JOIN notes_jobs j ON j.id=t.id WHERE t.status IN ('queued','running','cancelled')"):
                r=dict(r);rows.append(dict(id=r['id'],key=r['key'],kind='notes',owner=r['owner'],title=r['title'],status=r['status'],stage='Notes '+r['stage'],percent=None,created=r['created'],activity=None))
    if os.environ.get('SMARTINIS_RESEARCH_ENABLED')=='1':
        import research_jobs
        for job in research_jobs.active(worker.ROOT):
            rows.append(dict(id=job['id'],key=job['id'],kind='research',owner=job['owner'],title='Private research request',status=job['status'],stage=job['stage'],percent=None,created=job['created'],activity=job['updated']))
    queued=sorted((r for r in rows if r['status']=='queued'),key=lambda r:(r['created'],['audio','meeting-recap','notes','research'].index(r['kind']),r['key']))
    positions={(r['kind'],r['key']):i+1 for i,r in enumerate(queued)}
    resources=memory();occupied=slot_busy(worker.ROOT)
    running=any(r['status']=='running' for r in rows)
    minimum=int(os.environ.get('NOTES_MIN_AVAILABLE_MB','8192')) if os.environ.get('SMARTINIS_NOTES_ENABLED')=='1' else 8192 if os.environ.get('SMARTINIS_RESEARCH_ENABLED')=='1' else None
    for r in rows:
        r['position']=positions.get((r['kind'],r['key']))
        row_minimum=minimum
        if r['kind']=='meeting-recap' and os.environ.get('SMARTINIS_RECAP_RAM_GUARD','1')!='0':
            row_minimum=int(os.environ.get('RECAP_RAM_HEADROOM_MB','2048'))
        r['reason']=('Waiting for the running job to finish' if running else 'Processing slot is busy (possibly ingestion)' if occupied else 'Waiting for enough available memory' if row_minimum and resources['available_mb'] is not None and resources['available_mb']<row_minimum else 'Waiting for the worker to claim this job') if r['status']=='queued' else ''
    visible=[{k:v for k,v in r.items() if k!='owner'} for r in rows if r['owner']==owner]
    visible.sort(key=lambda r:({'running':0,'queued':1,'needs_review':2,'cancelled':3}[r['status']],r['created']))
    return {'jobs':visible,'server_time':time.time(),'resources':resources,'slot_busy':occupied,'version':VERSION}

def audit(db,owner,kind,key):
    db.execute('CREATE TABLE IF NOT EXISTS traffic_events (sequence INTEGER PRIMARY KEY,owner TEXT NOT NULL,kind TEXT NOT NULL,task TEXT NOT NULL,action TEXT NOT NULL,created REAL NOT NULL)')
    db.execute('INSERT INTO traffic_events(owner,kind,task,action,created) VALUES (?,?,?,?,?)',(owner,kind,key,'cancel-waiting',time.time()))

def cancel(worker,owner,kind,key):
    if kind=='research':
        if os.environ.get('SMARTINIS_RESEARCH_ENABLED')!='1':raise KeyError('Job not found')
        import research_jobs
        return research_jobs.cancel(worker.ROOT,owner,key)
    if kind=='audio':
        with worker.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT state FROM jobs WHERE id=? AND owner=?',(key,owner)).fetchone()
            if not row:raise KeyError('Job not found')
            if row['state']=='cancelled':return
            if row['state']!='queued':raise ValueError('This job has already started or finished. Running jobs cannot be cancelled.')
            db.execute("UPDATE jobs SET state='cancelled',detail='Cancelled before processing; source retained',percent=NULL,updated=? WHERE id=? AND owner=? AND state='queued'",(time.time(),key,owner))
            audit(db,owner,kind,key)
        return
    if kind not in ('meeting-recap','notes'):raise KeyError('Job not found')
    if kind=='notes' and os.environ.get('SMARTINIS_NOTES_ENABLED')!='1':raise KeyError('Job not found')
    table='tasks' if kind=='meeting-recap' else 'notes_tasks';jobs='meetings' if kind=='meeting-recap' else 'notes_jobs'
    with review.connection(worker.ROOT) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT t.*,j.owner FROM '+table+' t JOIN '+jobs+' j ON j.id=t.id WHERE t.key=? AND j.owner=?',(key,owner)).fetchone()
        if not row:raise KeyError('Job not found')
        if row['status']=='cancelled':return
        if row['status']!='queued':raise ValueError('This job has already started or finished. Running jobs cannot be cancelled.')
        db.execute('UPDATE '+table+" SET status='cancelled' WHERE key=? AND status='queued'",(key,))
        if kind=='meeting-recap':
            job=db.execute('SELECT * FROM meetings WHERE id=?',(row['id'],)).fetchone()
            if job['pending']==key:
                db.execute('UPDATE meetings SET pending=NULL,error=NULL WHERE id=?',(row['id'],))
                state=review._state(job['folder']);state.update(pending=None,error=None,review_state='draft');review._save_state(job['folder'],state)
        else:
            # Keep all source/revision/approval data. No failed/retry auto-resume semantics.
            db.execute("UPDATE notes_jobs SET state='cancelled',updated=? WHERE id=? AND state=?",(time.time(),row['id'],row['stage']+'-queued'))
        audit(db,owner,kind,key)
