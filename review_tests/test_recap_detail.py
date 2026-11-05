import json,unittest,tempfile,hashlib
from pathlib import Path
from unittest.mock import patch
import test_review
import test_dashboard
import test_ingestion as ingestion_fixture
import meeting_draft as draft
import knowledge_lifecycle as lifecycle

class RegenerationTests(test_review.ReviewTests):
    def test_approved_regeneration_keeps_exact_snapshot_and_source(self):
        self.action('approve');first=test_review.ingestion.document(self.folder,self.root)
        original=(self.folder/'transcript.json').read_bytes()
        result=self.action('regenerate',detail_level='long',ai_instructions='Discuss dependencies.')
        self.assertEqual(test_review.ingestion.document(self.folder,self.root)['sha256'],first['sha256'])
        seen=[]
        def generate(payload,path):
            seen.append(payload);return 'All dependencies from the reviewed source.'
        test_review.review.process_next(self.root,generate)
        self.assertEqual(seen[0]['detail_level'],'long');self.assertEqual(seen[0]['ai_instructions'],'Discuss dependencies.')
        current=test_review.review.view(self.root,self.job['id'],'alice')
        self.assertEqual(current['detail_level'],'long')
        self.assertEqual(current['revision'],2);self.assertEqual(current['last_approved']['revision'],1)
        self.assertNotIn('Discuss dependencies.',json.dumps(current))
        self.assertEqual((self.folder/'transcript.json').read_bytes(),original)
        self.assertEqual(test_review.ingestion.document(self.folder,self.root)['sha256'],first['sha256'])
        self.action('approve',revision=2)
        self.assertNotEqual(test_review.ingestion.document(self.folder,self.root)['sha256'],first['sha256'])
        self.action('regenerate',revision=2,detail_level='medium')
        test_review.review.process_next(self.root,lambda p,w:'Another unapproved draft')
        self.assertEqual(test_review.review.view(self.root,self.job['id'],'alice')['revision'],3)

    def test_validation_owner_failure_retry_and_withdrawal(self):
        for kw in [{'detail_level':'enormous'},{'detail_level':[]},{'ai_instructions':'x'*4001}]:
            with self.assertRaises(ValueError):self.action('regenerate',**kw)
        with self.assertRaises(test_review.review.Conflict):
            test_review.review.act(self.root,self.job['id'],'bob',dict(action='regenerate',revision=1))
        self.action('approve')
        source=self.folder.name
        lifecycle.change(self.root,source,'alice','remove',0)
        self.action('regenerate',detail_level='long')
        def fail(p,w):raise TimeoutError('test timeout')
        test_review.review.process_next(self.root,fail)
        self.action('retry');test_review.review.recover(self.root)
        test_review.review.process_next(self.root,lambda p,w:'Recovered complete draft')
        self.action('approve',revision=2)
        self.assertEqual(lifecycle.all_states(self.root)[source]['status'],'pending')

class IndexedRegeneration(unittest.TestCase):
    setUp=test_review.ReviewTests.setUp
    action=test_review.ReviewTests.action
    def test_indexed_reapproval_withdrawal_and_explicit_restore(self):
        test_review.report.save(self.folder/'job.json',{'state':'completed'})
        client=ingestion_fixture.FakeClient();request=client.request
        def private(method,path,obj=None):
            value=request(method,path,obj)
            if path=='/api/v1/knowledge/kb':value.update(user_id='alice',access_grants=[])
            return value
        client.request=private
        config={'base_url':'http://127.0.0.1:8080','collection_id':'kb','meetings_root':str(self.root.resolve())}
        state=test_review.ingestion.State(self.root/'fake-ledger.json',config)
        def sync():
            with patch.object(test_review.ingestion,'emit'):
                result=test_review.ingestion.sync(client,config,state,apply=True,busy=lambda _:False)
            self.assertFalse(result['errors']);return result
        self.action('approve');sync();self.assertEqual(client.members,{'file1'})
        self.action('regenerate',detail_level='long');sync();self.assertEqual(client.uploads,1)
        test_review.review.process_next(self.root,lambda p,w:'New detailed recap from the same transcript')
        sync();self.assertEqual(client.members,{'file1'});self.assertEqual(client.uploads,1)
        self.action('approve',revision=2);sync();self.assertEqual(client.members,{'file2'})
        sync();self.assertEqual(client.uploads,2)
        lifecycle.change(self.root,self.folder.name,'alice','remove',0);sync();self.assertEqual(client.members,set())
        self.action('regenerate',revision=2,detail_level='medium')
        test_review.review.process_next(self.root,lambda p,w:'Another complete draft after withdrawal')
        self.action('approve',revision=3);sync();self.assertEqual(client.uploads,2);self.assertEqual(client.members,set())
        lifecycle.change(self.root,self.folder.name,'alice','restore',1);sync();self.assertEqual(client.members,{'file3'})

class DetailTests(unittest.TestCase):
    def test_all_levels_all_source_corrections_cache_and_budgets(self):
        calls=[]
        class Client:
            def __init__(self,args,archive):self.args=args;self.archive=archive
            def discover(self):test_review.report.save(self.archive/'model_info.json',{'test':True})
            def generate(self,prompt,label,system,schema=None):
                calls.append((prompt,self.args.output_tokens))
                data=json.loads(prompt.split('DATA:\n',1)[1].split('\nStyle refinement:',1)[0])
                if 'sections' in schema.get('properties',{}):return {'sections':[{'topic_ids':[sid for r in data['source'] for sid in r.get('topic_ids',[r.get('topic_id')])],'text':' '.join(x['text'] for x in data['source'])}]}
                return {'recap':' '.join(x['text'].split()[0] for x in data['source'])+(' User-corrected wording' if 'User-corrected wording' in prompt else '')}
        source={'segments':[{'start':i*60,'end':i*60+30,'text':f'TOPIC_{i} '+('technical evidence '*60),'user_corrected':i==80} for i in range(85)]}
        source['segments'].append({'start':5200,'end':5201,'text':'EXCLUDED_SECRET','excluded_from_recap':True})
        with tempfile.TemporaryDirectory() as tmp,patch.object(draft.report,'Ollama',Client):
            for level,tokens in [('short',2400),('medium',3840),('long',6000)]:
                payload={'transcript':source,'metadata':{'report_language':'English'},'detail_level':level,'ai_instructions':'Focus on constraints.'}
                archive=Path(tmp)/level;begin=len(calls);text=draft.generate(payload,archive)
                for i in range(85):self.assertIn(f'TOPIC_{i}',text)
                self.assertNotIn('EXCLUDED_SECRET',text)
                self.assertIn('User-corrected wording',text)
                self.assertTrue(all((tokens<=limit<=tokens+1600) if 'Every supplied topic_id' in prompt else limit==tokens for prompt,limit in calls[begin:]))
                self.assertIn('Focus on constraints.',calls[-1][0])
                before=len(calls);self.assertEqual(draft.generate(payload,archive),text);self.assertEqual(len(calls),before)

class ConciseWording(unittest.TestCase):
    def test_refinement_keeps_coverage_and_failure_keeps_valid_draft(self):
        outer=self
        for broken in [False,True]:
            calls=[]
            class Client:
                def __init__(self,args,archive):self.args=args;self.archive=archive
                def discover(self):test_review.report.save(self.archive/'model_info.json',{'fixture':True})
                def generate(self,prompt,label,system,schema=None):
                    calls.append(label)
                    data=json.loads(prompt.split('DATA:\n',1)[1].split('\nStyle refinement:',1)[0])
                    if 'sections' not in schema.get('properties',{}):return {'recap':'Supported technical evidence and conditions.'}
                    ids=[sid for row in data['source'] for sid in row.get('topic_ids',[row.get('topic_id')])]
                    if 'Style refinement:' in prompt:
                        if broken:raise test_review.report.ReportError('Synthetic wording refinement failure')
                        text=' '.join('fact'+str(i) for i in range(750))
                    else:text=' '.join('fact'+str(i) for i in range(1200))
                    return {'sections':[{'topic_ids':ids,'text':text}]}
            payload={'metadata':{},'detail_level':'short','transcript':{'segments':[{'start':i*60,'end':i*60+30,'text':'Technical source facts. '*200} for i in range(30)]}}
            with tempfile.TemporaryDirectory() as tmp,patch.object(draft.report,'Ollama',Client):
                text=draft.generate(payload,Path(tmp));self.assertEqual(len(text.split()),1200 if broken else 750)
                self.assertTrue(any('concise wording' in label for label in calls))
                n=len(calls);self.assertEqual(draft.generate(payload,Path(tmp)),text);self.assertEqual(len(calls),n)

class MeetingWideReconciliation(unittest.TestCase):
    def test_optional_wording_runs_only_on_complete_meeting_not_intermediate_batches(self):
        labels=[];pack=draft.report.pack
        def two_batches(rows,budget):
            if rows and 'topic_id' in rows[0]:
                middle=len(rows)//2;return [rows[:middle],rows[middle:]]
            return pack(rows,budget)
        class Client:
            def __init__(self,args,archive):self.args=args;self.archive=archive
            def discover(self):test_review.report.save(self.archive/'model_info.json',{'fixture':True})
            def generate(self,prompt,label,system,schema=None):
                labels.append(label)
                if 'sections' not in schema.get('properties',{}):return {'recap':'Supported facts.\n\nSupported conditions.'}
                data=json.loads(prompt.split('DATA:\n',1)[1].split('\nStyle refinement:',1)[0])
                ids=[sid for row in data['source'] for sid in row.get('topic_ids',[row.get('topic_id')])]
                return {'sections':[{'topic_ids':ids,'text':'v '*(1688 if 'Style refinement:' in prompt else 2200)}]}
        payload={'metadata':{},'detail_level':'long','transcript':{'segments':[{'start':i*60,'end':i*60+30,'text':'Technical source facts. '*200} for i in range(30)]}}
        with tempfile.TemporaryDirectory() as tmp,patch.object(draft.report,'Ollama',Client),patch.object(draft.report,'pack',two_batches):
            draft.generate(payload,Path(tmp))
        self.assertEqual([label for label in labels if 'concise wording' in label],['Reconcile complete meeting — concise wording'])

    def test_all_batches_reconcile_without_losing_source_topic_ids(self):
        labels=[]
        class Client:
            def __init__(self,args,archive):self.args=args;self.archive=archive
            def discover(self):test_review.report.save(self.archive/'model_info.json',{'fixture':True})
            def generate(self,prompt,label,system,schema=None):
                labels.append(label);data=json.loads(prompt.split('DATA:\n',1)[1].split('\nStyle refinement:',1)[0])
                self_outer.assertLessEqual(len((system+prompt).encode())+self.args.output_tokens+self.args.token_safety,self.args.context)
                if 'sections' in schema.get('properties',{}):
                    ids=[sid for row in data['source'] for sid in row.get('topic_ids',[row.get('topic_id')])]
                    return {'sections':[{'topic_ids':ids,'text':'Reconciled outcomes preserve later qualifications.'}]}
                return {'recap':'\n\n'.join('Technical fact '+str(i)+': '+('supported evidence '*80) for i in range(12))}
        self_outer=self
        payload={'metadata':{},'detail_level':'long','transcript':{'segments':[{'start':i*60,'end':i*60+30,'text':'Technical source facts. '*200} for i in range(30)]}}
        with tempfile.TemporaryDirectory() as tmp,patch.object(draft.report,'Ollama',Client):
            text=draft.generate(payload,Path(tmp));meta=json.loads((Path(tmp)/'generation.json').read_text())
            self.assertGreater(meta['consolidation_batches'],1);self.assertTrue(meta['global_reconciled'])
            self.assertIn('Reconcile complete meeting',labels);self.assertIn('later qualifications',text)

class WorkingNoteFiltering(unittest.TestCase):
    def test_empty_labels_and_model_status_are_not_facts(self):
        self.assertEqual(draft.topic_paragraphs('### Thematic Outcomes\n\n**Technical Evolution and Core Competencies**'),[])
        self.assertEqual(draft.topic_paragraphs('The provided transcript segment contains no substantive information, technical discussions, or actionable items. It consists of fragmented recognitions. No topics were identified for summary.'),[])
        self.assertIn('No specific actions or deadlines were established.',draft.topic_paragraphs('### Outcomes\n\nNo specific actions or deadlines were established.')[0])
        self.assertIn('TLS enabled',draft.topic_paragraphs('### Outcomes\n\n**TLS enabled**')[0])
        self.assertIn('team found',draft.topic_paragraphs('The team found the supplied transcript contains no substantive information and agreed to rerecord it.')[0])

class AttributionValidation(unittest.TestCase):
    def test_attendees_are_not_speaker_identity_but_explicit_named_actions_are_evidence(self):
        payload={'metadata':{'participants':['Alice Example','Elena']},'transcript':{'segments':[{'start':0,'end':5,'text':'I worked on compilers for ten years.'},{'start':5,'end':10,'text':'Elena owns rollback validation.'}]}}
        self.assertTrue(draft.unsupported_names(payload,'Alice described ten years of compiler work.'))
        payload['transcript']['segments'].append({'start':10,'end':15,'text':'Excluded speech','speaker_confirmed':True,'speaker_name':'Alice Example','excluded_from_recap':True})
        self.assertTrue(draft.unsupported_names(payload,'Alice described ten years of compiler work.'))
        self.assertTrue(draft.unsupported_names(payload,'Alice Example worked on compilers.'))
        payload['transcript']['segments'][0]['review_note']='Alice Example owns the follow-up.'
        self.assertFalse(draft.unsupported_names(payload,'Alice Example owns the follow-up.'))
        payload['transcript']['segments'][0].pop('review_note')
        self.assertFalse(draft.unsupported_names(payload,'One participant described compiler experience. Elena owns rollback validation.'))
        payload['transcript']['segments'][0].update(speaker_confirmed=True,speaker_name='Alice Example')
        self.assertFalse(draft.unsupported_names(payload,'Alice described compiler experience.'))
    def test_model_context_omits_attendee_and_title_cues_and_repairs_bad_attribution(self):
        calls=[]
        class Client:
            def __init__(self,args,archive):self.args=args;self.archive=archive
            def discover(self):test_review.report.save(self.archive/'model_info.json',{'fixture':True})
            def generate(self,prompt,label,system,schema=None):
                calls.append(prompt)
                self_outer.assertNotIn('Meeting with Alice',prompt)
                self_outer.assertNotIn('"participants"',prompt)
                if len(calls)==1:return {'recap':'Alice described ten years of compiler work.'}
                self_outer.assertIn('Unconfirmed participant attribution',prompt)
                return {'recap':'One participant described compiler experience; identity remains unconfirmed.'}
        self_outer=self
        payload={'metadata':{'participants':['Alice'],'meeting_title':'Meeting with Alice'},'transcript':{'segments':[{'start':0,'end':5,'text':'I worked on compilers for ten years.'}]}}
        with tempfile.TemporaryDirectory() as tmp,patch.object(draft.report,'Ollama',Client):
            self.assertIn('One participant',draft.generate(payload,Path(tmp)))
            self.assertEqual(len(calls),2)

class CoverageValidation(unittest.TestCase):
    def test_missing_and_duplicate_topics_fail_closed_then_reuse_source_cache(self):
        calls=[];mode=['missing']
        class Client:
            def __init__(self,args,archive):self.args=args;self.archive=archive
            def discover(self):test_review.report.save(self.archive/'model_info.json',{'fixture':True})
            def generate(self,prompt,label,system,schema=None):
                self_outer.assertLessEqual(len((system+prompt).encode())+self.args.output_tokens+self.args.token_safety,self.args.context)
                calls.append(label);data=json.loads(prompt.split('DATA:\n',1)[1].split('\nStyle refinement:',1)[0].split('\nValidation detail:',1)[0].split('\nRecovery instruction:',1)[0])
                if 'sections' in schema.get('properties',{}):
                    ids=[sid for row in data['source'] for sid in row.get('topic_ids',[row.get('topic_id')])]
                    if mode[0]=='missing':ids=ids[:max(1,len(ids)//2)]
                    if mode[0]=='small-gap':ids=ids[:-1]
                    if mode[0]=='duplicate':ids=ids+[ids[0]]
                    return {'sections':[{'topic_ids':ids,'text':'All supported outcomes require review.'}]}
                return {'recap':'## Topic\n\nSupported technical outcomes.\n\nConditional follow-up.'}
        self_outer=self
        payload={'transcript':{'segments':[{'start':i*60,'end':i*60+30,'text':'Technical facts and constraints. '*200} for i in range(25)]},'metadata':{},'detail_level':'long'}
        with tempfile.TemporaryDirectory() as tmp,patch.object(draft.report,'Ollama',Client):
            with self.assertRaisesRegex(ValueError,'coverage'):draft.generate(payload,Path(tmp))
            source_calls=sum(label.startswith('Review source') for label in calls)
            mode[0]='duplicate'
            with self.assertRaisesRegex(ValueError,'coverage'):draft.generate(payload,Path(tmp))
            self.assertEqual(sum(label.startswith('Review source') for label in calls),source_calls)
            mode[0]='small-gap';self.assertIn('supported outcomes',draft.generate(payload,Path(tmp)))
            self.assertEqual(sum(label.startswith('Review source') for label in calls),source_calls)
            metrics=json.loads((Path(tmp)/'generation.json').read_text());self.assertGreater(metrics['covered_topics'],1)
            self.assertIn('coverage_recovered',(Path(tmp)/'events.jsonl').read_text())

class PartitionedCoverageRecovery(unittest.TestCase):
    def test_large_invalid_merge_recovers_in_disjoint_bounded_groups_and_reuses_cache(self):
        calls=[]
        class Client:
            def __init__(self,args,archive):self.args=args;self.archive=archive
            def discover(self):test_review.report.save(self.archive/'model_info.json',{'fixture':True})
            def generate(self,prompt,label,system,schema=None):
                calls.append(label)
                data=json.loads(prompt.split('DATA:\n',1)[1].split('\nStyle refinement:',1)[0].split('\nValidation detail:',1)[0])
                if 'sections' not in schema.get('properties',{}):return {'recap':'\n\n'.join('Supported fact '+str(i)+'.' for i in range(40))}
                ids=[sid for row in data['source'] for sid in row.get('topic_ids',[row.get('topic_id')])]
                if len(ids)>24:return {'sections':[{'topic_ids':ids[:len(ids)//2]+ids[:1],'text':'Invalid large merge.'}]}
                return {'sections':[{'topic_ids':ids,'text':'\n\n'.join(row['text'] for row in data['source'])}]}
        payload={'metadata':{},'detail_level':'long','transcript':{'segments':[{'start':i*60,'end':i*60+30,'text':'Technical source facts. '*200} for i in range(30)]}}
        with tempfile.TemporaryDirectory() as tmp,patch.object(draft.report,'Ollama',Client):
            archive=Path(tmp);text=draft.generate(payload,archive)
            self.assertIn('Supported fact 39.',text)
            self.assertNotIn('Invalid large merge.',text)
            self.assertTrue(any('coverage part' in label for label in calls))
            self.assertIn('coverage_partitioned',(archive/'events.jsonl').read_text())
            count=len(calls);self.assertEqual(draft.generate(payload,archive),text);self.assertEqual(len(calls),count)
            self.assertTrue(json.loads((archive/'draft-partitions.json').read_text()))

class RegenerationHTTP(unittest.TestCase):
    setUp=test_dashboard.DashboardTests.setUp
    action=test_dashboard.DashboardTests.action
    request=test_dashboard.DashboardTests.request
    session=test_dashboard.DashboardTests.session
    def test_real_route_auth_csrf_and_durable_queue(self):
        route='api/meetings/'+self.job['id'];obj={'action':'regenerate','revision':1,'detail_level':'medium','ai_instructions':'Show dependencies.'}
        self.action('approve')
        self.assertEqual(self.request(route,obj)[0],403)
        self.assertEqual(self.request(route,obj,cookie='bob-session',csrf=self.session('bob-session'))[0],404)
        status,value,_=self.request(route,obj,csrf=self.session())
        self.assertEqual(status,200);self.assertIsNotNone(value['review']['pending']);self.assertEqual(value['review']['pending_detail_level'],'medium')
        self.assertEqual(value['meeting']['approved_revision'],1)
        with test_review.review.connection(self.root) as db:
            task=json.loads(db.execute('select payload from tasks').fetchone()[0])
        self.assertEqual(task['detail_level'],'medium');self.assertEqual(task['ai_instructions'],'Show dependencies.')
        test_review.review.process_next(self.root,lambda p,w:'Reviewed-source generated draft')
        status,value,_=self.request(route)
        self.assertEqual(value['review']['detail_level'],'medium')
        self.assertEqual(value['meeting']['approved_revision'],1)

if __name__=='__main__':unittest.main()




