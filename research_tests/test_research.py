from contextlib import closing
from pathlib import Path
import json
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import heavy_gate
import research_jobs as jobs
from research_privacy import ApprovedQuery, Guard, PrivacyBlocked, QueryReviewRequired, plan
from research_web import PublicWeb, Text, target, readable_url,excerpts,recipe_text
from research_question import answer_style

QUESTION='Based on my latest discussions about JCA, what are the main technical risks, and what current industry practices could help mitigate them?'
PRIVATE='Alice SecretName discussed JCA and ProjectAurora. She said "the midnight migration uses the hidden contract".'


class Research(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);jobs.init(self.root);self.calls=[];self.sent=[]
    def submit(self,mode='auto',key='one',question=QUESTION):return jobs.submit(self.root,'owner',key,question,mode)
    def model(self,task,payload):
        self.calls.append((task,payload))
        if task=='route':return {'knowledge':True,'web':True}
        if task=='abstract':return {'brief':'Enterprise software integration reliability and migration risk mitigation'}
        if task=='plan':
            if 'PlayStation' in payload['public_brief'] or 'PS3' in payload['public_brief']:return {'queries':['PlayStation 3 launch date Japan Italy Sony']}
            return {'queries':['enterprise integration migration risk mitigation','API compatibility contract testing guidance']}
        if task=='privacy':return {'decision':'safe'}
        if task=='compare':return {'comparison':'Separate evidence from interpretation.'}
        return {'findings':[{'text':'Synthetic evidence comparison','sources':[s['id'] for s in payload['evidence']],'type':'inference'}],
                'uncertainties':'Synthetic fixture, not real project findings.'}
    def knowledge(self,owner,question):return [{'kind':'knowledge','text':PRIVATE,'title':'Synthetic approval','revision':1,'sha256':'a'*64,'url':''}]
    def web(self):
        outer=self
        class Web:
            def search(self,query):
                outer.assertIsInstance(query,ApprovedQuery);outer.sent.append(query.text)
                return ['https://docs.example.org/'+str(len(outer.sent))]
            def read(self,url):return 'Synthetic public guidance for software integration and migration.'
        return Web()
    def test_three_modes_and_all_required_stage_transitions(self):
        for mode,expected in [('knowledge',{'knowledge'}),('web',{'web'}),('auto',{'knowledge','web'})]:
            self.calls=[];self.sent=[];jid=self.submit(mode,key=mode);stages=[];real=jobs.update
            def record(*args,**kwargs):stages.append(args[2]);return real(*args,**kwargs)
            with patch.object(jobs,'update',side_effect=record):jobs.tick(self.root,self.model,self.knowledge,self.web())
            value=jobs.get(self.root,'owner',jid)
            self.assertEqual(value['status'],'completed',value['stage'])
            self.assertEqual({s['kind'] for s in value['result']['sources']},expected)
            self.assertIn(jobs.STAGES['comparing'],stages);self.assertIn(jobs.STAGES['drafting'],stages)
            for task,payload in self.calls:
                if task=='plan':
                    self.assertNotIn('private_evidence',payload);self.assertNotIn('JCA',json.dumps(payload));self.assertNotIn('SecretName',json.dumps(payload))
            self.assertNotIn('JCA',str(self.sent));self.assertNotIn('Alice',str(self.sent))
            if mode=='knowledge':self.assertEqual(self.sent,[]);self.assertNotIn('plan',[c[0] for c in self.calls])
            else:self.assertIn(jobs.STAGES['privacy'],stages);self.assertIn(jobs.STAGES['searching'],stages);self.assertIn(jobs.STAGES['reading'],stages)
    def test_general_ps3_question_has_no_topic_restriction_or_private_retrieval(self):
        jid=self.submit('web',question='When was the PS3 released in Italy and Japan?')
        def forbidden(*args):raise AssertionError('Web-only must not retrieve private evidence')
        jobs.tick(self.root,self.model,forbidden,self.web())
        self.assertEqual(jobs.get(self.root,'owner',jid)['status'],'completed')
        self.assertEqual(self.sent,['PlayStation 3 launch date Japan Italy Sony'])
    def test_model_approval_never_bypasses_private_identifier_block(self):
        jid=self.submit('web');base=self.model
        def malicious(task,payload):return {'queries':['JCA ProjectAurora contract']} if task=='plan' else base(task,payload)
        jobs.tick(self.root,malicious,self.knowledge,self.web())
        self.assertEqual(self.sent,[]);self.assertEqual(jobs.get(self.root,'owner',jid)['status'],'needs_review')
    def test_uncertain_privacy_verdict_sends_no_query(self):
        jid=self.submit('web',question='PlayStation launch dates Japan Italy');base=self.model
        def uncertain(task,payload):return {'decision':'uncertain'} if task=='privacy' else base(task,payload)
        jobs.tick(self.root,uncertain,self.knowledge,self.web())
        self.assertEqual(self.sent,[]);self.assertEqual(jobs.get(self.root,'owner',jid)['status'],'needs_review')
    def test_hybrid_privacy_failure_can_return_private_only_with_warning(self):
        jid=self.submit();base=self.model
        def bad(task,payload):return {'brief':'password=Secret123 from private notes'} if task=='abstract' else base(task,payload)
        jobs.tick(self.root,bad,self.knowledge,self.web())
        result=jobs.get(self.root,'owner',jid)['result']
        self.assertEqual(self.sent,[]);self.assertTrue(any('privacy' in w for w in result['warnings']))
        self.assertEqual({s['kind'] for s in result['sources']},{'knowledge'})
    def pause(self):
        jid=self.submit('web',question='PlayStation release dates Japan Italy');base=self.model
        def uncertain(task,payload):return {'decision':'uncertain'} if task=='privacy' else base(task,payload)
        jobs.tick(self.root,uncertain,self.knowledge,self.web())
        value=jobs.get(self.root,'owner',jid);self.assertEqual(value['status'],'needs_review')
        return jid,value['result']['review']
    def test_exact_query_approval_resumes_without_regeneration_and_is_owner_scoped(self):
        jid,review=self.pause();self.assertEqual(self.sent,[])
        with heavy_gate.slot(self.root) as acquired:self.assertTrue(acquired)
        with self.assertRaises(KeyError):jobs.review_queries(self.root,'other',jid,'approve',review['digest'][:12])
        with self.assertRaises(ValueError):jobs.review_queries(self.root,'owner',jid,'approve','0'*12)
        jobs.review_queries(self.root,'owner',jid,'approve',review['digest'][:12])
        base=self.model
        def resume(task,payload):
            self.assertNotIn(task,('plan','privacy','abstract','route'))
            return base(task,payload)
        jobs.tick(self.root,resume,self.knowledge,self.web())
        self.assertEqual(self.sent,review['queries'])
        self.assertEqual(jobs.get(self.root,'owner',jid)['status'],'completed')
        with self.assertRaises(ValueError):jobs.review_queries(self.root,'owner',jid,'approve',review['digest'][:12])
    def test_rejection_and_expiry_send_nothing(self):
        jid,review=self.pause();jobs.review_queries(self.root,'owner',jid,'reject')
        self.assertEqual(jobs.get(self.root,'owner',jid)['status'],'cancelled');self.assertEqual(self.sent,[])
        jid=self.submit('web',key='expired',question='public research')
        payload={'review':{'queries':['public research'],'digest':'x','expires':0}}
        jobs.update(self.root,jid,'waiting','needs_review',payload)
        with self.assertRaises(ValueError):jobs.review_queries(self.root,'owner',jid,'approve','0'*12)
    def test_review_query_tampering_is_detected(self):
        jid,review=self.pause()
        with closing(jobs.connect(self.root)) as db,db:
            value=json.loads(db.execute('SELECT result FROM research_jobs WHERE id=?',(jid,)).fetchone()[0])
            value['review']['queries']=['changed query']
            db.execute('UPDATE research_jobs SET result=? WHERE id=?',(json.dumps(value),jid))
        with self.assertRaises(ValueError):jobs.review_queries(self.root,'owner',jid,'approve',review['digest'][:12])
    def test_missing_privacy_index_fails_closed(self):
        class Knowledge:
            def identifiers(self,owner):raise OSError('Unavailable')
        jid=self.submit('web',question='public question')
        jobs.tick(self.root,self.model,Knowledge(),self.web())
        self.assertEqual(self.sent,[]);self.assertIn('Privacy check',jobs.get(self.root,'owner',jid)['stage'])
    def test_idempotency_ownership_restart_and_cancellation(self):
        jid=self.submit();self.assertEqual(jid,self.submit())
        with self.assertRaises(ValueError):jobs.submit(self.root,'owner','one','different','auto')
        with self.assertRaises(KeyError):jobs.get(self.root,'other',jid)
        with self.assertRaises(KeyError):jobs.cancel(self.root,'other',jid)
        jobs.cancel(self.root,'owner',jid);self.assertEqual(jobs.get(self.root,'owner',jid)['status'],'cancelled')
        jid=self.submit(key='restart');jobs.update(self.root,jid,'Planning');jobs.init(self.root)
        self.assertEqual(jobs.get(self.root,'owner',jid)['status'],'failed')
    def test_slot_and_explicit_blocking_reason(self):
        jid=self.submit()
        with heavy_gate.slot(self.root) as acquired:
            self.assertTrue(acquired);self.assertFalse(jobs.tick(self.root,self.model,self.knowledge,self.web()))
        self.assertIn('another protected workload',jobs.get(self.root,'owner',jid)['stage'])
        with closing(sqlite3.connect(self.root/'jobs.sqlite3')) as db,db:
            db.execute('CREATE TABLE jobs(state TEXT,detail TEXT)');db.execute('INSERT INTO jobs VALUES (?,?)',('transcribing','Identifying speakers on CPU; private file'))
        self.assertIn('speaker identification',jobs.busy_reason(self.root));self.assertNotIn('private file',jobs.busy_reason(self.root))
    def test_deadline_empty_sources_and_source_failures(self):
        jid=self.submit('knowledge');row={'id':jid,'owner':'owner','question':QUESTION,'mode':'knowledge'}
        with self.assertRaises(TimeoutError):jobs.run(self.root,row,self.model,self.knowledge,self.web(),clock=iter([0,601]).__next__)
        with self.assertRaises(jobs.NoEvidence):jobs.run(self.root,row,self.model,lambda *a:[],self.web())
        web=self.web();web.search=lambda q:(_ for _ in ()).throw(TimeoutError())
        jid=self.submit('auto',key='partial');jobs.tick(self.root,self.model,self.knowledge,web)
        self.assertEqual(jobs.get(self.root,'owner',jid)['status'],'completed')
    def test_search_retry_remains_within_three_requests(self):
        jid=self.submit('web',question='general integration migration guidance');web=self.web();attempts=[]
        def empty(query):attempts.append(query.text);return []
        web.search=empty
        with patch('research_jobs.time.sleep'):jobs.tick(self.root,self.model,self.knowledge,web)
        self.assertEqual(len(attempts),3);self.assertEqual(jobs.get(self.root,'owner',jid)['status'],'failed')
    def test_citations_cannot_be_invented_or_misclassified(self):
        for kind,refs in [('public',['K1']),('internal',['W1']),('inference',['W999'])]:
            with self.assertRaises(ValueError):jobs.validate_answer({'findings':[{'text':'claim','sources':refs,'type':kind}],'uncertainties':''},[{'id':'K1'},{'id':'W1'}])
    def test_fast_stage_events_are_durable_and_owner_scoped(self):
        jid=self.submit('web',question='PlayStation launch date Japan Italy')
        jobs.tick(self.root,self.model,self.knowledge,self.web())
        value=jobs.get(self.root,'owner',jid)
        history=[e['stage'] for e in value['events']]
        self.assertIn(jobs.STAGES['privacy'],history)
        self.assertIn(jobs.STAGES['searching'],history)
        self.assertIn(jobs.STAGES['reading'],history)
        with self.assertRaises(KeyError):jobs.get(self.root,'other',jid)


class Privacy(unittest.TestCase):
    def test_answer_shapes_are_generic_not_subject_permissions(self):
        for q in ['How to make a New York cheesecake?','How do I connect Excel to Power BI?','Give a recipe for soup','Instructions for making a paper airplane']:
            self.assertEqual(answer_style(q),'instructions')
        self.assertEqual(answer_style('Who was Ada Lovelace?'),'person')
        self.assertEqual(answer_style('When was the PS3 released?'),'dates')
        self.assertEqual(answer_style('Why is the sky blue?'),'facts')
    def test_uppercase_prose_is_not_mistaken_for_private_identifiers(self):
        guard=Guard('public question',[{'text':'THE API AND THE SOURCE ARE IN THE NOTES. JCA is private.'}])
        self.assertEqual(guard.check('the PlayStation launch in Japan and Italy'),'the PlayStation launch in Japan and Italy')
        with self.assertRaises(PrivacyBlocked):guard.check('JCA launch in Japan')
    def test_public_technology_in_private_notes_does_not_become_private_project(self):
        guard=Guard('public question',[{'text':'PYTHON EXCEL POWERBI and JCA are discussed.'}])
        guard.check('latest stable Python release')
        guard.check('connect Excel to Power BI')
        with self.assertRaises(PrivacyBlocked):guard.check('JCA latest discussion')
    def test_generic_title_case_is_not_a_private_name(self):
        guard=Guard('public question',[{'text':'Technical Risks and Business Planning are discussed with Alice Smith for ProjectAurora.'}])
        guard.check('technical risks business planning guidance')
        with self.assertRaises(PrivacyBlocked):guard.check('Alice Smith business planning')
        with self.assertRaises(PrivacyBlocked):guard.check('ProjectAurora planning')
    def test_public_architecture_terms_and_explicit_private_project_are_distinct(self):
        guard=Guard('public question',[{'text':'CLOUD GATEWAY MULTI LAYER and Service Layer are concepts.'}])
        guard.check('multi cloud gateway service layer architecture')
        private=Guard('public question',[{'text':'Project Cloud and ProjectCloud are internal codenames.'}])
        with self.assertRaises(PrivacyBlocked):private.check('Cloud project guidance')
        with self.assertRaises(PrivacyBlocked):private.check('ProjectCloud guidance')
    def test_literal_encoded_and_quoted_private_material_is_blocked(self):
        guard=Guard(QUESTION,[{'text':PRIVATE}],['Alice','SecretName','JCA'],sensitive=True)
        for query in ['JCA migration','Ａlice migration','J%43A migration','JСA migration','J C A migration',
                      'SkNB migration','4a4341 migration','ProjectAurora rollout','the midnight migration uses the hidden contract',
                      'my meetings project risks','person@example.org practices','password=Secret123 practices',
                      'https://internal.example.org','api_key=abcd1234','J\u200bCA migration']:
            with self.subTest(query=query):
                with self.assertRaises((PrivacyBlocked,QueryReviewRequired)):guard.approve([query],{'decision':'safe'})
        self.assertIsInstance(guard.approve(['enterprise integration migration reliability'],{'decision':'safe'})[0],ApprovedQuery)
    def test_user_can_mark_plain_name_public_but_cannot_approve_secrets_or_quotes(self):
        guard=Guard(QUESTION,[{'text':PRIVATE}],['JCA'],sensitive=True)
        self.assertEqual(guard.approve(['JCA documentation'],{'decision':'unsafe'},user_approved=True)[0].text,'JCA documentation')
        for query in ['password=Secret123','SkNB migration','J%43A migration','the midnight migration uses the hidden contract']:
            with self.assertRaises(PrivacyBlocked):guard.approve([query],{'decision':'safe'},user_approved=True)
    def test_public_entities_and_non_technical_subjects_are_allowed(self):
        for query in ['PlayStation 3 release date Japan Italy','photosynthesis light absorption science',
                      'current Python release official downloads','history of the Roman Empire',
                      'private key encryption explained','password rotation best practices','internal combustion engine','private cloud benefits']:
            self.assertEqual(Guard(query).approve([query],{'decision':'safe'})[0].text,query)
    def test_planner_shape_and_bounds(self):
        for value in [{'queries':[]},{'queries':['x']},{'queries':['a b']*4},{'queries':['a b'],'reason':'extra'}]:
            with self.assertRaises(ValueError):plan(value)
        self.assertEqual(plan({'queries':['public question','public question']}),['public question'])


class Web(unittest.TestCase):
    def test_structured_recipe_is_data_only_and_contains_quantities_and_method(self):
        raw='<script type="application/ld+json">'+json.dumps({'@graph':[{'@type':'Recipe','name':'Synthetic cake','recipeIngredient':['200 g flour','100 g butter'],
            'recipeInstructions':[{'@type':'HowToStep','text':'Bake at 170 C for 40 minutes.'}]}]})+'</script><script>execute()</script>'
        value=recipe_text(raw)
        self.assertIn('200 g flour',value);self.assertIn('170 C',value);self.assertNotIn('execute',value)
        self.assertEqual(recipe_text('<script type="application/ld+json">{"@type":null}</script>'),'')
    def test_egress_requires_approved_query_and_no_curated_fallback(self):
        web=PublicWeb('https://search.example.org/search')
        with self.assertRaises(TypeError):web.search('private text')
        with patch('research_web.get',return_value=('{"results":[]}','application/json')):
            self.assertEqual(web.search(ApprovedQuery('PlayStation launch Italy')),[])
        self.assertIn('No curated fallback',web.last_warning)
    def test_general_discovery_filters_unrelated_and_action_urls(self):
        rows={'results':[{'url':'https://sonyinteractive.com/press','title':'PlayStation 3 launch in Japan and Italy','content':'Sony announcement'},
             {'url':'https://en.wikipedia.org/wiki/PlayStation_3','title':'PlayStation 3','content':'Japan Italy launch'},
             {'url':'https://evil.example/delete','title':'PlayStation Japan Italy'},
             {'url':'https://shopping.example/','title':'Lidl food shopping'}]}
        web=PublicWeb('https://search.example.org/search')
        with patch('research_web.get',return_value=(json.dumps(rows),'application/json')):
            urls=web.search(ApprovedQuery('PlayStation 3 release Japan Italy'))
        self.assertEqual(len(urls),2);self.assertTrue(urls[0].startswith('https://sonyinteractive.com/'))
        with self.assertRaises(ValueError):web.read('https://undiscovered.example/a')
    def test_ssrf_public_source_policy_and_loopback_exception(self):
        def dns(ip):return lambda *a,**kw:[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443))]
        for ip in ['127.0.0.1','10.0.0.1','169.254.169.254','::1','100.64.0.1','2002:7f00:1::']:
            with self.assertRaises(ValueError):target('https://example.org/a',None,dns(ip))
        for url in ['http://example.org/a','https://example.org:8443/a','https://user@example.org/a','https://example.org/logout','https://example.org/a?token=secret','https://example.org/%64elete','https://example.org/a?action=delete']:
            with self.assertRaises(ValueError):target(url,None,dns('8.8.8.8'))
        self.assertEqual(target('https://example.org/a',None,dns('8.8.8.8'))[1],'8.8.8.8')
        self.assertTrue(PublicWeb('http://127.0.0.1:8888/search').local)
        with self.assertRaises(ValueError):PublicWeb('http://127.0.0.1:8765/search')
    def test_scripts_navigation_and_styles_are_not_evidence(self):
        p=Text();p.feed('<nav>Menu</nav><main>Evidence<script>execute()</script></main><style>secret</style>')
        self.assertEqual(''.join(p.main_parts),'Evidence');self.assertNotIn('execute',''.join(p.parts))
    def test_tutorial_excerpts_retrieve_steps_beyond_document_opening(self):
        raw=('Unrelated introduction and navigation. '*100)+'Select Get Data then Excel. Choose the workbook. Select the table in Navigator and choose Load or Transform Data.'+(' More background.'*100)
        value=excerpts(raw,'how connect Excel Power BI Desktop steps')
        self.assertIn('Navigator',value[:1800]);self.assertIn('Transform Data',value[:1800])


if __name__=='__main__':unittest.main()
