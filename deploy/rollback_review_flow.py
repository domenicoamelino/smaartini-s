#!/usr/bin/env python3
"""Roll back code and the installed Function; retain later meeting edits/approvals."""
import json,pathlib,re,shutil,sys,tarfile
import deploy

def main():
    base=deploy.BASE
    backup=pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else pathlib.Path((base/'backups/review-flow-2.7.0-latest.txt').read_text().strip())
    if not backup.resolve().is_relative_to((base/'backups').resolve()):raise RuntimeError('Rollback must be inside the private platform backups')
    deploy.idle()
    deploy.command('systemctl','--user','stop','meeting-ingestion.timer')
    deploy.command('systemctl','--user','stop','meeting-monitor.service',check=False)
    with tarfile.open(backup/'private-rollback.tar.gz') as archive:
        for member in archive.getmembers():
            path=pathlib.PurePosixPath(member.name)
            if not member.isfile() or path.is_absolute() or '..' in path.parts:continue
            if not (member.name.startswith(('transcription/meeting-worker-2.3/','ingestion/','ingestion-monitor/'))):continue
            # State databases, approval state, snapshots and credentials other than the
            # worker model settings must retain post-deployment updates.
            if path.suffix not in ('.py','.html','.js','.css') and member.name!='transcription/meeting-worker-2.3/worker.env':continue
            target=base/member.name;temporary=target.with_name(target.name+'.rollback')
            with archive.extractfile(member) as source,temporary.open('wb') as dest:shutil.copyfileobj(source,dest)
            temporary.chmod(member.mode);temporary.replace(target)
    sys.path.insert(0,str(base/'ingestion'));import ingest_meetings as ingestion
    cfg=ingestion.load_config(base/'ingestion/config.json');client=ingestion.Client(cfg['base_url'],ingestion.load_key(base/'ingestion/api-key.txt'))
    function=json.loads((backup/'openwebui-function.json').read_text())
    client.request('POST','/api/v1/functions/id/'+function['id']+'/update',{key:function[key] for key in ('id','name','content','meta')})
    text=(deploy.WORKER/'meeting_dashboard.py').read_text();version=re.search(r"VERSION\s*=\s*['\"]([^'\"]+)",text).group(1)
    deploy.restart_worker(version)
    deploy.command('systemctl','--user','restart','meeting-monitor.service')
    inventory=json.loads((backup/'inventory.json').read_text())
    if inventory['timer_active']:deploy.command('systemctl','--user','start','meeting-ingestion.timer')
    print('Code rollback complete. Meeting edits, approvals, stored audio and current knowledge-base state retained.')

if __name__=='__main__':main()
