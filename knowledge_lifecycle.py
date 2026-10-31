"""Durable owner-scoped Knowledge withdrawal. Sources and approvals are retained."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import time
from urllib.parse import quote

VERSION='0.1.0'

def connect(root):
    db=sqlite3.connect(Path(root)/'reviews.sqlite3',timeout=10)
    db.row_factory=sqlite3.Row
    return db

def init(db):
    db.execute('CREATE TABLE IF NOT EXISTS knowledge_lifecycle (source TEXT PRIMARY KEY, owner TEXT NOT NULL, status TEXT NOT NULL, generation INTEGER NOT NULL, updated REAL NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS knowledge_events (sequence INTEGER PRIMARY KEY, source TEXT NOT NULL, owner TEXT NOT NULL, action TEXT NOT NULL, generation INTEGER NOT NULL, created REAL NOT NULL)')

def all_states(root):
    path=Path(root)/'reviews.sqlite3'
    if not path.exists():return {}
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
        db.row_factory=sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='knowledge_lifecycle' AND type='table'").fetchone():return {}
        return {r['source']:dict(r) for r in db.execute('SELECT * FROM knowledge_lifecycle')}

def change(root,source,owner,action,generation,verify=None):
    if not source or Path(source).name!=source or not owner:raise ValueError('Invalid source identity')
    if action not in ('remove','restore') or type(generation) is not int:raise ValueError('Invalid Knowledge action')
    with closing(connect(root)) as db,db:
        init(db);db.execute('BEGIN IMMEDIATE')
        if verify is not None:verify(db)
        row=db.execute('SELECT * FROM knowledge_lifecycle WHERE source=?',(source,)).fetchone()
        if row and row['owner']!=owner:raise ValueError('Source not found')
        current=row['generation'] if row else 0
        if generation!=current:raise ValueError('Knowledge status changed. Refresh before retrying.')
        if action=='restore' and (not row or row['status']!='removed'):raise ValueError('Wait until removal is confirmed before restoring')
        if action=='remove' and row and row['status'] in ('pending','removed'):return dict(row)
        state='pending' if action=='remove' else 'active';current+=1;stamp=time.time()
        db.execute('INSERT OR REPLACE INTO knowledge_lifecycle VALUES (?,?,?,?,?)',(source,owner,state,current,stamp))
        db.execute('INSERT INTO knowledge_events(source,owner,action,generation,created) VALUES (?,?,?,?,?)',(source,owner,action,current,stamp))
        return {'source':source,'owner':owner,'status':state,'generation':current,'updated':stamp}

def finish(root,source,owner,generation):
    with closing(connect(root)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        changed=db.execute("UPDATE knowledge_lifecycle SET status='removed',updated=? WHERE source=? AND owner=? AND generation=? AND status='pending'",(time.time(),source,owner,generation)).rowcount
        if changed:db.execute('INSERT INTO knowledge_events(source,owner,action,generation,created) VALUES (?,?,?,?,?)',(source,owner,'removed',generation,time.time()))

def decorate(root,rows):
    states=all_states(root)
    for row in rows:
        state=states.get(row['knowledge_source'])
        if state and state['owner']!=row['knowledge_owner']:raise ValueError('Knowledge ownership mismatch')
        row['knowledge_generation']=state['generation'] if state else 0
        row['knowledge_status']=state['status'] if state else 'active'
        if state and state['status']!='active':
            row['status']='Removal queued' if state['status']=='pending' else 'Removed from Knowledge'
            if state['status']=='removed':row['indexed_revision']=None
        row.pop('knowledge_owner',None)
    return rows

def reconcile(client,config,state,remote,report,apply):
    """Detach only ledger-owned memberships; never delete a global uploaded file."""
    states=all_states(config['meetings_root'])
    blocked={key for key,value in states.items() if value['status']!='active'}
    pending=[(key,value) for key,value in states.items() if value['status']=='pending']
    if not pending:return blocked,remote
    kb=client.request('GET','/api/v1/knowledge/'+quote(config['collection_id'],safe=''))
    for key,value in pending:
        if kb.get('user_id')!=value['owner'] or kb.get('access_grants')!=[] or not kb.get('write_access'):
            raise ValueError('Removal requires the owner-matched private destination')
        entry=json.loads(json.dumps(state.data['meetings'].get(key,{})))
        records=[entry.get('committed') or {},entry.get('pending') or {}]+entry.get('history',[])
        ids={r['file_id'] for r in records if r.get('file_id')}
        others={r['file_id'] for k,e in state.data['meetings'].items() if k!=key for r in [e.get('committed') or {},e.get('pending') or {}]+e.get('history',[]) if r.get('file_id')}
        if ids & others:raise ValueError('Shared managed file identity; automatic removal refused')
        report['removal_planned']=report.get('removal_planned',0)+1
        if not apply:continue
        for fid in sorted(ids & set(remote)):
            try:client.remove(config['collection_id'],fid)
            except Exception:
                # Lost response may follow a successful detach. Membership is authoritative.
                if fid in {r['id'] for r in client.files(config['collection_id'])}:raise
            remote={r['id']:r for r in client.files(config['collection_id'])}
            if fid in remote:raise ValueError('Removal not confirmed; request remains queued')
        if ids & set(remote):raise ValueError('Managed membership remains; removal not confirmed')
        for name in ('committed','pending'):
            if entry.get(name):entry.setdefault('history',[]).append({**entry.pop(name),'withdrawn_at':time.time()})
        if entry:
            state.data['meetings'][key]=entry;state.save()
        finish(config['meetings_root'],key,value['owner'],value['generation'])
        report['removed']=report.get('removed',0)+1
        report['changes'].append({'meeting':key,'status':'removed','filename':'','revision':None})
    return blocked,remote
