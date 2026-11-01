"""Private, idle-only SMARTINI recovery snapshot; never run restored services."""
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tarfile
import time

os.umask(0o077)
platform=Path.home()/'ai-platform'
plan=json.loads((platform/'experiments/notes-20261030/notes-deploy-plan.json').read_text())
root=Path(plan['root']);worker=Path(plan['worker']);ingestion=Path(plan['ingestion'])
destination=platform/'backups'/('offdevice-recovery-'+time.strftime('%Y%m%d-%H%M%S'))
destination.mkdir(mode=0o700)
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as handle:
        while block:=handle.read(1024*1024):h.update(block)
    return h.hexdigest()
def regular_files(directory):
    for p in directory.rglob('*'):
        if p.is_symlink():raise RuntimeError('Symlink source refused')
        if p.is_file() and '__pycache__' not in p.parts and not p.name.endswith(('-wal','-shm','.lock')) and p.name not in ('jobs.sqlite3','reviews.sqlite3'):
            yield p
manifest={'schema':'smartinis-recovery/1','created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'archive_root':str(root),'worker_root':str(worker),'ingestion_root':str(ingestion),'files':{},'databases':{},'scope':'SMARTINI sources/revisions/approvals/withdrawals/ledger/config/source; excludes Open WebUI volume, models and virtual environments'}
with ExitStack() as stack:
    for path in [ingestion/'ingestion.lock',root/'.smartinis-heavy.lock']:
        handle=stack.enter_context(path.open('a+b'));fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    # Reserved write locks briefly freeze review/queue changes; no live rows are changed.
    dbs={}
    for name in ['jobs.sqlite3','reviews.sqlite3']:
        db=sqlite3.connect(root/name,timeout=3);stack.callback(db.close);db.execute('BEGIN IMMEDIATE');stack.callback(db.rollback);dbs[name]=db
    assert dbs['jobs.sqlite3'].execute("SELECT count(*) FROM jobs WHERE state IN ('queued','transcribing','analyzing','uploading')").fetchone()[0]==0,'Audio work active; retry when idle'
    for table in ['tasks','notes_tasks']:
        assert dbs['reviews.sqlite3'].execute('SELECT count(*) FROM '+table+" WHERE status IN ('queued','running')").fetchone()[0]==0,'Review work active; retry when idle'
    for name in dbs:
        target=destination/name
        with sqlite3.connect((root/name).as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(target) as copy:
            source.backup(copy);assert copy.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            tables=[r[0] for r in copy.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            manifest['databases'][name]={t:copy.execute('SELECT count(*) FROM "'+t.replace('"','""')+'"').fetchone()[0] for t in tables}
        manifest['files']['databases/'+name]=sha(target)
    with tarfile.open(destination/'recovery.tar.gz','w:gz',compresslevel=1) as archive:
        for name in dbs:archive.add(destination/name,arcname='databases/'+name)
        for directory,prefix in [(root,'archive'),(worker,'worker'),(ingestion,'ingestion')]:
            for p in regular_files(directory):
                if prefix=='worker' and not (p.parent==worker or 'assets' in p.relative_to(worker).parts):continue
                relative=prefix+'/'+p.relative_to(directory).as_posix()
                manifest['files'][relative]=sha(p);archive.add(p,arcname=relative)
    (destination/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
record={'backup':str(destination),'bundle_sha256':sha(destination/'recovery.tar.gz'),'manifest_sha256':sha(destination/'MANIFEST.json'),'bundle_bytes':(destination/'recovery.tar.gz').stat().st_size,'file_count':len(manifest['files']),'live_rows_changed':False,'services_started_or_stopped':False}
(destination/'TRANSFER.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
