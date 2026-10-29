"""Metadata-aware CLI and recovery boundaries; no real services or model calls."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote

import recover_meeting_job as recovery
import submit_meeting as cli


class ClientTests(unittest.TestCase):
    def test_cli_encodes_metadata_and_streams_original_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / 'sample.m4a'
            audio.write_bytes(b'synthetic-audio')
            calls = []

            class Connection:
                def __init__(self, *args, **kwargs):
                    pass

                def request(self, method, path, body=None, headers=None):
                    calls.append((path, body.read() if hasattr(body, 'read') else body, headers))

                def getresponse(self):
                    class Response:
                        status = 200

                        def read(self):
                            return json.dumps({'id': 'a' * 32, 'upload_token': 'test-token',
                                               'state': 'queued'}).encode()
                    return Response()

                def close(self):
                    pass

            with patch.object(cli.http.client, 'HTTPConnection', Connection), \
                 patch.dict(cli.os.environ, {'MEETING_API_KEY': 'x' * 40}), \
                 patch('sys.argv', ['submit', str(audio), '--title', 'Café planning',
                                    '--meeting-date', '2026-10-22', '--participant', 'Alex']), \
                 contextlib.redirect_stdout(io.StringIO()):
                cli.main()
            self.assertEqual(calls[1][1], b'synthetic-audio')
            metadata = json.loads(unquote(calls[1][2]['X-Meeting-Metadata']))
            self.assertEqual(metadata, {'meeting_title': 'Café planning',
                                       'meeting_date': '2026-10-22', 'participants': ['Alex'],
                                       'transcription_vocabulary':'','diarization_enabled':False,'speaker_count':None})

    def test_cli_rejects_missing_metadata_before_any_network_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / 'sample.m4a'
            audio.write_bytes(b'test')
            with patch.object(cli.http.client, 'HTTPConnection') as connection, \
                 patch.dict(cli.os.environ, {'MEETING_API_KEY': 'x' * 40}), \
                 patch('sys.argv', ['submit', str(audio)]), \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    cli.main()
                connection.assert_not_called()


class RecoveryTests(unittest.TestCase):
    def recover(self, status='complete'):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp).resolve()
            archive = folder / 'analysis' / 'attempt'
            archive.mkdir(parents=True)
            (archive / 'manifest.json').write_text(json.dumps({
                'model': 'test', 'language': 'English', 'context': 4096,
                'output_tokens': 500, 'status':status}), encoding='utf-8')
            for name in ('report.md', 'transcript.md', 'source.json', 'findings.json'):
                (archive / name).write_text('synthetic', encoding='utf-8')
            job = {'id': 'a' * 32, 'state': 'failed', 'folder': str(folder)}
            events = []

            with patch.object(recovery.w, 'get_job', return_value=job), \
                 patch.object(recovery.w.report, 'run', return_value=archive), \
                 patch.object(recovery.w.review, 'ensure', side_effect=lambda *a:events.append('review')) as ensure, \
                 patch.object(recovery.w.knowledge, 'export') as export, \
                 patch.object(recovery.w, 'update', side_effect=lambda *a, **k: events.append(k['state'])), \
                 patch('sys.argv', ['recover', job['id']]), \
                 contextlib.redirect_stdout(io.StringIO()):
                if status!='complete':
                    with self.assertRaises(RuntimeError):
                        recovery.main()
                    ensure.assert_not_called()
                else:
                    recovery.main()
                export.assert_not_called()
            return events

    def test_recovery_publishes_only_reviewable_unapproved_draft(self):
        self.assertEqual(self.recover(), ['completed','review'])

    def test_incomplete_recovery_keeps_job_failed(self):
        self.assertEqual(self.recover('incomplete'), [])
