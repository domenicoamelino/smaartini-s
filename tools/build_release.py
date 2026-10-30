#!/usr/bin/env python3
"""Build a source-only deployment ZIP. Never deploy or copy private runtime state."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
NAME='SMARTINIS-2.7.1-review-recovery'
REVIEW_TESTS=['test_document_recovery.py','test_flow.py','test_review.py','test_workflow.py','test_dashboard.py','test_speakers.py','test_pipe_review.py']
CHECK='''#!/usr/bin/env python3
import os,pathlib,subprocess,sys
root=pathlib.Path(__file__).resolve().parents[1]
platform=root/'ai-platform'
env=dict(os.environ,MEETING_TEST_PLATFORM_ROOT=str(platform))
for directory,modules in [('ingestion',['test_document_recovery','test_flow','test_review','test_workflow','test_dashboard','test_speakers','test_pipe_review','test_ingestion']),('ingestion-monitor',['test_monitor','test_telegram'])]:
    subprocess.run([sys.executable,'-m','unittest',*modules,'-v'],cwd=platform/directory,env=env,check=True)
print('All offline package checks passed; no live processing or approval performed.')
'''

def build(destination):
    destination=Path(destination).resolve()
    archive=destination.parent/(destination.name+'.zip')
    if destination.exists() or archive.exists():
        raise ValueError('Release destination already exists; choose a fresh --output directory')
    if destination==ROOT or ROOT.is_relative_to(destination):
        raise ValueError('Release destination must not contain the source repository')
    destination.mkdir(parents=True)
    def copy(source,relative):
        if source.is_symlink():raise ValueError('Source symlinks are not packaged: '+str(source))
        target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    for source in ROOT.iterdir():
        if source.is_file() and source.suffix in ('.py','.html','.js','.css') and not source.name.startswith('test') and '.before-' not in source.name:
            copy(source,Path('ai-platform/transcription/meeting-worker-2.3')/source.name)
    copy(ROOT/'requirements-asr.txt','ai-platform/transcription/meeting-worker-2.3/requirements-asr.txt')
    for folder,target in [('ingestion','ingestion'),('monitoring','ingestion-monitor'),('diarization-benchmark','diarization-benchmark')]:
        for source in (ROOT/folder).iterdir():
            allowed=source.suffix in ('.py','.html','.css','.js','.service','.timer','.md','.sh') or source.name in ('monitor.conf','requirements.txt')
            if source.is_file() and allowed:
                copy(source,Path('ai-platform')/target/source.name)
    for name in REVIEW_TESTS:copy(ROOT/'review_tests'/name,Path('ai-platform/ingestion')/name)
    for source in (ROOT/'docs').glob('*.md'):copy(source,Path('docs')/source.name)
    copy(ROOT/'README.md','README.md')
    copy(ROOT/'LICENSE','LICENSE')
    for source in (ROOT/'assets/brand').glob('*'):
        if source.is_file() and source.suffix in ('.png','.svg','.jpg'):copy(source,Path('assets/brand')/source.name)
    for directory in ('assets/dashboard','assets/vendor'):
        folder=ROOT/directory
        if folder.exists():
            for source in folder.iterdir():
                if source.is_file() and source.suffix in ('.js','.html','.md'):copy(source,Path(directory)/source.name)
    dashboard_builder=ROOT/'tools/build_dashboard_assets.py'
    if dashboard_builder.exists():copy(dashboard_builder,'tools/build_dashboard_assets.py')
    copy(ROOT/'deploy/deploy_review_flow.py','deploy.py');copy(ROOT/'deploy/rollback_review_flow.py','rollback.py')
    targeted=ROOT/'deploy/rollback_review_usability.py'
    if targeted.exists():copy(targeted,'rollback_review_usability.py')
    (destination/'tools').mkdir(exist_ok=True)
    (destination/'tools/check_all.py').write_text(CHECK,encoding='utf-8')
    (destination/'tools/check_review.py').write_text('from check_all import *\n',encoding='utf-8')
    files={str(p.relative_to(destination)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.rglob('*') if p.is_file()}
    (destination/'SHA256SUMS.json').write_text(json.dumps(files,indent=2)+'\n',encoding='utf-8')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as output:
        for file in destination.rglob('*'):
            if file.is_file():output.write(file,Path(destination.name)/file.relative_to(destination))
    return archive

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'dist'/NAME)
    args=parser.parse_args()
    try:archive=build(args.output)
    except ValueError as exc:parser.error(str(exc))
    print('Built:',archive)
    print('No deployment, service restart, model call, approval, commit or push performed.')

if __name__=='__main__':main()
