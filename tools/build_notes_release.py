"""Build a source-only Notes review package. Never activate services or copy runtime data."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
CORE=['traffic_control.py','traffic.html','traffic.js','knowledge_lifecycle.py','text_store.py','text_ingestion.py','text_web.py','text_card.html','text.html','text.js','text_markdown.js','openwebui_text_pipe.py','meeting_asr.py','meeting_dashboard.py','meeting_draft.py','meeting_flow.py','meeting_knowledge.py',
    'meeting_notifications.py','meeting_recovery.py','meeting_report.py','meeting_review.py','meeting_revision.py',
    'meeting_speakers.py','meeting_worker.py','openwebui_meeting_pipe.py','dashboard.html','dashboard.js',
    'dashboard.css','upload.html','configure_meeting_notifications.py','inspect_meeting_run.py',
    'recover_meeting_job.py','submit_meeting.py','notes_document.py','notes_store.py','notes_models.py',
    'notes_presentation.py','notes_library.py','notes_card.py','notes_upload.html','notes_dispatch.py','notes_risk.py','notes_web.py','notes_ingestion.py','heavy_gate.py',
    'openwebui_notes_pipe.py','notes.html','notes.js','notes.css','requirements-asr.txt','requirements-notes.txt']


def build(output,guide="docs/NOTES-ADOPTION.md"):
    output=Path(output).resolve()
    archive=output.with_suffix('.zip')
    if output.exists() or archive.exists() or output==ROOT or ROOT in output.parents:
        raise ValueError('Choose a fresh destination outside the source checkout')
    output.mkdir(parents=True)
    def copy(source,target):
        source=Path(source)
        if source.is_symlink():raise ValueError('Do not package source symlinks')
        destination=output/target;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
    for name in CORE:
        copy(ROOT/name,Path('source')/name)
        if name.startswith(('notes','text')) or name in ['heavy_gate.py','openwebui_text_pipe.py','openwebui_notes_pipe.py',
                'traffic_control.py','traffic.html','traffic.js','notes_library.py','knowledge_lifecycle.py','meeting_worker.py','meeting_notifications.py','meeting_dashboard.py','dashboard.html','dashboard.js','dashboard.css','requirements-notes.txt']:
            copy(ROOT/name,Path('payload/ai-platform/transcription/meeting-worker-2.3')/name)
    for directory in ['docs','tools','review_tests','tests','ingestion','monitoring','deploy','diarization-benchmark','notes_prototype']:
        for file in (ROOT/directory).iterdir():
            if file.is_file() and file.suffix in ('.py','.md','.cjs','.html','.js','.css','.txt','.service','.timer','.sh','.example','.conf'):
                copy(file,Path('source')/directory/file.name)
    for directory in ['assets/brand','assets/dashboard','assets/vendor']:
        for file in (ROOT/directory).iterdir():
            if file.is_file() and file.suffix in ('.png','.svg','.jpg','.js','.html','.md'):
                copy(file,Path('source')/directory/file.name)
    for name in ['README.md','LICENSE','CHANGELOG.md','.gitignore']:
        copy(ROOT/name,Path('source')/name)
    for name in ['ingest_meetings.py']:
        copy(ROOT/'ingestion'/name,Path('payload/ai-platform/ingestion')/name)
    for name in ['knowledge_lifecycle.py','text_store.py','text_ingestion.py','notes_ingestion.py','notes_document.py','notes_presentation.py','heavy_gate.py']:
        copy(ROOT/name,Path('payload/ai-platform/ingestion')/name)
    guide_path=(ROOT/guide).resolve()
    if not guide_path.is_relative_to((ROOT/'docs').resolve()) or guide_path.suffix!='.md':raise ValueError('Choose a Markdown guide inside docs')
    copy(guide_path,'START-HERE.md')
    manifest={str(file.relative_to(output)).replace('\\','/'):hashlib.sha256(file.read_bytes()).hexdigest()
        for file in output.rglob('*') if file.is_file()}
    (output/'SHA256SUMS.json').write_text(json.dumps(manifest,indent=2)+'\n')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        for file in output.rglob('*'):
            if file.is_file():bundle.write(file,Path(output.name)/file.relative_to(output))
    return archive


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--guide',default='docs/NOTES-ADOPTION.md')
    args=parser.parse_args();print(build(args.output,args.guide))
