"""Deterministic RAM pressure, context budgeting and durable resume checks."""
import itertools
import json
import os
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import test_review
import meeting_draft as draft
import recap_resources as resources


class RAMPolicy(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.archive=Path(self.temp.name)

    def test_context_tiers_and_resident_headroom(self):
        for available,resident,expected in [(30000,0,32768),(18000,0,16384),(5000,32768,32768)]:
            with self.subTest(available=available,resident=resident),tempfile.TemporaryDirectory() as tmp:
                with patch.object(resources,'probe',return_value={'available_mb':available,'weights_mb':8000,'resident_context':resident}):
                    plan=resources.plan('gemma','http://local',32768,14000,Path(tmp))
                    self.assertEqual(plan['context'],expected);self.assertEqual(plan['headroom_mb'],2048)

    def test_insufficient_ram_and_feedback_do_not_silently_truncate(self):
        for available,resident,minimum in [(14000,0,14000),(1500,32768,14000),(18000,0,20000)]:
            with self.subTest(available=available,resident=resident,minimum=minimum):
                with patch.object(resources,'probe',return_value={'available_mb':available,'weights_mb':8000,'resident_context':resident}):
                    with self.assertRaises(resources.ResourceWait):resources.plan('gemma','http://local',32768,minimum,self.archive)

    def test_resume_keeps_context_for_completed_cache(self):
        (self.archive/'request_0001.json').write_text(json.dumps({'options':{'num_ctx':32768}}))
        with patch.object(resources,'probe',return_value={'available_mb':18000,'weights_mb':8000,'resident_context':0}):
            with self.assertRaises(resources.ResourceWait):resources.plan('gemma','http://local',32768,14000,self.archive)
        with patch.object(resources,'probe',return_value={'available_mb':30000,'weights_mb':8000,'resident_context':0}):
            self.assertEqual(resources.plan('gemma','http://local',32768,14000,self.archive)['context'],32768)

    def test_unknown_memory_or_model_state_waits_safely(self):
        with patch.object(resources,'available_mb',return_value=None),patch.object(resources,'api') as api:
            with self.assertRaises(resources.ResourceWait):resources.probe('gemma','http://local')
            api.assert_not_called()
        with patch.object(resources,'available_mb',return_value=30000),patch.object(resources,'api',side_effect=OSError('temporary outage')):
            with self.assertRaises(resources.ResourceWait):resources.probe('gemma','http://local')
        with patch.object(resources,'available_mb',return_value=1000):
            with self.assertRaises(resources.ResourceWait):resources.watch(4096)

    def test_headroom_setting_is_bounded(self):
        with patch.dict(os.environ,{'RECAP_RAM_HEADROOM_MB':'1'}):
            with self.assertRaises(ValueError):resources.headroom_mb()

    def test_measured_gemma_layout_preserves_32k_without_inflated_kv_budget(self):
        prefix='gemma4.attention.'
        info={'general.architecture':'gemma4','gemma4.block_count':48,
              prefix+'head_count_kv':[1 if i%6==5 else 8 for i in range(48)],
              prefix+'sliding_window_pattern':[i%6!=5 for i in range(48)],prefix+'sliding_window':1024,
              prefix+'key_length':512,prefix+'value_length':512,prefix+'key_length_swa':256,prefix+'value_length_swa':256}
        self.assertEqual(resources.kv_mb(32768,info),1152);self.assertEqual(resources.kv_mb(16384,info),896)
        with patch.object(resources,'probe',return_value={'available_mb':13000,'weights_mb':7650,'resident_context':0,'model_info':info}):
            self.assertEqual(resources.plan('gemma','http://local',32768,14000,self.archive)['context'],32768)

    def test_transient_dip_recovers_but_sustained_or_critical_pressure_pauses(self):
        state={}
        with patch.object(resources,'available_mb',side_effect=[1800,3000,1800,1800]):
            resources.watch(2048,state);resources.watch(2048,state);resources.watch(2048,state)
            with self.assertRaises(resources.ResourceWait):resources.watch(2048,state)
        with patch.object(resources,'available_mb',return_value=900):
            with self.assertRaises(resources.ResourceWait):resources.watch(2048,{})


class GenerationRAM(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'SMARTINIS_RECAP_RAM_GUARD':'1','REVIEW_CONTEXT':'32768'});self.env.start();self.addCleanup(self.env.stop)

    def test_smaller_context_preserves_source_and_level_budgets(self):
        calls=[];outer=self
        class Client:
            def __init__(self,args,archive):self.args=args;self.archive=archive
            def discover(self):draft.report.save(self.archive/'model_info.json',{'fixture':True})
            def generate(self,prompt,label,system,schema=None):
                outer.assertEqual(self.args.context,16384)
                outer.assertLessEqual(len((system+prompt).encode())+self.args.output_tokens+self.args.token_safety,16384)
                calls.append((label,prompt,self.args.output_tokens))
                data=json.loads(prompt.split('DATA:\n',1)[1].split('\nStyle refinement:',1)[0])
                if 'sections' in schema.get('properties',{}):
                    ids=[sid for row in data['source'] for sid in row.get('topic_ids',[row.get('topic_id')])]
                    return {'sections':[{'topic_ids':ids,'text':'\n\n'.join(row['text'] for row in data['source'])}]}
                return {'recap':' '.join(row['text'].split()[0] for row in data['source'])}
        transcript={'segments':[{'start':i*60,'end':i*60+30,'text':f'TOPIC_{i} '+('technical evidence '*80)} for i in range(85)]}
        snapshot={'available_mb':18000,'weights_mb':8000,'resident_context':0}
        with tempfile.TemporaryDirectory() as tmp,patch.object(resources,'probe',return_value=snapshot),patch.object(draft.report,'Ollama',Client):
            for level,tokens in [('short',2400),('medium',3840),('long',6000)]:
                calls.clear();payload={'metadata':{},'transcript':transcript,'detail_level':level}
                text=draft.generate(payload,Path(tmp)/level)
                for i in range(85):self.assertIn(f'TOPIC_{i}',text)
                self.assertTrue(all(limit>=tokens for _,_,limit in calls))
                self.assertEqual(json.loads((Path(tmp)/level/'generation.json').read_text())['context'],16384)

    def test_pressure_keeps_completed_source_cache_for_resume(self):
        calls=[];pressure=[True]
        class Client:
            def __init__(self,args,archive):self.args=args;self.archive=archive
            def discover(self):draft.report.save(self.archive/'model_info.json',{'fixture':True})
            def generate(self,prompt,label,system,schema=None):
                calls.append(label)
                if pressure[0] and label.startswith('Review source 2/'):
                    pressure[0]=False;raise resources.ResourceWait('Synthetic pressure',1000,4096)
                data=json.loads(prompt.split('DATA:\n',1)[1].split('\nStyle refinement:',1)[0])
                if 'sections' in schema.get('properties',{}):
                    return {'sections':[{'topic_ids':[sid for row in data['source'] for sid in row.get('topic_ids',[row.get('topic_id')])],'text':'All supported facts retained.'}]}
                return {'recap':'Supported facts.'}
        payload={'metadata':{},'transcript':{'segments':[{'start':i*60,'end':i*60+30,'text':'Technical evidence. '*300} for i in range(30)]}}
        with tempfile.TemporaryDirectory() as tmp,patch.object(resources,'probe',return_value={'available_mb':30000,'weights_mb':8000,'resident_context':32768}),patch.object(resources,'release') as release,patch.object(draft.report,'Ollama',Client):
            archive=Path(tmp)
            with self.assertRaises(resources.ResourceWait):draft.generate(payload,archive)
            self.assertTrue(json.loads((archive/'draft-cache.json').read_text()));release.assert_called_once()
            draft.generate(payload,archive)
            self.assertEqual(sum(label.startswith('Review source 1/') for label in calls),1)

    def test_stream_memory_guard_retains_partial_and_propagates_wait(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def __iter__(self):return iter([json.dumps({'message':{'content':'{"recap":"partial'}}).encode()])
        with tempfile.TemporaryDirectory() as tmp:
            archive=Path(tmp);args=draft.report.parser().parse_args([str(archive/'source.json')])
            args.capture_partial=True;args.memory_guard=Mock(side_effect=resources.ResourceWait('Pressure',1000,4096))
            client=draft.report.Ollama(args,archive);ticks=itertools.count(step=3)
            with patch.object(client,'request',return_value=Response()),patch.object(draft.report.time,'monotonic',side_effect=lambda:next(ticks)):
                with self.assertRaises(resources.ResourceWait):client.generate('source','test')
            self.assertTrue(list(archive.glob('stream_*.json')));self.assertFalse(list(archive.glob('response_*.json')))

    def test_low_ram_during_optional_wording_keeps_complete_draft(self):
        class Client:
            def __init__(self,args,archive):self.args=args;self.archive=archive
            def discover(self):draft.report.save(self.archive/'model_info.json',{'fixture':True})
            def generate(self,prompt,label,system,schema=None):
                if 'Style refinement:' in prompt:raise resources.ResourceWait('Pressure',1000,4096)
                if 'sections' not in schema.get('properties',{}):return {'recap':'Supported facts.'}
                data=json.loads(prompt.split('DATA:\n',1)[1])
                ids=[sid for row in data['source'] for sid in row.get('topic_ids',[row.get('topic_id')])]
                return {'sections':[{'topic_ids':ids,'text':'fact '*1200}]}
        payload={'metadata':{},'transcript':{'segments':[{'start':i*60,'end':i*60+30,'text':'Technical evidence. '*200} for i in range(30)]}}
        with tempfile.TemporaryDirectory() as tmp,patch.object(resources,'probe',return_value={'available_mb':30000,'weights_mb':8000,'resident_context':32768}),patch.object(resources,'release') as release,patch.object(draft.report,'Ollama',Client):
            self.assertEqual(len(draft.generate(payload,Path(tmp)).split()),1200);release.assert_called_once()


class DurableRAMWait(unittest.TestCase):
    setUp=test_review.ReviewTests.setUp
    action=test_review.ReviewTests.action
    def test_pause_does_not_fail_or_change_approval_then_resumes_new_draft(self):
        self.action('approve');self.action('regenerate',detail_level='medium')
        def pause(payload,work):raise resources.ResourceWait('Pressure',1000,4096)
        test_review.review.process_next(self.root,pause)
        view=test_review.review.view(self.root,self.job['id'],'alice')
        self.assertEqual(view['revision'],1);self.assertEqual(view['last_approved']['revision'],1);self.assertIsNotNone(view['pending'])
        work=self.folder/'review-work'/view['pending']
        self.assertFalse((work/'failure.json').exists())
        with test_review.review.connection(self.root) as db:
            self.assertEqual(db.execute('select status from tasks').fetchone()[0],'queued')
            self.assertEqual(db.execute("select count(*) from notices where key like 'revision-failed:%'").fetchone()[0],0)
        called=Mock(return_value='Recovered supported draft')
        self.assertFalse(test_review.review.process_next(self.root,called));called.assert_not_called()
        test_review.review.recover(self.root)
        draft.report.save(work/'resource-wait.json',{'waiting':True,'retry_after':0})
        self.assertTrue(test_review.review.process_next(self.root,called))
        final=test_review.review.view(self.root,self.job['id'],'alice')
        self.assertEqual(final['revision'],2);self.assertEqual(final['last_approved']['revision'],1)
        self.assertFalse(json.loads((work/'resource-wait.json').read_text())['waiting'])


class SchedulerRAMAdmission(unittest.TestCase):
    setUp=test_review.ReviewTests.setUp
    action=test_review.ReviewTests.action
    def test_resident_recap_is_not_blocked_by_unrelated_8gb_gate(self):
        import notes_dispatch
        self.action('regenerate')
        with patch.dict(os.environ,{'SMARTINIS_RECAP_RAM_GUARD':'1'}),patch.object(notes_dispatch.notes,'oldest',return_value=None),patch.object(notes_dispatch.notes_models,'available_mb',return_value=6000),patch.object(test_review.review,'process_next',return_value=True) as run:
            self.assertTrue(notes_dispatch.step(test_review.worker));run.assert_called_once()
        for kind,enabled in [('meeting-recap','0'),('notes','1'),('audio','1')]:
            with self.subTest(kind=kind,enabled=enabled),patch.dict(os.environ,{'SMARTINIS_RECAP_RAM_GUARD':enabled}),patch.object(notes_dispatch,'choose',return_value=kind),patch.object(notes_dispatch.notes,'oldest',return_value=None),patch.object(notes_dispatch.notes_models,'available_mb',return_value=6000),patch.object(test_review.review,'process_next') as run:
                self.assertFalse(notes_dispatch.step(test_review.worker));run.assert_not_called()

    def test_memory_paused_recap_does_not_block_ready_notes(self):
        import notes_dispatch
        self.action('regenerate')
        def pause(payload,work):raise resources.ResourceWait('Pressure',1000,2048)
        test_review.review.process_next(self.root,pause)
        self.assertIsNone(test_review.review.oldest_ready(self.root))
        with patch.object(notes_dispatch.notes,'oldest',return_value=1),patch.object(notes_dispatch.notes_models,'available_mb',return_value=20000),patch.object(notes_dispatch.notes,'process_next',return_value=True) as note,patch.object(test_review.review,'process_next') as recap:
            self.assertTrue(notes_dispatch.step(test_review.worker));note.assert_called_once();recap.assert_not_called()


@unittest.skipIf(os.name=='nt','Server deployment uses Linux flock')
class RAMDeployment(unittest.TestCase):
    def setUp(self):
        import deploy_recap_ram_guard as installer
        self.installer=installer;self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'meetings';self.root.mkdir();self.target=self.base/'runtime';self.target.mkdir();self.source=self.base/'stage';self.source.mkdir()
        (self.target/'old.py').write_text('old');(self.source/'old.py').write_text('new');(self.source/'new.py').write_text('resource guard')
        with sqlite3.connect(self.root/'reviews.sqlite3') as db:db.executescript('create table tasks(status text);create table marker(value text);')
        from contextlib import ExitStack
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        values={'BASE':self.base,'ROOT':self.root,'TARGET':self.target,'SOURCE':self.source,'FILES':['old.py','new.py'],'BEFORE':{'old.py':installer.sha(self.target/'old.py'),'new.py':None}}
        for name,value in values.items():self.stack.enter_context(patch.object(installer,name,value))
        self.stack.enter_context(patch.object(installer,'restart'));self.stack.enter_context(patch.object(installer,'healthy',return_value=True))

    def test_code_rollback_removes_only_new_module_and_keeps_later_db_work(self):
        result=self.installer.apply();self.assertEqual((self.target/'old.py').read_text(),'new')
        with sqlite3.connect(self.root/'reviews.sqlite3') as db:db.execute("insert into marker values ('later user work')")
        self.installer.apply(Path(result['backup']))
        self.assertEqual((self.target/'old.py').read_text(),'old');self.assertFalse((self.target/'new.py').exists())
        with sqlite3.connect(self.root/'reviews.sqlite3') as db:self.assertEqual(db.execute('select value from marker').fetchone()[0],'later user work')

    def test_refuses_active_work_or_changed_code(self):
        with sqlite3.connect(self.root/'reviews.sqlite3') as db:db.execute("insert into tasks values ('queued')")
        with self.assertRaises(RuntimeError):self.installer.apply()
        with sqlite3.connect(self.root/'reviews.sqlite3') as db:db.execute('delete from tasks')
        (self.target/'old.py').write_text('other local work')
        with self.assertRaises(AssertionError):self.installer.apply()
        self.assertFalse((self.target/'new.py').exists())


if __name__=='__main__':unittest.main()
