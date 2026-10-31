import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from test_notes_pipe import BaseModel,Response

class Client:
    posts=[];gets=[];fail=False
    def __init__(self,**kwargs):pass
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def post(self,url,**kwargs):
        self.posts.append((url,kwargs));return Response({'id':'a'*32,'upload_token':'scoped-text-token'})
    async def get(self,url,**kwargs):
        self.gets.append((url,kwargs))
        if self.fail:raise ConnectionError()
        return Response({'id':'a'*32,'state':'draft-saved','doc_id':'text-'+'b'*32,'created':0})

class TextPipe(unittest.TestCase):
    def setUp(self):
        Client.posts=[];Client.gets=[];Client.fail=False
        spec=importlib.util.spec_from_file_location('text_pipe_fixture',Path(__file__).resolve().parents[1]/'openwebui_text_pipe.py')
        module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'httpx':types.SimpleNamespace(AsyncClient=Client),
            'pydantic':types.SimpleNamespace(BaseModel=BaseModel,Field=lambda default=None,**kwargs:default)}):spec.loader.exec_module(module)
        self.pipe=module.Pipe();self.pipe.valves.PUBLIC_ORIGIN='https://text.invalid';self.pipe.valves.WORKER_API_KEY='server-only-secret';self.events=[]
    def run_pipe(self,message='text',chat='chat'):
        async def emit(value):self.events.append(value)
        return asyncio.run(self.pipe.pipe({'messages':[{'role':'user','content':message}]},__user__={'id':'alice'},__chat_id__=chat,__message_id__='message',__event_emitter__=emit))
    def test_embed_server_side_auth_and_model_free_draft_link(self):
        result=self.run_pipe();self.assertIn('?view=text#text-',result);self.assertIn('successful ingestion',result)
        self.assertEqual(Client.posts[0][1]['headers']['X-Owner-Id'],'alice')
        self.assertNotIn('server-only-secret',result+str(self.events));self.assertTrue(any(e['type']=='embeds' for e in self.events))
    def test_status_reconnect_does_not_create_a_new_submission(self):
        self.run_pipe('status '+'a'*32);self.assertEqual(Client.posts,[])
    def test_connection_loss_has_recovery_identity(self):
        Client.fail=True;self.assertIn('status '+'a'*32,self.run_pipe())
    def test_saved_chat_and_origin_setup_required(self):
        self.assertIn('saved chat',self.run_pipe(chat=None));self.assertEqual(Client.posts,[])
        self.pipe.valves.PUBLIC_ORIGIN='https://name:secret@text.invalid/path';self.assertIn('Configure',self.run_pipe());self.assertEqual(Client.posts,[])

if __name__=='__main__':unittest.main()
