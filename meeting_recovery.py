"""Owner-scoped, read-only generation diagnostics and incomplete draft recovery."""
import datetime as dt
import json
import os
from pathlib import Path
import re


def safe_message(value):
    value=str(value)
    for key,secret in os.environ.items():
        if len(secret)>=12 and any(word in key for word in ('TOKEN','PASSWORD','SECRET','API_KEY')):
            value=value.replace(secret,'[redacted]')
    value=re.sub(r'(?i)(bearer\s+)[^\s"<>]+',r'\1[redacted]',value)
    value=re.sub(r'\b(?:sk-[A-Za-z0-9_-]{12,}|\d{6,}:[A-Za-z0-9_-]{20,})\b','[redacted]',value)
    value=re.sub(r'(?i)((?:api[_ -]?key|password|token|secret)\s*[=:]\s*)[^\s,;]+',r'\1[redacted]',value)
    value=re.sub(r'https?://[^\s"<>]+','[service URL]',value)
    value=re.sub(r'/home/[^\s"<>]+','[private path]',value)
    return value[:1800]


def event(folder,kind,**values):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    row={'time':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),'event':kind}
    row.update({key:safe_message(value) if isinstance(value,str) else value for key,value in values.items()})
    with (folder/'events.jsonl').open('a',encoding='utf-8') as out:
        out.write(json.dumps(row,ensure_ascii=False)+'\n');out.flush()


def problem(exc):
    detail=safe_message(exc);text=detail.lower();category='generation_error';explanation='Generation failed; saved stages are retained.'
    if 'truncated' in text or 'output-token' in text:
        category='output_limit';explanation='The model reached its output-token limit before finishing the response.'
    elif isinstance(exc,TimeoutError) or any(word in text for word in ('timed out','timeout','time limit')):
        category='timeout';explanation='The model or connection exceeded its time limit.'
    elif 'context' in text:
        category='context_limit';explanation='The request or its evidence exceeded the safe context allowance.'
    elif isinstance(exc,json.JSONDecodeError) or 'json' in text or 'invalid recap' in text:
        category='invalid_response';explanation='The model response was incomplete or was not valid recap JSON.'
    elif any(word in text for word in ('connection','ollama http','unreachable','refused')):
        category='service_error';explanation='The local model service could not complete the request.'
    elif 'memory' in text:
        category='memory_limit';explanation='The local model service reported a memory problem.'
    return {'type':type(exc).__name__,'category':category,'message':explanation+' Detail: '+detail}


def read(path,limit=2*1024*1024):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>limit:return None
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return None


def extract(raw):
    try:
        value=json.loads(raw)
        if isinstance(value,dict) and isinstance(value.get('recap'),str):return value['recap'].strip(),True
        if isinstance(value,dict) and isinstance(value.get('sections'),list):
            texts=[section['text'].strip() for section in value['sections'] if isinstance(section,dict) and isinstance(section.get('text'),str) and section['text'].strip()]
            return '\n\n'.join(texts),False  # Coverage is unvalidated outside the completed-stage cache.
    except (ValueError,TypeError):pass
    if not isinstance(raw,str):return '',False
    match=re.search(r'"recap"\s*:\s*"',raw)
    if not match:
        if re.search(r'"sections"\s*:\s*\[',raw):
            texts=[]
            for field in re.finditer(r'"text"\s*:\s*"',raw):
                text,_=extract('{"recap":"'+raw[field.end():])
                if text:texts.append(text)
            return '\n\n'.join(texts),False
        return '',False
    fragment=raw[match.end():];escaped=False;end=len(fragment)
    for index,char in enumerate(fragment):
        if char=='"' and not escaped:end=index;break
        escaped=char=='\\' and not escaped
        if char!='\\':escaped=False
    fragment=fragment[:end]
    for trim in range(min(16,len(fragment))):
        candidate=fragment if not trim else fragment[:-trim]
        try:return json.loads('"'+candidate+'"').strip(),False
        except ValueError:continue
    return '',False


def attempt(folder,task):
    directory=Path(folder)/'review-work'/task['key']
    if directory.is_symlink():return None
    events=[];path=directory/'events.jsonl'
    if path.is_file() and not path.is_symlink():
        for line in path.read_text(encoding='utf-8')[-150000:].splitlines()[-150:]:
            try:
                row=json.loads(line);events.append({k:safe_message(v) if isinstance(v,str) else v for k,v in row.items()})
            except ValueError:continue
    notes=[];seen=set();responses=[]
    def add(text,complete,label):
        if text and text not in seen:
            seen.add(text);notes.append({'label':label,'complete':complete,'text':text[:20000]})
    cache=read(directory/'draft-cache.json') or {}
    for text in cache.values():
        if isinstance(text,str):add(text,True,'Saved completed generation stage')
    for path in sorted(directory.glob('response_*.json'))+sorted(directory.glob('stream_*.json')):
        value=read(path)
        if not isinstance(value,dict):continue
        metrics=value.get('metrics') or {};reason=metrics.get('done_reason')
        text,valid=extract(value.get('content',''))
        complete=valid and reason=='stop' and path.name.startswith('response_')
        add(text,complete,'Completed response' if complete else 'Unvalidated or interrupted output — incomplete, may contain errors')
        responses.append({'file':path.name,'done_reason':reason or 'interrupted','output_tokens':metrics.get('eval_count'),
            'prompt_tokens':metrics.get('prompt_eval_count'),'characters':len(value.get('content',''))})
    problem=read(directory/'failure.json')
    if not problem and any(row['done_reason']=='length' for row in responses):
        problem={'type':'OutputLimit','message':'The model reached its output-token limit before completing the recap. Saved notes and interrupted output can be recovered; retry uses bounded compact-output recovery.'}
    if not problem and task['status']=='failed':
        problem={'type':'LegacyFailure','message':'The earlier worker did not retain the exception detail. Available response metrics and saved draft text are shown below.'}
    if problem:problem={key:safe_message(value) for key,value in problem.items()}
    return {'task':task['key'],'base_revision':task['base'],'status':task['status'],'created':task['created'],
        'events':events,'responses':responses[-30:],'failure':problem,'notes':notes}


def recovery_text(info):
    if not info or not info['notes']:return ''
    lines=['# Recovered working draft — incomplete and unreviewed','',
        'These are saved generation stages, not a complete or approved meeting recap. Some passages may overlap or contradict later notes. Check against the downloadable transcript before saving and approving.','']
    for i,note in enumerate(info['notes'],1):
        lines.extend([f"## {i}. {note['label']}",note['text'],''])
    return '\n'.join(lines)[:59000]
