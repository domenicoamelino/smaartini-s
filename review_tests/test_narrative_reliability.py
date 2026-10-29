import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import meeting_report as r


class ReliabilityTests(unittest.TestCase):
    def args(self, **kw):
        return types.SimpleNamespace(**dict(language='English', context=5000,
            output_tokens=512, token_safety=384, resume=None, **kw))

    def facts(self, n=1, size=50):
        return [{'kind': 'topic', 'text': f'Topic {i}: ' + 'x' * size,
                 'evidence': [{'id': f'S{i+1:06d}', 'quote': 'Roles are unclear.'}],
                 'owner': None, 'deadline': None, 'interpretation': None} for i in range(n)]

    def paragraph(self, ref=1, text='Roles are unclear.'):
        return {'section': 'discussion', 'text': text, 'facts': [ref]}

    def test_old_boundary_fails_but_every_new_retry_fits_in_utf8(self):
        args = self.args()
        rows = r.narrative_items(self.facts(30, 60))
        compact = [{k: v for k, v in row.items() if k != 'sources'} for row in rows]
        old = args.context - args.output_tokens - args.token_safety - len(r.NARRATIVE_SYSTEM.encode()) - 350
        self.assertTrue(any(len((r.NARRATIVE_SYSTEM + r.narrative_prompt(b, args.language, r.NARRATIVE_CORRECTION)).encode())
            + args.output_tokens + args.token_safety > args.context for b in r.pack(compact, old)))
        for language in ('English', 'Italian', '日本語'):
            args.language = language
            for batch in r.pack(compact, r.narrative_budget(args)):
                for correction in ('', r.NARRATIVE_CORRECTION):
                    self.assertLessEqual(len((r.NARRATIVE_SYSTEM + r.narrative_prompt(batch, language, correction)).encode())
                        + args.output_tokens + args.token_safety, args.context)

    def test_retry_size_guard_and_first_attempt_sibling_survives(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.args()
            calls = []
            def generate(prompt, label, system, **kw):
                calls.append(prompt)
                self.assertLessEqual(len((system + prompt).encode()) + args.output_tokens + args.token_safety, args.context)
                return {'paragraphs': [self.paragraph(), self.paragraph(text='Lived there until age 27.')]}
            client = types.SimpleNamespace(archive=Path(temp), generate=generate)
            with patch.object(r, 'verify_claim', return_value=True):
                paragraphs, rows = r.write_narrative(client, self.facts(), args)
            self.assertEqual(len(calls), 2)
            self.assertEqual(paragraphs, [self.paragraph()])
            self.assertEqual(len(rows), 1)
            self.assertTrue((Path(temp) / 'omitted_claims.json').exists())

    def test_first_valid_paragraph_survives_malformed_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            client = types.SimpleNamespace(archive=Path(temp), generate=lambda *a, **k: None)
            with patch.object(client, 'generate', side_effect=[{'paragraphs': [self.paragraph(), {}]}, {}]), patch.object(r, 'verify_claim', return_value=True):
                paragraphs, _ = r.write_narrative(client, self.facts(), self.args())
            self.assertEqual(paragraphs, [self.paragraph()])
            self.assertTrue((Path(temp) / 'narrative_incomplete.json').exists())

    def test_context_overflow_omits_batch_and_continues(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.args()
            def generate(prompt, label, system, **kw):
                ref = kw['request_meta']['items'][0]['ref']
                if ref == 1:
                    raise r.ReportError('Internal context budget exceeded')
                return {'paragraphs': [self.paragraph(ref)]}
            client = types.SimpleNamespace(archive=Path(temp), generate=generate)
            with patch.object(r, 'verify_claim', return_value=True):
                paragraphs, rows = r.write_narrative(client, self.facts(3, 700), args)
            self.assertEqual(len(rows), 3)
            self.assertTrue(paragraphs)
            self.assertTrue((Path(temp) / 'narrative_incomplete.json').exists())
            self.assertTrue((Path(temp) / 'narrative.json').exists())

    def test_oversized_record_keeps_evidence_and_other_batches(self):
        with tempfile.TemporaryDirectory() as temp:
            facts = self.facts(1, 5000) + self.facts()
            client = types.SimpleNamespace(archive=Path(temp), generate=lambda *a, **k: {'paragraphs': [self.paragraph(2)]})
            with patch.object(r, 'verify_claim', return_value=True):
                paragraphs, rows = r.write_narrative(client, facts, self.args())
            self.assertEqual(len(rows), 2)
            self.assertEqual(paragraphs[0]['facts'], [2])
            self.assertTrue((Path(temp) / 'narrative_incomplete.json').exists())

    def test_unknown_speaker_context_is_validation_not_transport_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            client = types.SimpleNamespace(archive=Path(temp), generate=lambda *a, **k:
                {'paragraphs': [self.paragraph(text='SPEAKER_99 said something.'), self.paragraph()]})
            with patch.object(r, 'verify_claim', return_value=True):
                paragraphs, _ = r.write_narrative(client, self.facts(), self.args())
            self.assertEqual(paragraphs, [self.paragraph()])

    def test_empty_narrative_checkpoint_regenerates_safely(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.args()
            client = types.SimpleNamespace(archive=Path(temp), generate=lambda *a, **k: {'paragraphs': [self.paragraph()]})
            with patch.object(r, 'verify_claim', return_value=True):
                r.write_narrative(client, self.facts(), args)
                path = Path(temp) / 'narrative_cache.json'
                data = json.loads(path.read_text())
                path.write_text(json.dumps({key: [] for key in data}))
                args.resume = Path(temp)
                paragraphs, _ = r.write_narrative(client, self.facts(), args)
            self.assertEqual(paragraphs, [self.paragraph()])

    def test_transport_failure_stops_instead_of_publishing(self):
        with tempfile.TemporaryDirectory() as temp:
            client = types.SimpleNamespace(archive=Path(temp), generate=lambda *a, **k: None)
            with patch.object(client, 'generate', side_effect=r.ReportError('HTTP 500')):
                with self.assertRaisesRegex(r.ReportError, 'resumable'):
                    r.write_narrative(client, self.facts(), self.args())

    def test_missing_cache_never_starts_extraction(self):
        client = types.SimpleNamespace(cache={}, generate=lambda *a, **k: self.fail('generation started'))
        args = self.args(require_cached_extraction=True)
        with self.assertRaisesRegex(r.ReportError, 'will not rerun'):
            r.extract(client, [{'id':'S000001', 'text':'Roles are unclear.'}], {}, args)

    def test_personal_history_without_verified_identity_is_rejected(self):
        with self.assertRaisesRegex(r.ReportError, 'identity review'):
            r.check_narrative({'paragraphs':[self.paragraph(text='The speaker was born in Eindhoven.')]}, {1},
                {1: {'kind':'topic', 'sources':['I was born in Eindhoven.'], 'speaker_context':[]}})


if __name__ == '__main__':
    unittest.main()
