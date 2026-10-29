"""Release packaging keeps the existing layout and excludes private runtime files."""
import importlib.util
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

spec=importlib.util.spec_from_file_location('release_builder',Path(__file__).resolve().parents[1]/'tools/build_release.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

class ReleaseTests(unittest.TestCase):
    def test_complete_layout_excludes_secrets_audio_and_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'repo';root.mkdir()
            files=['meeting_worker.py','meeting_asr.py','requirements-asr.txt','README.md','LICENSE',
                'ingestion/ingest_meetings.py','monitoring/run_monitor.py','diarization-benchmark/diarize_meeting.py',
                'docs/USAGE-FLOW.md','assets/brand/logo.png','deploy/deploy_review_flow.py','deploy/rollback_review_flow.py']
            files += ['review_tests/'+name for name in builder.REVIEW_TESTS]
            for name in files:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('public source fixture')
            for name in ['worker.env','monitoring/monitor.json','monitoring/telegram-token.txt','ingestion/api-key.txt','ingestion/state.json','ingestion/audio.mp3','data/private.py']:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('PRIVATE_RUNTIME_SENTINEL')
            destination=Path(temp)/'release'
            with patch.object(builder,'ROOT',root):
                archive=builder.build(destination)
                with self.assertRaises(ValueError):builder.build(destination)
            with zipfile.ZipFile(archive) as z:
                names=z.namelist()
                for name in ['release/ai-platform/transcription/meeting-worker-2.3/meeting_asr.py','release/tools/check_all.py','release/deploy.py','release/rollback.py','release/docs/USAGE-FLOW.md']:
                    self.assertIn(name,names)
                for name in names:self.assertNotIn(b'PRIVATE_RUNTIME_SENTINEL',z.read(name))

if __name__=='__main__':unittest.main()
