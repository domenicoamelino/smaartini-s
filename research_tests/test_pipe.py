import asyncio
import importlib.util
from pathlib import Path
import sys
import time
import types
import unittest
from unittest.mock import patch


class Response:
    def __init__(self,obj): self.obj=obj
    def json(self): return self.obj
    def raise_for_status(self): pass


class Client:
    values=[]; posts=[]
    def __init__(self,**kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    async def post(self,url,**kwargs):
        self.posts.append(kwargs['json']); return Response({'id':'a'*32})
    async def get(self,url,**kwargs):
        await asyncio.sleep(0)
        value=self.values.pop(0)
        if isinstance(value,Exception): raise value
        return Response(value)


class PipeTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('research_pipe_under_test',Path(__file__).resolve().parents[1]/'openwebui_research_pipe.py')
        self.module=importlib.util.module_from_spec(spec)
        http=types.SimpleNamespace(AsyncClient=Client,TimeoutException=TimeoutError,NetworkError=ConnectionError)
        with patch.dict(sys.modules,{'httpx':http,'pydantic':types.SimpleNamespace(BaseModel=object,Field=lambda default=None,**kw:default)}): spec.loader.exec_module(self.module)
        self.pipe=self.module.Pipe(); Client.posts=[]; self.events=[]
    async def emit(self,event): self.events.append(event['data'])
    def call(self,text):
        return self.pipe.pipe({'messages':[{'role':'user','content':text}]},{'id':'alice'},self.emit,'chat','message')
    def test_live_waiting_failure_and_reconnect_no_resubmit(self):
        Client.values=[{'status':'queued','stage':'Waiting for shared slot','created':time.time()-5,'updated':time.time()-5},
            {'status':'running','stage':'Planning locally','updated':time.time()-10},
            {'status':'failed','stage':'Source timeout','updated':time.time()}]
        real_sleep=asyncio.sleep
        async def fast(*a): await real_sleep(0)
        async def exercise():
            ticks=[]
            async def ui():
                for _ in range(4): await real_sleep(0); ticks.append(1)
            result,_=await asyncio.gather(self.call('status '+'a'*32),ui())
            self.assertTrue(ticks); return result
        with patch.object(self.module.asyncio,'sleep',side_effect=fast): result=asyncio.run(exercise())
        self.assertIn('timeout',result);self.assertEqual(Client.posts,[])
        self.assertTrue(any('waiting' in e['description'] for e in self.events))
        self.assertTrue(self.events[-1]['done'])
    def test_mode_override_and_network_wait(self):
        Client.values=[TimeoutError(),TimeoutError(),TimeoutError()]
        real_sleep=asyncio.sleep
        async def fast(*a): await real_sleep(0)
        with patch.object(self.module.asyncio,'sleep',side_effect=fast): result=asyncio.run(self.call('/web public question'))
        self.assertEqual(Client.posts[0]['mode'],'web')
        self.assertEqual(Client.posts[0]['question'],'public question')
        self.assertIn('status '+ 'a'*32,result)
        self.assertTrue(any('retry 2' in e['description'] for e in self.events))
    def test_help_and_bare_modes_do_not_start_research(self):
        for command in ['/help','/web','/work','/knowledge','/auto']:
            result=asyncio.run(self.call(command))
            self.assertIn('no public searches',result)
            self.assertIn('/auto',result)
        self.assertEqual(Client.posts,[])
    def test_work_alias_uses_public_mode(self):
        Client.values=[{'status':'failed','stage':'No evidence'}]
        asyncio.run(self.call('/work public question'))
        self.assertEqual(Client.posts[0]['mode'],'web')
        self.assertEqual(Client.posts[0]['question'],'public question')
    def test_query_review_is_shown_and_returns_control_to_user(self):
        Client.values=[{'id':'a'*32,'status':'needs_review','stage':'Waiting for review','result':{
            'review':{'queries':['Power BI Excel import tutorial'],'reason':'Term may be private','digest':'b'*64}}}]
        result=asyncio.run(self.call('/web tutorial'))
        self.assertIn('Power BI Excel import tutorial',result)
        self.assertIn('approve '+'a'*32+' '+'b'*12,result)
        self.assertIn('reject '+'a'*32,result)
        self.assertTrue(self.events[-1]['done'])
    def test_approval_command_posts_review_without_creating_a_new_job(self):
        Client.values=[{'status':'cancelled','stage':'Already declined'}]
        result=asyncio.run(self.call('approve '+'a'*32+' '+'b'*12))
        self.assertEqual(Client.posts,[{'decision':'approve','proof':'b'*12}])
        self.assertIn('Already declined',result)
    def test_native_confirmation_uses_exact_queries_and_requires_explicit_true(self):
        Client.values=[{'id':'a'*32,'status':'needs_review','stage':'Review','result':{'review':{
            'queries':['Power BI Excel tutorial'],'reason':'Uncertain','digest':'b'*64}}},
            {'status':'cancelled','stage':'Synthetic terminal'}]
        prompts=[]
        async def confirm(event):prompts.append(event);return True
        result=asyncio.run(self.pipe.pipe({'messages':[{'role':'user','content':'status '+'a'*32}]},
            {'id':'alice'},self.emit,'chat','message',__event_call__=confirm))
        self.assertEqual(prompts[0]['type'],'confirmation');self.assertIn('Power BI Excel tutorial',prompts[0]['data']['message'])
        self.assertEqual(Client.posts,[{'decision':'approve','proof':'b'*12}])
    def test_native_confirmation_unrecognized_response_cannot_approve(self):
        Client.values=[{'id':'a'*32,'status':'needs_review','stage':'Review','result':{'review':{
            'queries':['public question'],'reason':'Uncertain','digest':'b'*64}}}]
        async def no_boolean(event):return {'approved':True}
        result=asyncio.run(self.pipe.pipe({'messages':[{'role':'user','content':'status '+'a'*32}]},
            {'id':'alice'},self.emit,'chat','message',__event_call__=no_boolean))
        self.assertEqual(Client.posts,[]);self.assertIn('approve '+'a'*32,result)
    def test_hybrid_tutorial_keeps_step_order_across_citation_types(self):
        result={'answer':{'findings':[{'text':'1. Public step','sources':['W1'],'type':'public'},
            {'text':'2. Private step','sources':['K1'],'type':'internal'},
            {'text':'3. Combined step','sources':['K1','W1'],'type':'inference'}],'uncertainties':''},
            'warnings':[],'sources':[]}
        value=self.module.render(result)
        self.assertLess(value.index('1. Public'),value.index('2. Private'))
        self.assertLess(value.index('2. Private'),value.index('3. Combined'))
        self.assertIn('(interpretation)',value)


if __name__=='__main__': unittest.main()
