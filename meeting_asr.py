#!/usr/bin/env python3
"""Standalone cached local Whisper transcription; no production integration."""
import argparse
import dataclasses
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time

OPTIONS = {'language':None,'task':'transcribe','multilingual':True,'beam_size':5,
           'vad_filter':True,'vad_parameters':{'min_silence_duration_ms':500},
           'word_timestamps':True,'condition_on_previous_text':True,
           'temperature':[0.0,0.2,0.4,0.6,0.8,1.0], 'initial_prompt':None,'hotwords':None}
REPOSITORIES = {'turbo':'mobiuslabsgmbh/faster-whisper-large-v3-turbo',
                'large-v3':'Systran/faster-whisper-large-v3'}
PROFILES = {'baseline':OPTIONS,
            'speech-preserving':{**OPTIONS,'vad_filter':False,'vad_parameters':None}}


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def save(path,data):
    path=Path(path);tmp=path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(path)


def model_directory(model):
    root=Path.home()/'.cache/huggingface/hub'/('models--'+REPOSITORIES[model].replace('/','--'))
    revision='0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf' if model=='turbo' else (root/'refs/main').read_text().strip()
    if not revision or any(c not in '0123456789abcdef' for c in revision):raise ValueError('Invalid cached revision')
    folder=root/'snapshots'/revision
    for name in ('model.bin','config.json','tokenizer.json'):
        if not (folder/name).is_file():raise FileNotFoundError('Incomplete cached model: '+str(folder))
    return folder,revision


def signature(audio,model,threads,profile='baseline'):
    folder,revision=model_directory(model)
    # The immutable cached revision and its local file stat identify existing weights;
    # the setup manifest separately records the full model.bin SHA-256 once.
    stat=(folder/'model.bin').stat()
    data={'audio_sha256':sha(audio),'model':model,'repository':REPOSITORIES[model],
          'revision':revision,'weights_bytes':stat.st_size,'weights_mtime_ns':stat.st_mtime_ns,
          'options':PROFILES[profile],'device':'cpu','compute_type':'int8','threads':threads,
          'versions':{x:importlib.metadata.version(x) for x in ('faster-whisper','ctranslate2','av')}}
    key=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    return folder,data,key


def write_text_outputs(result,output):
    (output/'transcript.txt').write_text(result['text']+'\n',encoding='utf-8')
    (output/'transcript.md').write_text('\n\n'.join(
        f"[{int(x['start'])//60:02}:{int(x['start'])%60:02}–{int(x['end'])//60:02}:{int(x['end'])%60:02}] {x['text'].strip()}" for x in result['segments'])+'\n',encoding='utf-8')


def transcribe(audio,model,output,threads=8,profile='speech-preserving',progress=None,stop=None):
    os.environ['HF_HUB_OFFLINE']='1';os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    os.environ['DO_NOT_TRACK']='1'
    from faster_whisper import WhisperModel
    audio=Path(audio);output=Path(output)
    folder,config,key=signature(audio,model,threads,profile)
    result_path=output/'transcript.json'
    if result_path.exists():
        previous=json.loads(result_path.read_text())
        if previous.get('cache_key')!=key:raise RuntimeError('Output belongs to a different configuration; choose a new directory')
        write_text_outputs(previous,output)
        if progress: progress({'phase':'complete','cached':True})
        print('Reused completed cached transcription',output,flush=True);return previous
    output.mkdir(parents=True,exist_ok=True)
    save(output/'run.json',{'cache_key':key,**config})
    start=time.monotonic()
    save(output/'progress.json',{'phase':'loading','model':model,'elapsed_seconds':0})
    if progress: progress({'phase':'loading'})
    engine=WhisperModel(str(folder),device='cpu',compute_type='int8',cpu_threads=threads,
                        num_workers=1,local_files_only=True)
    loaded=time.monotonic()
    segments,info=engine.transcribe(str(audio),**config['options'])
    result=[]
    for segment in segments:
        if stop is not None and stop.is_set(): raise InterruptedError('Transcription stopped; partial/cache retained')
        item=dataclasses.asdict(segment)
        result.append(item)
        save(output/'segments.partial.json',result)
        save(output/'progress.json',{'phase':'transcribing','model':model,
             'elapsed_seconds':round(time.monotonic()-start,1),'audio_position':segment.end,
             'audio_duration':info.duration,'segments':len(result)})
        if progress: progress({'phase':'transcribing','audio_position':segment.end,'audio_duration':info.duration})
    elapsed=time.monotonic()-start
    if sha(audio)!=config['audio_sha256']:raise RuntimeError('Audio changed during transcription')
    out={'cache_key':key,**config,'audio_file':audio.name,'audio_duration_seconds':info.duration,
         'duration_after_vad':info.duration_after_vad,'initial_detected_language':info.language,
         'initial_language_probability':info.language_probability,'load_seconds':loaded-start,
         'wall_seconds':elapsed,'realtime_factor':elapsed/info.duration if info.duration else None,
         'segments':result,'text':' '.join(x['text'].strip() for x in result),
         'speaker_attribution':'Not performed; no named speakers inferred'}
    save(result_path,out)
    write_text_outputs(out,output)
    save(output/'progress.json',{'phase':'complete','wall_seconds':elapsed,'segments':len(result)})
    print(f'Complete: {model}, {elapsed:.1f}s, {len(result)} segments',flush=True)
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('audio',type=Path);p.add_argument('--model',choices=REPOSITORIES,default='turbo')
    p.add_argument('--output',required=True,type=Path);p.add_argument('--threads',type=int,default=8)
    p.add_argument('--profile',choices=PROFILES,default='baseline')
    a=p.parse_args()
    if not 1<=a.threads<=16:p.error('Use 1–16 CPU threads')
    transcribe(a.audio,a.model,a.output,a.threads,a.profile)


if __name__=='__main__':main()
