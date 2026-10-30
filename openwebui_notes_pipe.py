"""
title: SMARTINI’s Notes
author: Local AI project
version: 0.3.0
description: Upload photographed notes in an audio-style card; review and approve separately.
"""
import asyncio
import re
import time
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, Field


class Pipe:
    class UserValves(BaseModel):
        RECAP_LANGUAGE: Literal['English','Dutch','Italian'] = Field(default='English')

    class Valves(BaseModel):
        WORKER_URL: str = Field(default='http://127.0.0.1:8765')
        WORKER_API_KEY: str = Field(default='',json_schema_extra={'input':{'type':'password'}})
        PUBLIC_ORIGIN: str = Field(default='',description='Same browser origin as the existing audio Function, without a path')
        POLL_SECONDS: int = Field(default=3,ge=2,le=30)
        WAIT_SECONDS: int = Field(default=21600,ge=60,le=86400)

    def __init__(self):
        self.valves=self.Valves()

    async def pipe(self,body:dict,__user__:dict=None,__event_emitter__=None,
                   __chat_id__:str=None,__message_id__:str=None,__task__:str=None):
        if __task__:return 'Handwritten notes'
        if not __user__ or not __user__.get('id'):return 'Sign in before starting Notes.'
        origin=self.valves.PUBLIC_ORIGIN.rstrip('/')
        parsed=urlsplit(origin)
        if (parsed.scheme not in ('http','https') or not parsed.netloc or parsed.username or
            parsed.password or parsed.path or parsed.query or parsed.fragment or not self.valves.WORKER_API_KEY):
            return 'Admin setup required: copy WORKER_URL, WORKER_API_KEY and PUBLIC_ORIGIN from the audio Function. Notes backend 0.3.0 must be installed and enabled first.'
        owner=str(__user__['id'])
        headers={'Authorization':'Bearer '+self.valves.WORKER_API_KEY,'X-Owner-Id':owner}
        preferences=__user__.get('valves') or self.UserValves()
        language=preferences.get('RECAP_LANGUAGE','English') if isinstance(preferences,dict) else getattr(preferences,'RECAP_LANGUAGE','English')
        async def emit(kind,data):
            if __event_emitter__:
                try:await __event_emitter__({'type':kind,'data':data})
                except Exception:pass
        async def status(text,done=False):
            await emit('status',{'description':text,'done':done,'hidden':False})
        text=''
        for message in reversed(body.get('messages',[])):
            if message.get('role')=='user':
                content=message.get('content','')
                text=content if isinstance(content,str) else ' '.join(v.get('text','') for v in content if isinstance(v,dict))
                break
        match=re.fullmatch(r'\s*status\s+([a-f0-9]{32})\s*',text,re.I)
        sid=match[1].lower() if match else None
        async with httpx.AsyncClient(timeout=30,trust_env=False,follow_redirects=False) as client:
            try:
                base=self.valves.WORKER_URL.rstrip('/')+'/v1/notes/sessions'
                if not sid:
                    if not __chat_id__ or not __message_id__:
                        return 'Start a saved Open WebUI chat so Notes has a stable request ID.'
                    response=await client.post(base,headers=headers,json={
                        'request_key':str(__chat_id__)+':'+str(__message_id__),'language':language})
                    response.raise_for_status();session=response.json();sid=session['id']
                    await emit('embeds',{'embeds':[origin+'/meeting-ui/note-upload/view/'+session['upload_token']],'replace':True})
                    await status('Add a title, notes date and pictures in the card, then confirm processing. Recap: '+language+'.')
                started=time.monotonic();last=None
                while time.monotonic()-started<self.valves.WAIT_SECONDS:
                    response=await client.get(base+'/'+sid,headers=headers)
                    if response.status_code==404:
                        await status('Notes request unavailable for this account',True)
                        return 'Notes request not found or belongs to another account.'
                    response.raise_for_status();value=response.json();state=value['state']
                    if state in ('page-review','recap-review','approved','failed'):
                        failed=state=='failed'
                        await status('Notes needs attention' if failed else 'Notes draft ready for review',True)
                        jid=value['job_id']
                        if not re.fullmatch(r'note-[a-f0-9]{32}',jid):raise ValueError('Invalid Notes job identity')
                        return ('Originals and completed work are retained. Review or retry in the dashboard.' if failed else
                            ('Your extracted source is ready. Review it, then click Approve source & generate recap and diagrams. The final result needs a second approval.' if state=='page-review' else 'Your final Notes recap and diagrams are ready. Edit text or replace images, then separately approve the final result for Knowledge.'))+'\n\n[Open Notes dashboard]('+origin+'/meeting-ui/notes#'+jid+')'
                    if state!=last:
                        await status({'waiting_upload':'Waiting for you to confirm the upload card',
                            'extract-queued':'Notes queued with the other local jobs','extract-running':'Analysing pictures sequentially',
                            'final-queued':'Final recap and diagrams queued','final-running':'Generating final recap and diagrams','recap-queued':'Combined recap queued','recap-running':'Preparing your combined recap',
                            'page-review':'Transcription ready; review it in the Notes dashboard'}.get(state,state))
                        last=state
                    if state=='waiting_upload' and time.time()-value['created']>1800:
                        return 'Upload card expired. Start a new Notes request.'
                    await asyncio.sleep(self.valves.POLL_SECONDS)
                await status('Chat waiting limit reached; server work continues',True)
                return 'The Notes request remains on the server. Send `status '+sid+'` to reconnect.'
            except asyncio.CancelledError:
                raise
            except Exception:
                await status('Notes connection interrupted',True)
                return 'Could not connect to Notes. Confirm that backend 0.3.0 is installed and enabled. Any committed job continues on the server.'+(' Send `status '+sid+'` to reconnect.' if sid else '')
