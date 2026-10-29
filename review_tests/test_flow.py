import json
import unittest
from unittest.mock import patch
import test_review
import meeting_flow as flow
import meeting_draft as draft

class TranscriptFlow(test_review.ReviewTests):
    def test_review_first_and_replacement(self):
        # Begin a new upload with the production review-first marker.
        root, folder = self.root, self.folder
        with test_review.review.connection(root) as c:
            c.execute('DELETE FROM revisions');c.execute('DELETE FROM meetings')
        import shutil
        shutil.rmtree(folder/'review');(folder/'review.json').unlink()
        source=json.loads((folder/'transcript.json').read_text());source['workflow']='review-first/1'
        test_review.report.save(folder/'transcript.json',source)
        test_review.review.ensure(root,self.job)
        with self.assertRaises(test_review.review.Conflict):self.action('approve')
        with self.assertRaises(ValueError):self.action('transcript-confirm')
        result=self.action('transcript-confirm',confirm_review=True,turns={'S000002':{'text':'Budget approved at 27 euros.','reviewed':True}})
        self.assertEqual(result['revision'],2)
        with self.assertRaises(test_review.review.Conflict):self.action('approve',revision=2)
        captured=[]
        def generate(payload,path):captured.append(payload);return '# Recap\nBudget approved: 27 euros.'
        test_review.review.process_next(root,generate)
        self.assertIn('27 euros',captured[0]['transcript']['segments'][1]['text'])
        self.action('approve',revision=3)
        old=test_review.ingestion.document(folder,root)
        self.action('transcript-save',revision=3,turns={'S000002':{'text':'Budget proposed at 28 euros.'}})
        self.assertEqual(test_review.ingestion.document(folder,root)['sha256'],old['sha256'])
        with self.assertRaises(test_review.review.Conflict):self.action('approve',revision=4)
        test_review.review.recover(root)
        self.assertFalse(test_review.review.view(root,self.job['id'],'alice')['transcript_reviewed'])
        self.action('transcript-confirm',revision=4,confirm_review=True)
        test_review.review.process_next(root,lambda payload,path:'# Recap\nProposed budget: 28 euros.')
        self.action('approve',revision=6)
        new=test_review.ingestion.document(folder,root)
        self.assertNotEqual(old['sha256'],new['sha256'])

class Edits(unittest.TestCase):
    def test_cutoff_preserves_original_and_flags(self):
        source={'segments':[{'start':0,'end':2,'text':'decem','avg_logprob':-2},{'start':2,'end':4,'text':'Goodbye'}]}
        edited=flow.apply_edits(source,{'turns':{'S000001':{'text':'December','reviewed':True}},'meeting_end_seconds':2})
        self.assertEqual(source['segments'][0]['text'],'decem')
        self.assertEqual(edited['segments'][0]['original_text'],'decem')
        self.assertTrue(edited['segments'][1]['excluded_from_recap'])
        self.assertFalse(flow.turns(edited)[0]['warnings'])
        self.assertEqual(len(draft.records({'transcript':edited})),1)
        self.assertNotIn('Goodbye',draft.records({'transcript':edited})[0]['text'])
        restored=flow.apply_edits(edited,{'meeting_end_seconds':None})
        self.assertFalse(restored['segments'][1]['excluded_from_recap'])
    def test_invalid_turns_and_cutoffs(self):
        source={'segments':[{'start':0,'end':2,'text':'Hello'}]}
        for obj in [{'turns':{'S000002':{'text':'x'}}},{'meeting_end_seconds':float('nan')},{'turns':{'S000001':{'excluded':True}}}]:
            with self.assertRaises(ValueError):flow.apply_edits(source,obj)

class WorkerReviewFirst(test_review.ReviewTests):
    def test_upload_stops_at_transcript_without_model_or_approval(self):
        worker=test_review.worker
        source={'audio_duration_seconds':2,'segments':[{'start':0,'end':2,'text':'Plan for December.'}]}
        new=worker.create_session('alice','new-upload')
        folder=self.root/('processed-upload_'+new['id']);folder.mkdir()
        test_review.report.save(folder/'meeting_metadata.json',dict(test_review.fixture.BASE))
        (folder/'audio.wav').write_bytes(b'fixture')
        worker.update(new['id'],state='queued',folder=str(folder),filename='new.wav')
        with patch.object(worker.asr,'transcribe',return_value=source) as transcribe, patch.object(worker.revisions,'generate') as recap:
            worker.process(worker.get_job(new['id']))
        self.assertEqual(transcribe.call_args.kwargs['profile'],'speech-preserving')
        recap.assert_not_called()
        value=test_review.review.view(self.root,new['id'],'alice')
        self.assertFalse(value['transcript_reviewed']);self.assertFalse(value['recap_ready'])
        self.assertIsNone(test_review.ingestion.document(folder,self.root))
        with self.assertRaises(test_review.review.Conflict):
            test_review.review.act(self.root,new['id'],'alice',{'action':'approve','revision':1})

class GeneratorChecks(unittest.TestCase):
    def test_all_source_covered_and_model_cache_reused(self):
        import tempfile
        from pathlib import Path
        calls=[]
        class Client:
            def __init__(self,args,archive):self.archive=archive
            def discover(self):test_review.report.save(self.archive/'model_info.json',{'model':'fixture'})
            def generate(self,prompt,label,system,schema=None):calls.append((prompt,label));return {'recap':'# Compact draft\nSupported outcomes require manual review.'}
        payload={'transcript':{'segments':[{'start':i*60,'end':i*60+30,'text':f'UNIQUE_{i}_SOURCE '+('work project evidence '*60)} for i in range(50)]},'metadata':{'report_language':'English'}}
        with tempfile.TemporaryDirectory() as temp,patch.object(draft.report,'Ollama',Client):
            first=draft.generate(payload,Path(temp));n=len(calls)
            self.assertGreater(n,1)
            source_prompts=' '.join(prompt for prompt,label in calls if label.startswith('Review source'))
            for i in range(50):self.assertIn(f'UNIQUE_{i}_SOURCE',source_prompts)
            self.assertEqual(draft.generate(payload,Path(temp)),first);self.assertEqual(len(calls),n)
    def test_frozen_asr_and_completed_cache_reuse(self):
        import dataclasses,tempfile,types
        from pathlib import Path
        import meeting_asr as asr
        @dataclasses.dataclass
        class Segment:
            start:float=0
            end:float=1
            text:str='Hello, goedemorgen, buongiorno.'
        options=[]
        class Engine:
            def __init__(self,*a,**kw):pass
            def transcribe(self,*a,**kw):options.append(kw);return iter([Segment()]),types.SimpleNamespace(duration=1,duration_after_vad=1,language='en',language_probability=.8)
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);(p/'audio.wav').write_bytes(b'fixture');(p/'model.bin').write_bytes(b'fixture')
            with patch.object(asr,'model_directory',return_value=(p,'frozen')),patch('importlib.metadata.version',return_value='fixture'),patch.dict('sys.modules',{'faster_whisper':types.SimpleNamespace(WhisperModel=Engine)}):
                result=asr.transcribe(p/'audio.wav','turbo',p/'out')
                with patch.object(Engine,'__init__',side_effect=AssertionError('Cache must avoid model loading')):
                    cached=asr.transcribe(p/'audio.wav','turbo',p/'out')
            self.assertEqual(result,cached);self.assertEqual(len(options),1)
            self.assertFalse(options[0]['vad_filter']);self.assertIsNone(options[0]['language']);self.assertTrue(options[0]['multilingual'])

if __name__=='__main__':unittest.main()
