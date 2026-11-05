"""Conservative Audio-only RAM admission; preserve complete source coverage."""
import json
import math
import os
from pathlib import Path
import urllib.request


class ResourceWait(RuntimeError):
    def __init__(self,message,available_mb=None,required_mb=None):
        super().__init__(message)
        self.available_mb=available_mb
        self.required_mb=required_mb


def enabled():
    return os.environ.get('SMARTINIS_RECAP_RAM_GUARD','1')!='0'


def available_mb():
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith('MemAvailable:'):return int(line.split()[1])//1024
    except (OSError,ValueError):pass
    return None


def api(url,path,body=None):
    data=json.dumps(body).encode() if body is not None else None
    request=urllib.request.Request(url.rstrip('/')+path,data,{'Content-Type':'application/json'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request,timeout=5) as response:return json.load(response)


def headroom_mb():
    value=int(os.environ.get('RECAP_RAM_HEADROOM_MB','2048'))
    if not 1024<=value<=8192:raise ValueError('Recap RAM headroom must be 1024–8192 MiB')
    return value


def probe(model,url):
    available=available_mb()
    if available is None:raise ResourceWait('Waiting for a reliable available-RAM reading')
    try:
        models=api(url,'/api/ps').get('models',[])
        tags=api(url,'/api/tags').get('models',[])
        artifact=next((row for row in tags if row.get('name')==model),None)
        if not artifact or not isinstance(artifact.get('size'),(int,float)) or artifact['size']<=0:
            raise ValueError('Installed model size unavailable')
        weights=math.ceil(artifact['size']/1048576)
        raw_info=api(url,'/api/show',{'model':model}).get('model_info',{})
        arch=raw_info.get('general.architecture','');prefix=arch+'.attention.'
        fields=['head_count_kv','sliding_window_pattern','sliding_window','key_length','value_length','key_length_swa','value_length_swa']
        keep={'general.architecture',arch+'.block_count',*(prefix+field for field in fields)}
        info={key:value for key,value in raw_info.items() if key in keep}
        resident=next((row for row in models if row.get('name')==model),{})
        context=resident.get('context_length',0)
        return {'available_mb':available,'weights_mb':weights,'model_info':info,'resident_context':context if isinstance(context,int) else 0}
    except (OSError,ValueError,TypeError,KeyError) as exc:
        raise ResourceWait('Waiting to verify the local model RAM budget',available) from exc


def kv_mb(context,info):
    # The deployed Gemma has mixed full/sliding attention. Ollama's measured
    # f16 caches use 32K full-attention cells and 2 x the sliding window.
    # Do not budget every sliding layer as a full 32K cache.
    try:
        arch=info['general.architecture'];prefix=arch+'.attention.'
        layers=info[arch+'.block_count'];heads=info[prefix+'head_count_kv']
        if isinstance(heads,int):heads=[heads]*layers
        sliding=info[prefix+'sliding_window_pattern'];window=info[prefix+'sliding_window']
        if not isinstance(layers,int) or not 0<layers<=256 or len(heads)!=layers or len(sliding)!=layers or not isinstance(window,int) or window<=0:raise ValueError('Unknown attention layout')
        total=0
        for head,is_sliding in zip(heads,sliding):
            suffix='_swa' if is_sliding else ''
            width=info[prefix+'key_length'+suffix]+info[prefix+'value_length'+suffix]
            if not isinstance(head,int) or not isinstance(width,int) or head<=0 or width<=0:raise ValueError('Invalid attention dimensions')
            cells=min(context,window*2) if is_sliding else context
            total+=head*width*cells*2
        return math.ceil(total/1048576)
    except (KeyError,TypeError,ValueError):
        return math.ceil(context/4)


def required_mb(context,weights,headroom,info=None):
    # Model file + architecture-aware KV + 1 GiB runtime/workspace + headroom.
    # It is admission budgeting, not an exact measurement of process RSS.
    return weights+kv_mb(context,info or {})+1024+headroom


def check(context,snapshot,headroom):
    required=headroom if snapshot['resident_context']==context else required_mb(context,snapshot['weights_mb'],headroom,snapshot.get('model_info'))
    if snapshot['available_mb']<required:
        raise ResourceWait(f"Waiting for RAM: {snapshot['available_mb']} MiB available; {required} MiB required",snapshot['available_mb'],required)
    return required


def saved_context(archive):
    plan=archive/'resource-plan.json'
    if plan.exists():return json.loads(plan.read_text())['context']
    requests=sorted(archive.glob('request_*.json'))
    if requests:
        value=json.loads(requests[0].read_text()).get('options',{}).get('num_ctx')
        if isinstance(value,int) and 16384<=value<=32768:return value
    return None


def plan(model,url,ceiling,minimum,archive):
    snapshot=probe(model,url);headroom=headroom_mb();saved=saved_context(archive)
    candidates=[saved] if saved is not None and minimum<=saved<=ceiling else list(dict.fromkeys([ceiling,16384]))
    valid=[value for value in candidates if minimum<=value<=ceiling and value>=16384]
    if not valid:raise ValueError('Review context too small for supplied feedback')
    waiting=None
    for context in valid:
        try:required=check(context,snapshot,headroom)
        except ResourceWait as exc:waiting=exc;continue
        value={**snapshot,'context':context,'headroom_mb':headroom,'admission_required_mb':required,'model':model}
        path=archive/'resource-plan.json';temporary=archive/'resource-plan.tmp'
        temporary.write_text(json.dumps(value,indent=2));os.replace(temporary,path)
        return value
    raise waiting


def admit(plan,url):
    return check(plan['context'],probe(plan['model'],url),plan['headroom_mb'])


def watch(headroom,state=None):
    available=available_mb()
    if available is not None and available>=headroom:
        if state is not None:state['low_samples']=0
        return
    if state is not None:state['low_samples']=state.get('low_samples',0)+1
    if available is None or available<1024 or state is None or state['low_samples']>=2:
        raise ResourceWait('Paused for safe RAM headroom',available,headroom)


def release(model,url):
    try:api(url,'/api/generate',{'model':model,'keep_alive':0})
    except (OSError,ValueError,TypeError):pass
