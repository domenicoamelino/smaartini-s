#!/usr/bin/env python3
"""Deploy staged files on the existing server; preserve meeting content and secrets."""
import datetime,hashlib,json,os,pathlib,shutil,signal,sqlite3,subprocess,sys,tarfile,time,urllib.request

BASE=pathlib.Path.home()/'ai-platform'
SOURCE=pathlib.Path(__file__).resolve().parent/'ai-platform'
WORKER=BASE/'transcription/meeting-worker-2.3'
os.umask(0o077)

def command(*args,check=True):
    return subprocess.run(args,capture_output=True,text=True,check=check)

def idle():
    for file,query in [(BASE/'meetings/jobs.sqlite3',"SELECT count(*) FROM jobs WHERE state IN ('queued','transcribing','analyzing','uploading')"),
                       (BASE/'meetings/reviews.sqlite3',"SELECT count(*) FROM tasks WHERE status IN ('queued','running')")]:
        if file.exists():
            with sqlite3.connect(file) as c:
                if c.execute(query).fetchone()[0]:raise RuntimeError('A meeting job/revision is active; deploy after it finishes')

def restart_worker(expected_version='2.7.1'):
    result=command('systemctl','--no-ask-password','restart','minisforum-meetings.service',check=False)
    if result.returncode:
        # This system unit runs as this account and has Restart=on-failure.
        # No administrator password is needed to stop our own idle process.
        idle()
        props=command('systemctl','show','minisforum-meetings.service','-p','MainPID','-p','Restart','-p','User').stdout
        props=dict(line.split('=',1) for line in props.splitlines() if '=' in line)
        pid=int(props['MainPID'])
        if props['Restart']!='on-failure' or props['User']!=__import__('getpass').getuser() or pid<=1:
            raise RuntimeError('Worker restart policy/account could not be verified')
        proc=pathlib.Path('/proc')/str(pid)
        if proc.stat().st_uid!=os.getuid() or str(WORKER/'meeting_worker.py').encode() not in (proc/'cmdline').read_bytes().split(b'\0'):
            raise RuntimeError('Worker PID identity mismatch; no signal sent')
        os.kill(pid,signal.SIGKILL)
    for _ in range(40):
        time.sleep(1)
        try:
            with urllib.request.urlopen('http://127.0.0.1:8765/health',timeout=2) as response:info=json.load(response)
            if info.get('dashboard_version')==expected_version and info.get('worker_alive'):return
        except OSError:pass
    raise RuntimeError('Updated worker did not become healthy; use rollback.py')

def main():
    if not SOURCE.is_dir():raise RuntimeError('Extract the whole package; staged ai-platform directory is missing')
    idle()
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')
    backup=BASE/'backups'/('review-flow-2.7.1-'+stamp);backup.mkdir(parents=True,mode=0o700)
    inventory={}
    # Archive source/config/state before touching production. Audio and immutable review
    # directories are never modified by deployment and stay in the existing archive.
    with tarfile.open(backup/'private-rollback.tar.gz','w:gz') as archive:
        for relative in ['transcription/meeting-worker-2.3','ingestion','ingestion-monitor']:
            archive.add(BASE/relative,arcname=relative,filter=lambda item:None if '__pycache__' in pathlib.PurePosixPath(item.name).parts else item)
        units=pathlib.Path.home()/'.config/systemd/user'
        if units.exists():archive.add(units,arcname='systemd-user')
    for file in (BASE/'meetings').glob('*.sqlite3'):
        with sqlite3.connect(file) as src,sqlite3.connect(backup/file.name) as dst:src.backup(dst)
    for file in (BASE/'meetings').glob('processed-*/review.json'):
        target=backup/'review-states'/file.parent.name/'review.json';target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,target)
    sys.path.insert(0,str(BASE/'ingestion'))
    import ingest_meetings as ingestion
    cfg=ingestion.load_config(BASE/'ingestion/config.json')
    client=ingestion.Client(cfg['base_url'],ingestion.load_key(BASE/'ingestion/api-key.txt'))
    fid='minisforum_meeting_recap'
    function=client.request('GET','/api/v1/functions/id/'+fid)
    ingestion.save_json(backup/'openwebui-function.json',function)
    try:ingestion.save_json(backup/'openwebui-valves.json',client.request('GET','/api/v1/functions/id/'+fid+'/valves'))
    except ingestion.IngestionError:pass
    inventory['collection_members_before']=[row['id'] for row in client.files(cfg['collection_id'])]
    inventory['timer_active']=command('systemctl','--user','is-active','meeting-ingestion.timer',check=False).stdout.strip()=='active'
    ingestion.save_json(backup/'inventory.json',inventory)
    command('systemctl','--user','stop','meeting-ingestion.timer')
    command('systemctl','--user','stop','meeting-monitor.service',check=False)
    idle()
    for relative in ['transcription/meeting-worker-2.3','ingestion','ingestion-monitor']:
        src=SOURCE/relative;dest=BASE/relative
        for file in src.iterdir():
            if not file.is_file() or file.suffix not in ('.py','.html','.js','.css'):continue
            temporary=dest/(file.name+'.update');shutil.copy2(file,temporary);temporary.replace(dest/file.name)
    env=WORKER/'worker.env';text=env.read_text()
    values={'REPORT_MODEL':'gemma4:12b-it-q4_K_M','REVIEW_MODEL':'gemma4:12b-it-q4_K_M','WHISPER_MODEL':'turbo','REVIEW_CONTEXT':'32768'}
    lines=[line for line in text.splitlines() if line.partition('=')[0] not in values]
    lines.extend(key+'='+value for key,value in values.items())
    tmp=env.with_suffix('.env.update');tmp.write_text('\n'.join(lines)+'\n');tmp.chmod(0o600);tmp.replace(env)
    monitor=BASE/'ingestion-monitor/monitor.json'
    if not monitor.exists():
        prior=BASE/'backups/meeting-monitor-20261022-203549-257826/monitor.json'
        data=json.loads(prior.read_text())
        if len(data.get('password_hash',''))!=64 or len(data.get('password_salt',''))!=32:raise RuntimeError('Backed-up monitor configuration is invalid')
        shutil.copy2(prior,monitor);monitor.chmod(0o600)
    content=(WORKER/'openwebui_meeting_pipe.py').read_text()
    client.request('POST','/api/v1/functions/id/'+fid+'/update',{'id':fid,'name':function['name'],'content':content,'meta':function['meta']})
    updated=client.request('GET','/api/v1/functions/id/'+fid)
    if updated['content']!=content or updated['is_active']!=function['is_active']:raise RuntimeError('Installed Function verification failed')
    restart_worker()
    command('systemctl','--user','restart','meeting-monitor.service')
    if inventory['timer_active']:command('systemctl','--user','start','meeting-ingestion.timer')
    time.sleep(2)
    if command('systemctl','--user','is-active','meeting-monitor.service',check=False).stdout.strip()!='active':raise RuntimeError('Monitor dashboard did not recover')
    after=[row['id'] for row in client.files(cfg['collection_id'])]
    if sorted(after)!=sorted(inventory['collection_members_before']):raise RuntimeError('Knowledge collection unexpectedly changed during deploy')
    manifest={str(file.relative_to(BASE)):hashlib.sha256(file.read_bytes()).hexdigest() for relative in ['transcription/meeting-worker-2.3','ingestion','ingestion-monitor'] for file in (BASE/relative).iterdir() if file.is_file() and file.suffix in ('.py','.html','.js','.css')}
    ingestion.save_json(backup/'deployed-hashes.json',manifest)
    (BASE/'backups/review-flow-2.7.1-latest.txt').write_text(str(backup)+'\n')
    print('DEPLOYED 2.7.1; worker and monitor healthy; existing collection membership preserved')
    print('Private rollback:',backup)

if __name__=='__main__':main()
