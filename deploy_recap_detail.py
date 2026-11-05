"""Guarded code-only deployment/rollback; never restores live databases."""
import argparse,datetime,hashlib,json,os,shutil,signal,sqlite3,subprocess,time,urllib.request
from contextlib import ExitStack
from pathlib import Path
BASE=Path.home()/'ai-platform';ROOT=BASE/'meetings';TARGET=BASE/'transcription/meeting-worker-2.3'
FILES=['meeting_dashboard.py','meeting_recovery.py','meeting_draft.py','meeting_review.py','dashboard.html','dashboard.js','dashboard.css','traffic_control.py']
BEFORE={
'meeting_recovery.py':'71239b2d575b42670df71e70ea141285447309e64858f1637b9cc050cd066a41',
'meeting_dashboard.py':'9f9aaa746b1b01e82a00210834d90fa9f6676f955d328b53e845ef0b67315a67',
'meeting_draft.py':'8b1aa80cf77dfb97391dad3a1c9d489676c67738b6e7a1d0ff66d5f95ca44883',
'meeting_review.py':'8b984012bdb9b4fcb3e01ad8db4cc8938d6221818ff40569b962da194935845b',
'dashboard.html':'1c1f78528757f3f3acdd10c6ffe9d38f546bf91cd5d427772f7c58dff6298bf0',
'dashboard.js':'e528f7e5e9e17e8b8db53010c17656803fd304a702bd84ee5471f44323adce65',
'dashboard.css':'a3a6cb3b361a83dbe6d4c1f99af6bdca125638f6819d930b345d142c35d0a74d',
 'traffic_control.py':'7f93d897187b5222b228da3634b0bf91a9cdabc8fbcae7f6dd43c6d83d266275'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def idle(dbs):
 for name,db in dbs.items():
  if name=='jobs.sqlite3':
   if db.execute("select count(*) from jobs where state in ('queued','transcribing','analyzing','uploading')").fetchone()[0]:raise RuntimeError('User audio processing is active; no change made')
  else:
   for table in ['tasks','notes_tasks','research_jobs']:
    if db.execute("select 1 from sqlite_master where type='table' and name=?",(table,)).fetchone():
     if db.execute('select count(*) from '+table+" where status in ('queued','running')").fetchone()[0]:raise RuntimeError('User review/Research processing is active; no change made')
def restart():
 result=subprocess.run(['systemctl','--no-ask-password','restart','minisforum-meetings.service'],capture_output=True)
 if result.returncode:
  values=subprocess.check_output(['systemctl','show','minisforum-meetings.service','-p','MainPID','-p','Restart','-p','User'],text=True)
  props=dict(line.split('=',1) for line in values.splitlines() if '=' in line);pid=int(props['MainPID'])
  import getpass
  assert props['Restart']=='on-failure' and props['User']==getpass.getuser() and pid>1
  proc=Path('/proc')/str(pid)
  assert proc.stat().st_uid==os.getuid() and str(TARGET/'meeting_worker.py').encode() in (proc/'cmdline').read_bytes().split(b'\0')
  os.kill(pid,signal.SIGKILL)
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--rollback',type=Path);args=parser.parse_args();os.umask(0o077)
 source=Path(__file__).resolve().parent
 if args.rollback:
  source=args.rollback.resolve();assert source.is_relative_to((BASE/'backups').resolve())
  expected=json.loads((source/'manifest.json').read_text())['after']
 else:expected=BEFORE
 import fcntl
 with ExitStack() as stack:
  lock=stack.enter_context((ROOT/'.smartinis-heavy.lock').open('a+b'));fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  dbs={}
  for name in ['jobs.sqlite3','reviews.sqlite3','research.sqlite3']:
   if not (ROOT/name).exists():continue
   db=sqlite3.connect(ROOT/name,timeout=3);stack.callback(db.close);db.execute('BEGIN IMMEDIATE');stack.callback(db.rollback);dbs[name]=db
  idle(dbs)
  for name in FILES:
   assert sha(TARGET/name)==expected[name],'Production changed: '+name
   assert (source/name).is_file() and not (source/name).is_symlink()
  backup=BASE/'backups'/('audio-recap-detail-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S'));backup.mkdir(mode=0o700,parents=True)
  for name in FILES:shutil.copy2(TARGET/name,backup/name)
  for name in dbs:
   with sqlite3.connect(ROOT/name) as src,sqlite3.connect(backup/name) as dst:src.backup(dst)
  manifest={'before':{n:sha(TARGET/n) for n in FILES},'after':{n:sha(source/n) for n in FILES},'code_only_rollback':True}
  (backup/'manifest.json').write_text(json.dumps(manifest,indent=2))
  for name in FILES:
   temporary=TARGET/(name+'.recap-update');shutil.copy2(source/name,temporary);os.replace(temporary,TARGET/name)
  restart()
 for _ in range(45):
  try:
   with urllib.request.urlopen('http://127.0.0.1:8765/health',timeout=2) as response:value=json.load(response)
   if value.get('worker_alive'):
    print(json.dumps({'healthy':True,'backup':str(backup),'files':FILES}));return
  except OSError:pass
  time.sleep(1)
 raise RuntimeError('Health check failed; code-only backup available at '+str(backup))
if __name__=='__main__':main()


