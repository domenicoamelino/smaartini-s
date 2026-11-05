"""Idle, hash-guarded code-only install/rollback, including one new module."""
import argparse
from contextlib import ExitStack
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
import urllib.request
import uuid
import deploy_recap_detail as previous

BASE=Path.home()/'ai-platform';ROOT=BASE/'meetings';TARGET=BASE/'transcription/meeting-worker-2.3'
SOURCE=Path(__file__).resolve().parent
FILES=['recap_resources.py','meeting_draft.py','meeting_review.py','meeting_report.py','traffic_control.py','notes_dispatch.py']
BEFORE={'recap_resources.py':None,
        'meeting_draft.py':'18c5846524742e672c8de6cfb54e30c89fbe03a65d9d5e83244fb137d401c74b',
        'meeting_review.py':'9c797624cf160180efb61e1911c2b4d9608a937d84621155cb45c155d86d9b45',
        'meeting_report.py':'c269f537223304e7fabca9398ad118ad3cd0caf2dec8c0beb5905274246367af',
        'traffic_control.py':'96aa244c90409ace596b6396924e45b3b2614b69f1ba70a21864fc60b2a2c439',
        'notes_dispatch.py':'fce3326232770ff9f7816f4e4284cd7b223d66e86cb99289f2da661b043c0db6'}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
def restart():previous.restart()
def healthy():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8765/health',timeout=2) as response:return bool(json.load(response).get('worker_alive'))
    except OSError:return False

def apply(rollback=None):
    import fcntl
    os.umask(0o077)
    if rollback:
        source=Path(rollback).resolve();assert source.is_relative_to((BASE/'backups').resolve())
        manifest=json.loads((source/'manifest.json').read_text());expected=manifest['after'];desired=manifest['before']
    else:
        source=SOURCE;expected=BEFORE;desired={name:sha(source/name) for name in FILES}
        assert all(desired.values())
    with ExitStack() as stack:
        lock=stack.enter_context((ROOT/'.smartinis-heavy.lock').open('a+b'));fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        dbs={}
        for name in ['jobs.sqlite3','reviews.sqlite3','research.sqlite3']:
            if not (ROOT/name).exists():continue
            db=sqlite3.connect(ROOT/name,timeout=3);stack.callback(db.close);db.execute('BEGIN IMMEDIATE');stack.callback(db.rollback);dbs[name]=db
        previous.idle(dbs)
        for name in FILES:
            path=TARGET/name;assert path.resolve().is_relative_to(TARGET.resolve()) and not path.is_symlink()
            assert sha(path)==expected[name],'Production changed: '+name
            if desired[name] is not None:
                assert not (source/name).is_symlink() and sha(source/name)==desired[name],'Source changed: '+name
        before={name:sha(TARGET/name) for name in FILES}
        stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')
        backup=BASE/'backups'/('audio-recap-ram-'+stamp+'-'+uuid.uuid4().hex[:8]);backup.mkdir(mode=0o700,parents=True)
        for name in FILES:
            if before[name] is not None:shutil.copy2(TARGET/name,backup/name)
        for name in dbs:
            with sqlite3.connect(ROOT/name) as src,sqlite3.connect(backup/name) as dst:src.backup(dst)
        (backup/'manifest.json').write_text(json.dumps({'before':before,'after':desired,'code_only_rollback':True},indent=2))
        for name in FILES:
            if desired[name] is None:continue
            path=TARGET/name;temporary=path.with_name(path.name+'.ram-update');shutil.copy2(source/name,temporary);os.replace(temporary,path)
        for name in FILES:
            if desired[name] is None:(TARGET/name).unlink()
        restart()
    for _ in range(45):
        if healthy():return {'healthy':True,'backup':str(backup),'files':FILES,'sha256':desired}
        time.sleep(1)
    raise RuntimeError('Health check failed; code-only backup: '+str(backup))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--rollback',type=Path)
    print(json.dumps(apply(parser.parse_args().rollback)))
