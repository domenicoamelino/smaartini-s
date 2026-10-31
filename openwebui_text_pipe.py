"""
title: SMARTINI’s Text
author: Local AI project
version: 0.1.0
description: Save your Markdown as a draft; review, approve and ingest without AI processing.
"""
import asyncio
import re
import time
from urllib.parse import urlsplit
import httpx
from pydantic import BaseModel,Field

class Pipe:
    class Valves(BaseModel):
        WORKER_URL:str=Field(default='http://127.0.0.1:8765')
        WORKER_API_KEY:str=Field(default='',json_schema_extra={'input':{'type':'password'}})
        PUBLIC_ORIGIN:str=Field(default='',description='Copy the existing audio Function browser origin, without a path')
        POLL_SECONDS:int=Field(default=3,ge=2,le=30)
        WAIT_SECONDS:int=Field(default=1800,ge=60,le=7200)
    def __init__(self):self.valves=self.Valves()
    async def pipe(self,body:dict,__user__:dict=None,__event_emitter__=None,__chat_id__:str=None,__message_id__:str=None,__task__:str=None):
        if __task__:return 'Text material'
        if not __user__ or not __user__.get('id'):return 'Sign in before adding text.'
        origin=self.valves.PUBLIC_ORIGIN.rstrip('/');p=urlsplit(origin)
        if p.scheme not in ('http','https') or not p.netloc or p.username or p.password or p.path or p.query or p.fragment or not self.valves.WORKER_API_KEY:
            return 'Configure WORKER_URL, WORKER_API_KEY and PUBLIC_ORIGIN using the existing audio Function values. The Text backend must be enabled.'
        async def emit(kind,data):
            if __event_emitter__:
                try:await __event_emitter__({'type':kind,'data':data})
                except Exception:pass
        async def status(message,done=False):await emit('status',{'description':message,'done':done,'hidden':False})
        text=''
        for message in reversed(body.get('messages',[])):
            if message.get('role')=='user':
                content=message.get('content','');text=content if isinstance(content,str) else ' '.join(x.get('text','') for x in content if isinstance(x,dict));break
        match=re.fullmatch(r'\s*status\s+([a-f0-9]{32})\s*',text,re.I);sid=match[1].lower() if match else None
        headers={'Authorization':'Bearer '+self.valves.WORKER_API_KEY,'X-Owner-Id':str(__user__['id'])}
        async with httpx.AsyncClient(timeout=30,trust_env=False,follow_redirects=False) as client:
            try:
                base=self.valves.WORKER_URL.rstrip('/')+'/v1/text/sessions'
                if not sid:
                    if not __chat_id__ or not __message_id__:return 'Use a saved chat so the Text submission has a stable request identity.'
                    r=await client.post(base,headers=headers,json={'request_key':str(__chat_id__)+':'+str(__message_id__)})
                    r.raise_for_status();value=r.json();sid=value['id']
                    await emit('embeds',{'embeds':[origin+'/meeting-ui/write/view/'+value['upload_token']],'replace':True})
                await status('Add a title, date and Markdown text in the card, then save the draft. No AI processing.')
                started=time.monotonic()
                while time.monotonic()-started<self.valves.WAIT_SECONDS:
                    r=await client.get(base+'/'+sid,headers=headers);r.raise_for_status();value=r.json()
                    if value.get('doc_id'):
                        jid=value['doc_id']
                        if not re.fullmatch('text-[a-f0-9]{32}',jid):raise ValueError('Invalid text identity')
                        await status('Draft saved for your review',True)
                        return 'Text saved without AI processing. Review/edit and separately approve it for nightly Knowledge ingestion. InfoRag notifies you after successful ingestion.\n\n[Open text review]('+origin+'/meeting-ui/dashboard/?view=text#'+jid+')'
                    if time.time()-value['created']>1800:return 'Text card expired. Start a new request.'
                    await asyncio.sleep(self.valves.POLL_SECONDS)
                await status('Chat wait ended; saved drafts remain available',True)
                return 'Send `status '+sid+'` to reconnect. The card cannot approve or ingest your text.'
            except asyncio.CancelledError:raise
            except Exception:
                await status('Text connection interrupted',True)
                return 'Could not reach Text. Any saved draft remains on the server.'+(' Send `status '+sid+'` to reconnect.' if sid else '')
