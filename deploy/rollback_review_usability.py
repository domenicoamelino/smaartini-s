#!/usr/bin/env python3
"""Roll back the targeted 2.7.1 worker update without restoring meeting databases."""
import argparse,importlib.util,pathlib,re,shutil,subprocess,tarfile

def main():
    base=pathlib.Path.home()/'ai-platform';home=base/'backups/review-usability-20261030'
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('backup',nargs='?',type=pathlib.Path);args=parser.parse_args()
    backup=args.backup or pathlib.Path((home/'latest-rollback.txt').read_text().strip())
    if not backup.resolve().is_relative_to((base/'backups').resolve()):raise RuntimeError('Use the private platform backup directory')
    candidates=[pathlib.Path(__file__).with_name('deploy.py'),pathlib.Path(__file__).with_name('deploy_review_flow.py'),home/'release/deploy.py']
    helper=next((p for p in candidates if p.is_file()),None)
    if helper is None:raise RuntimeError('Keep the deployment helper beside the rollback script')
    spec=importlib.util.spec_from_file_location('restart_helpers',helper);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.idle();worker=base/'transcription/meeting-worker-2.3'
    timer=subprocess.run(['systemctl','--user','is-active','meeting-ingestion.timer'],capture_output=True,text=True).stdout.strip()=='active'
    subprocess.run(['systemctl','--user','stop','meeting-ingestion.timer'],check=True)
    try:
        with tarfile.open(backup/'private-worker-before.tar.gz') as archive:
            for member in archive.getmembers():
                path=pathlib.PurePosixPath(member.name)
                if not member.isfile() or len(path.parts)!=1 or path.suffix not in ('.py','.html','.css','.js'):continue
                target=worker/member.name;temp=target.with_name(target.name+'.rollback')
                with archive.extractfile(member) as source,temp.open('wb') as destination:shutil.copyfileobj(source,destination)
                temp.chmod(member.mode);temp.replace(target)
        version=re.search(r"VERSION\s*=\s*['\"]([^'\"]+)",(worker/'meeting_dashboard.py').read_text()).group(1)
        module.restart_worker(version)
    finally:
        if timer:subprocess.run(['systemctl','--user','start','meeting-ingestion.timer'],check=True)
    print('Worker code restored. Meeting edits, approved revisions, knowledge entries and settings retained.')

if __name__=='__main__':main()
