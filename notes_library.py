"""Owner-only Notes summaries for the shared recap dashboard. No processing/approval."""
import json
import os
from pathlib import Path
import meeting_review as review


def summaries(root,owner):
    allowed=os.environ.get('NOTES_ALLOWED_OWNERS','')
    if allowed and owner not in {x.strip() for x in allowed.split(',')}:return []
    with review.connection(root) as db:
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='notes_jobs'").fetchone()
        if not exists:return []
        jobs=[dict(r) for r in db.execute('SELECT * FROM notes_jobs WHERE owner=? ORDER BY updated DESC',(owner,))]
        approvals={(r['id'],r['revision']):json.loads(r['payload']) for r in db.execute(
            'SELECT a.* FROM notes_approvals a JOIN notes_jobs j ON j.id=a.id WHERE j.owner=?',(owner,))}
    ledger=Path(os.environ.get('MEETING_INGESTION_HOME',str(Path(root).parent/'ingestion')))/'state.json'
    try:entries=json.loads(ledger.read_text()).get('meetings',{})
    except (OSError,ValueError,TypeError):entries={}
    rows=[]
    for job in jobs:
        committed=entries.get('notes-'+job['id'][5:],{}).get('committed') or {}
        number=committed.get('approval_revision');approval=approvals.get((job['id'],number))
        indexed=number if (type(number) is int and number>0 and approval and committed.get('file_id') and
            committed.get('indexed_at') and committed.get('approval_sha256')==approval.get('knowledge_sha256')) else None
        state=job['state']
        if state=='cancelled':status='Waiting job cancelled'
        elif state=='failed':status='Notes generation needs attention'
        elif state.endswith(('-queued','-running')):status='Processing'
        elif state=='page-review':status='Transcription awaiting review'
        elif job['current']!=job['approved']:status='Ready for review'
        elif indexed==job['approved']:status='In knowledge base'
        else:status='Approved · awaiting ingestion'
        rows.append({'id':job['id'],'kind':'notes','title':job['title'],'meeting_date':job.get('notes_date') or '',
            'state':state,'status':status,'revision':job['current'] or None,'approved_revision':job['approved'],
            'indexed_revision':indexed,'updated':job['updated'],'created':job['created']})
    return rows
