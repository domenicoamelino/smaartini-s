"""
title: SMARTINI’s Research
author: Local AI project
version: 0.2.0-candidate
description: Bounded read-only Knowledge, Web or Auto research with durable live progress.
"""
import asyncio
import re
import time
import httpx
from pydantic import BaseModel, Field

MODE_HELP = '''Choose a research mode, then add your question:

- **/web** (also **/work**): search public internet sources. Private notes are not used as answer evidence.
- **/knowledge**: use only your approved private Knowledge; no public searches.
- **/auto**: choose Knowledge, web, or both. Use this to research extra public information related to your approved notes. Ambiguous public queries ask for your approval before being sent.

Example: `/auto Based on my latest approved notes, what are the technical risks and which current public practices could help?`

Without a prefix, Auto is the default. Send `/help` to see this guide again.'''


def plain(value):
    # Keep model/page supplied markup and remote images out of the chat renderer.
    return re.sub(r'([\\`*_{}\[\]<>#!|])',r'\\\1',str(value)).replace('\r',' ').replace('\n',' ')


def render(result):
    answer=result['answer']; lines=[]
    steps=bool(answer['findings']) and all(re.match(r'^\d+\.\s',r['text']) for r in answer['findings'])
    if steps:
        lines=['**Steps**','']
        if any(s['kind']=='knowledge' for s in result['sources']):lines+=['K citations are approved private Knowledge; W citations are public sources.','']
        for row in answer['findings']:
            lines.append(plain(row['text'])+' '+' '.join('['+s+']' for s in row['sources'])+(' (interpretation)' if row['type']=='inference' else ''))
        lines+=['']
    for label,kind in [] if steps else [('Internal evidence','internal'),('Public evidence','public'),('Interpretation and recommendations','inference')]:
        rows=[r for r in answer['findings'] if r['type']==kind]
        if rows:
            lines += ['**'+label+'**','']
            ordered=all(re.match(r'^\d+\.\s',r['text']) for r in rows)
            lines += [('' if ordered else '- ')+plain(r['text'])+' '+ ' '.join('['+s+']' for s in r['sources']) for r in rows]
            lines += ['']
    lines += ['**Uncertainty**',plain(answer['uncertainties']),'']
    for warning in result['warnings']: lines += ['- '+plain(warning)]
    lines += ['','**Sources**']
    for source in result['sources']:
        if source['kind']=='knowledge':
            lines += ['- ['+source['id']+'] Private approved Knowledge: '+plain(source['title'])+'; revision '+str(source['revision'])+'; SHA-256 '+source['sha256']]
        else:
            # Only runtime-validated URLs are used. Escape Markdown URL delimiters.
            url=source['url'].replace('(','%28').replace(')','%29').replace('<','%3C').replace('>','%3E')
            lines += ['- ['+source['id']+'] Public web: ['+plain(source['title'])+']('+url+'). '+plain(source['date'])+'; retrieved '+time.strftime('%Y-%m-%d',time.gmtime(source['retrieved_at']))]
    return '\n'.join(lines)


def render_review(job):
    review=job['result']['review'];jid=job['id'];proof=review['digest'][:12]
    lines=['**Are these queries safe to send to public search services?**','',plain(review['reason']),'']
    lines+=['- '+plain(q) for q in review['queries']]
    lines+=['','No queries have been sent. Approve only if this exact wording is public or you authorize sharing it. Approval applies to this job only.',
            '', 'Reply with:', '`approve '+jid+' '+proof+'`', '', 'Or decline with:', '`reject '+jid+'`',
            '', 'Passwords, tokens and copied private passages remain blocked.']
    return '\n'.join(lines)


class Pipe:
    class Valves(BaseModel):
        WORKER_URL: str = Field(default='http://127.0.0.1:8765')
        WORKER_API_KEY: str = Field(default='',json_schema_extra={'input':{'type':'password'}})
        MODE: str = Field(default='auto',description='auto, knowledge or web; per-message override: /knowledge, /web, /auto')
        WAIT_SECONDS: int = Field(default=900,ge=60,le=1800)
    def __init__(self): self.valves=self.Valves()
    async def pipe(self,body:dict,__user__:dict=None,__event_emitter__=None,__chat_id__:str=None,__message_id__:str=None,__task__:str=None,__event_call__=None):
        if __task__: return 'Research'
        if not __user__ or not __user__.get('id'): return 'Sign in before starting research.'
        async def status(message,done=False):
            if __event_emitter__:
                try: await asyncio.wait_for(__event_emitter__({'type':'status','data':{'description':message,'done':done,'hidden':False}}),timeout=2)
                except Exception: pass
        text=next((m.get('content','') for m in reversed(body.get('messages',[])) if m.get('role')=='user'),'')
        if not isinstance(text,str): return 'Use a text research question.'
        match=re.fullmatch(r'\s*status\s+([a-f0-9]{32})\s*',text)
        jid=match[1] if match else None; mode=self.valves.MODE
        approval=re.fullmatch(r'\s*approve\s+([a-f0-9]{32})\s+([a-f0-9]{12})\s*',text,re.I)
        rejection=re.fullmatch(r'\s*reject\s+([a-f0-9]{32})\s*',text,re.I)
        if approval or rejection:jid=(approval or rejection)[1].lower()
        if text.strip().lower() in ('/help','/web','/work','/knowledge','/auto'):return MODE_HELP
        command=re.match(r'^/(knowledge|web|work|auto)\s+',text,re.I)
        if command: mode='web' if command[1].lower()=='work' else command[1].lower(); text=text[command.end():]
        if mode not in ('auto','knowledge','web'): return 'Choose auto, knowledge or web research mode.'
        headers={'Authorization':'Bearer '+self.valves.WORKER_API_KEY,'X-Owner-Id':str(__user__['id'])}
        base=self.valves.WORKER_URL.rstrip('/')+'/v1/research/jobs'
        await status('Connecting to durable research queue')
        async with httpx.AsyncClient(timeout=10,trust_env=False,follow_redirects=False) as client:
            try:
                if approval or rejection:
                    r=await client.post(base+'/'+jid+'/review',headers=headers,json={'decision':'approve' if approval else 'reject','proof':approval[2].lower() if approval else ''})
                    r.raise_for_status()
                    if rejection:
                        await status('Queries rejected; no public search sent',True)
                        return 'Public queries rejected. Nothing was sent.'
                if not jid:
                    if not __chat_id__ or not __message_id__: return 'Use a saved chat to give research a stable request identity.'
                    r=await client.post(base,headers=headers,json={'request_key':str(__chat_id__)+':'+str(__message_id__),'question':text,'mode':mode})
                    r.raise_for_status(); jid=r.json()['id']
                start=time.monotonic(); failures=0; seen_events=set()
                while time.monotonic()-start<self.valves.WAIT_SECONDS:
                    try:
                        r=await client.get(base+'/'+jid,headers=headers); r.raise_for_status(); job=r.json(); failures=0
                    except (httpx.TimeoutException,httpx.NetworkError):
                        failures+=1
                        await status('Waiting for research connection; retry '+str(failures)+'. Job '+jid+' remains durable.')
                        if failures>=3: break
                        await asyncio.sleep(3); continue
                    for event in job.get('events',[]):
                        if event['sequence'] not in seen_events:
                            seen_events.add(event['sequence'])
                            await status(event['stage'])
                    if job['status']=='needs_review':
                        await status('Waiting for your public-query decision; no query sent',True)
                        if __event_call__ and __chat_id__ and __message_id__:
                            review=job['result']['review']
                            message='May SMARTINIS send these exact queries to public search services?\n\n'+'\n'.join('- '+plain(q) for q in review['queries'])+'\n\nConfirm only if this wording is public or you authorize sharing it. This applies to this research job only.'
                            try:
                                decision=await asyncio.wait_for(__event_call__({'type':'confirmation','data':{'title':'Approve public search queries?','message':message}}),timeout=120)
                                if decision is True or decision is False:
                                    r=await client.post(base+'/'+jid+'/review',headers=headers,json={'decision':'approve' if decision else 'reject','proof':review['digest'][:12] if decision else ''})
                                    r.raise_for_status()
                                    if decision is False:return 'Public queries rejected. Nothing was sent.'
                                    await status('You approved these queries; resuming research')
                                    continue
                            except asyncio.CancelledError:raise
                            except Exception:pass  # Durable text commands remain available if no client response arrives.
                        return render_review(job)
                    if job['status']=='completed':
                        await status('Research completed',True); return render(job['result'])
                    if job['status'] in ('failed','cancelled'):
                        await status(job['stage'],True); return job['stage']+'. Research ID: '+jid
                    elapsed=int(time.time()-(job.get('ready_at',job['created']) if job['status']=='queued' else job['updated']))
                    await status(job['stage']+' · '+('queued for ' if job['status']=='queued' else 'waiting ')+str(elapsed)+'s · research '+jid)
                    await asyncio.sleep(3)
                await status('Chat wait ended; research remains available',True)
                return 'Reconnect with `status '+jid+'`. The job continues independently of this chat.'
            except asyncio.CancelledError: raise
            except Exception:
                await status('Research connection failed or timed out',True)
                return 'Research unavailable.'+(' Reconnect with `status '+jid+'`.' if jid else ' Check the worker configuration; retry uses the same request identity.')
