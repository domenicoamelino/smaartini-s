import copy,json,tempfile,unittest,os
from pathlib import Path
from unittest.mock import patch
import test_review
import test_dashboard
import meeting_flow as flow
import meeting_draft as draft
import meeting_recovery as recovery

class DocumentTests(unittest.TestCase):
    def test_word_splits_become_complete_readable_document(self):
        source={'segments':[{'start':i*.3,'end':i*.3+.3,'text':f'word{i}', 'speaker':f'SPEAKER_{i%2:02d}','speaker_status':'assigned'} for i in range(5000)]}
        original=copy.deepcopy(source);blocks=flow.document_blocks(source)
        self.assertLess(len(blocks),60)
        self.assertEqual(' '.join(b['text'] for b in blocks),' '.join(s['text'] for s in source['segments']))
        self.assertEqual(source,original)
        self.assertEqual([i for b in blocks for i in b['indices']],list(range(5000)))
    def test_paragraph_edit_retains_original_source_and_uncertain_speaker(self):
        source={'segments':[{'start':i,'end':i+1,'text':word,'speaker':f'SPEAKER_{i%2:02d}','speaker_status':'assigned','words':[{'word':word}]} for i,word in enumerate(['The','month','is','November.'])]}
        block=flow.document_blocks(source)[0]
        result=flow.apply_edits(source,{'blocks':{block['id']:{'text':'The month is December.','reviewed':True}}})
        self.assertEqual(len(result['segments']),1)
        row=result['segments'][0];self.assertEqual(row['text'],'The month is December.')
        self.assertEqual(row['original_text'],'The month is November.');self.assertEqual(len(row['source_turn_ids']),4)
        self.assertNotIn('speaker_name',row);self.assertEqual(row['end'],4);self.assertEqual(row['words'],[])
        self.assertEqual(source['segments'][3]['text'],'November.')
    def test_confirmed_identity_boundary_and_cutoff_are_preserved(self):
        source={'segments':[{'start':0,'end':1,'text':'Hello.','speaker_confirmed':True,'speaker_name':'Ada'}, {'start':2,'end':3,'text':'Goodbye.'}]}
        self.assertEqual(len(flow.document_blocks(source)),2)
        cut=flow.apply_edits(source,{'meeting_end_seconds':2})
        block=flow.document_blocks(cut)[1]
        self.assertTrue(block['outside_meeting']);self.assertFalse(block['excluded'])
        restored=flow.apply_edits(cut,{'blocks':{block['id']:{'text':'Goodbye.','excluded':False}},'meeting_end_seconds':None})
        self.assertFalse(restored['segments'][1]['excluded_from_recap'])
    def test_invalid_paragraph_cannot_change_source(self):
        source={'segments':[{'start':0,'end':1,'text':'Hello'}]}
        for obj in [{'blocks':{'B999999-999999':{'text':'Other'}}},{'blocks':{'B000001-000001':{'text':None}}},{'blocks':{'B000001-000001':{'text':''}}}]:
            with self.assertRaises(ValueError):flow.apply_edits(source,obj)
        self.assertEqual(source['segments'][0]['text'],'Hello')

class FailureRecovery(test_review.ReviewTests):
    def fail_attempt(self):
        self.action('approve')
        self.action('transcript-confirm',confirm_review=True)
        def generate(payload,path):
            test_review.report.save(path/'draft-cache.json',{'saved':'First completed section.'})
            test_review.report.save(path/'response_0002.json',{'content':'{"recap":"Second partial section\\nUnfinished', 'metrics':{'done_reason':'length','eval_count':2400,'prompt_eval_count':6900}})
            raise test_review.report.ReportError('Incomplete/model-truncated output')
        test_review.review.process_next(self.root,generate)
    def test_failed_recap_has_log_and_manual_replacement_can_be_approved(self):
        self.fail_attempt();value=test_review.review.view(self.root,self.job['id'],'alice')
        self.assertFalse(value['recap_ready']);self.assertFalse(value['pending'])
        self.assertIn('First completed section',value['recovered_draft']);self.assertIn('Second partial section',value['recovered_draft'])
        self.assertEqual(value['generation_attempts'][0]['responses'][0]['done_reason'],'length')
        self.assertIn('truncated',value['generation_attempts'][0]['failure']['message'])
        previous=test_review.ingestion.document(self.folder,self.root)
        result=self.action('dashboard-save',revision=2,content='# Reviewed manual recap\nChecked wording.',metadata=dict(test_review.fixture.BASE),mapping={})
        self.assertEqual(result['revision'],3)
        self.assertEqual(test_review.ingestion.document(self.folder,self.root)['sha256'],previous['sha256'])
        self.assertTrue(test_review.review.view(self.root,self.job['id'],'alice')['recap_ready'])
        self.action('approve',revision=3)
        self.assertNotEqual(test_review.ingestion.document(self.folder,self.root)['sha256'],previous['sha256'])
    def test_old_attempt_not_offered_after_new_transcript_revision(self):
        self.fail_attempt()
        self.action('transcript-save',revision=2,turns={'S000001':{'text':'New corrected source'}})
        value=test_review.review.view(self.root,self.job['id'],'alice')
        self.assertEqual(value['recovered_draft'],'');self.assertTrue(value['generation_attempts'])
    def test_placeholder_cannot_be_promoted_by_metadata_only_save(self):
        self.fail_attempt();value=test_review.review.view(self.root,self.job['id'],'alice')
        with self.assertRaises(test_review.review.Conflict):self.action('dashboard-save',revision=2,content=value['report'],metadata=dict(test_review.fixture.BASE),mapping={})
    def test_logs_redact_secrets(self):
        with patch.dict(os.environ,{'MEETING_API_KEY':'super-secret-example-value'}):
            text=recovery.safe_message('key super-secret-example-value Bearer ABCDEFG https://private.example/path')
        self.assertNotIn('super-secret-example-value',text);self.assertNotIn('ABCDEFG',text);self.assertNotIn('private.example',text)

class DownloadTests(test_dashboard.DashboardTests):
    def test_transcript_download_is_readable_revision_bound_and_owner_scoped(self):
        url='api/meetings/'+self.job['id']+'/transcript.txt'
        status,text,headers=self.request(url)
        self.assertEqual(status,200);self.assertIn('00:00:00',text);self.assertIn('no role document',text)
        self.assertIn('-r1-transcript.txt',headers['Content-Disposition']);self.assertIn('no-store',headers['Cache-Control'])
        self.assertEqual(self.request(url,cookie='bob-session')[0],404)
        self.assertEqual(self.request(url,cookie=None)[0],401)
        self.assertEqual(self.request('api/meetings/'+self.job['id']+'/transcript.json')[0],200)
    def test_download_log_never_returns_prompt_or_api_key(self):
        status,value,_=self.request('api/meetings/'+self.job['id']+'/generation-log.json')
        self.assertEqual(status,200);self.assertEqual(value,[])

class CompactGeneration(unittest.TestCase):
    def test_stream_interruption_keeps_partial_text_for_every_attempt(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def __iter__(self):
                yield (json.dumps({'message':{'content':'{"recap":"Partial working text'}})+'\n').encode()
                raise TimeoutError('Interrupted connection')
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);args=test_review.report.parser().parse_args([str(path/'unused.json')]);args.capture_partial=True
            client=test_review.report.Ollama(args,path)
            with patch.object(client,'request',return_value=Response()),patch.object(test_review.report.time,'sleep'):
                with self.assertRaises(test_review.report.ReportError):client.generate('test','fixture',schema={'type':'object'})
            streams=list(path.glob('stream_*.json'));self.assertEqual(len(streams),3)
            for file in streams:self.assertIn('Partial working text',json.loads(file.read_text())['content'])
    def test_failure_categories_are_specific(self):
        for error,category in [(TimeoutError('timed out'),'timeout'),(ValueError('Invalid recap JSON'),'invalid_response'),(RuntimeError('context exceeded'),'context_limit'),(RuntimeError('Ollama HTTP 503'),'service_error')]:
            self.assertEqual(recovery.problem(error)['category'],category)
    def test_one_compact_retry_and_successful_stage_cache(self):
        calls=[]
        class Client:
            def __init__(self,args,archive):self.args=args;self.archive=archive
            def discover(self):test_review.report.save(self.archive/'model_info.json',{'model':'fixture'})
            def generate(self,prompt,label,system,schema=None):
                calls.append((prompt,self.args.output_tokens))
                if len(calls)==1:raise test_review.report.ReportError('Incomplete/model-truncated output')
                return {'recap':'# Draft\nCompleted compact output.'}
        payload={'transcript':{'segments':[{'start':0,'end':1,'text':'Discussed a plan.'}]},'metadata':{'report_language':'English'}}
        with tempfile.TemporaryDirectory() as temp,patch.object(draft.report,'Ollama',Client):
            result=draft.generate(payload,Path(temp));self.assertEqual(len(calls),2)
            self.assertIn('at most 250 words',calls[1][0]);self.assertLessEqual(calls[1][1],4800)
            self.assertEqual(draft.generate(payload,Path(temp)),result);self.assertEqual(len(calls),2)
            self.assertIn('compact_retry',(Path(temp)/'events.jsonl').read_text())
    def test_partial_json_recovery_is_explicitly_incomplete(self):
        text,complete=recovery.extract('{"recap":"Useful notes\\nUnfinished sentence')
        self.assertFalse(complete);self.assertIn('Useful notes\nUnfinished',text)

if __name__=='__main__':unittest.main()
