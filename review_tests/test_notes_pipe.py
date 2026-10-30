"""Offline Function event contract; real Open WebUI import remains an adoption check."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class BaseModel:pass
class Response:
    def __init__(self,obj,code=200):self.obj=obj;self.status_code=code
    def json(self):return self.obj
    def raise_for_status(self):
        if self.status_code>=400:raise ValueError('HTTP error')
class Client:
    posts=[];gets=[];state='recap-review';fail=False
    def __init__(self,**kwargs):pass
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def post(self,url,**kwargs):
        self.posts.append((url,kwargs));return Response({'id':'a'*32,'upload_token':'scoped-token'})
    async def get(self,url,**kwargs):
        self.gets.append((url,kwargs))
        if self.fail:raise ConnectionError()
        return Response({'id':'a'*32,'job_id':'note-'+'b'*32,'state':self.state,'created':0})


class NotesPipe(unittest.TestCase):
    def setUp(self):
        Client.posts=[];Client.gets=[];Client.state='recap-review';Client.fail=False
        spec=importlib.util.spec_from_file_location('notes_pipe_fixture',Path(__file__).resolve().parents[1]/'openwebui_notes_pipe.py')
        module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'httpx':types.SimpleNamespace(AsyncClient=Client),
            'pydantic':types.SimpleNamespace(BaseModel=BaseModel,Field=lambda default=None,**kwargs:default)}):spec.loader.exec_module(module)
        self.pipe=module.Pipe();self.pipe.valves.PUBLIC_ORIGIN='https://notes.invalid';self.pipe.valves.WORKER_API_KEY='server-only-secret'
        self.events=[]
    def run_pipe(self,text='notes',user=None,chat='chat',emitter=True):
        async def emit(value):self.events.append(value)
        return asyncio.run(self.pipe.pipe({'messages':[{'role':'user','content':text}]},
            __user__=user or {'id':'alice'},__chat_id__=chat,__message_id__='message',__event_emitter__=emit if emitter else None))
    def test_card_then_ready_link_and_secret_stays_server_side(self):
        result=self.run_pipe()
        embeds=[e for e in self.events if e['type']=='embeds']
        self.assertEqual(embeds[0]['data']['embeds'],['https://notes.invalid/meeting-ui/note-upload/view/scoped-token'])
        self.assertIn('/meeting-ui/notes#note-',result);self.assertIn('separately approve',result)
        self.assertNotIn('server-only-secret',str(self.events)+result)
        self.assertEqual(Client.posts[0][1]['headers']['X-Owner-Id'],'alice')
        self.assertEqual(Client.posts[0][1]['json']['request_key'],'chat:message')
    def test_status_reconnect_does_not_create_another_card(self):
        self.run_pipe('status '+'a'*32);self.assertEqual(Client.posts,[])
        self.assertFalse(any(e['type']=='embeds' for e in self.events))
    def test_failure_returns_recovery_dashboard(self):
        Client.state='failed';result=self.run_pipe();self.assertIn('retry',result);self.assertIn('Open Notes dashboard',result)
    def test_connection_loss_keeps_session_reconnect_id(self):
        Client.fail=True;result=self.run_pipe();self.assertIn('status '+'a'*32,result)
    def test_saved_chat_required(self):
        result=self.run_pipe(chat=None);self.assertIn('saved',result);self.assertEqual(Client.posts,[])
    def test_untrusted_origin_rejected(self):
        self.pipe.valves.PUBLIC_ORIGIN='https://name:secret@notes.invalid/path'
        self.assertIn('setup',self.run_pipe());self.assertEqual(Client.posts,[])
    def test_no_emitter_does_not_prevent_durable_status(self):
        self.assertIn('Open Notes dashboard',self.run_pipe(emitter=False))
    def test_source_readiness_returns_first_approval_instructions(self):
        Client.state='page-review';self.assertIn('Approve source',self.run_pipe())


if __name__=='__main__':unittest.main()
