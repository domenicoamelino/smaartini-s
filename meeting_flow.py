"""Transcript review helpers. Warnings are listening aids, never automatic edits."""
import copy
import math
import re


VERSION = '2.7.0'


def warnings(row):
    reasons=[]
    if row.get('user_reviewed'):
        return reasons
    if row.get('avg_logprob', 0) < -1: reasons.append('Low recognition confidence — listen and check')
    if row.get('temperature', 0) >= .8: reasons.append('Recognition needed a high-temperature fallback')
    if any(word.get('probability', 1) < .35 for word in row.get('words', [])):
        reasons.append('Some words have low recognition confidence — listen and check')
    if re.search(r'(?:[€$£]\s*\d|\d\s*(?:euros?|dollars?|pounds?)\b)', row.get('text',''), re.I):
        reasons.append('Check this amount against the recording')
    if row.get('asr_uncertain'): reasons.append('Overlapping or uncertain speech')
    if row.get('speaker_status') in ('mixed','overlap','uncertain','estimated_overlap'):
        reasons.append('Speaker is uncertain; do not assume an action owner')
    words=re.findall(r'\w+',row.get('text','').casefold());run=1
    for a,b in zip(words,words[1:]):
        run=run+1 if a==b else 1
        if run>=4:
            reasons.append('Repeated words — check whether they were spoken');break
    if re.search(r'[\uac00-\ud7af]',row.get('text','')):
        reasons.append('Unexpected script in this recording — verify the spoken words')
    return reasons


def turns(transcript):
    out=[]
    cut=transcript.get('meeting_end_seconds')
    for i,row in enumerate(transcript['segments'],1):
        flags=warnings(row)
        if cut is not None and row['start']<cut<row['end']:
            flags.append('This turn crosses the selected meeting end; check its wording')
        out.append({'id':f'S{i:06d}','start':row['start'],'end':row['end'],
            'text':row['text'],'excluded':bool(row.get('excluded_from_recap')),
            'reviewed':bool(row.get('user_reviewed')),'corrected':bool(row.get('user_corrected')),
            'speaker':row.get('speaker_name') or row.get('speaker') or 'Unassigned',
            'confirmed_speaker':row.get('speaker_name','') if row.get('speaker_confirmed') else '',
            'note':row.get('review_note',''),'warnings':flags})
    return out


def apply_edits(transcript,obj):
    result=copy.deepcopy(transcript)
    changes=obj.get('turns',{})
    if not isinstance(changes,dict) or len(changes)>500:
        raise ValueError('Save up to 500 turn edits at a time')
    for sid,edit in changes.items():
        if not isinstance(sid,str) or not re.fullmatch(r'S\d{6}',sid) or not isinstance(edit,dict):
            raise ValueError('Invalid transcript turn edit')
        index=int(sid[1:])-1
        if not 0<=index<len(result['segments']):raise ValueError('Transcript turn does not exist')
        row=result['segments'][index]
        if set(edit)-{'text','excluded','reviewed','note','confirmed_speaker'}:raise ValueError('Unsupported turn field')
        if 'confirmed_speaker' in edit:
            name=edit['confirmed_speaker']
            if not isinstance(name,str) or len(name)>100 or any(ord(c)<32 for c in name):
                raise ValueError('Confirmed speaker must be a name of up to 100 characters, or blank')
            if name.strip():
                row.update(speaker_name=name.strip(),speaker_confirmed=True,speaker_status='user_confirmed')
            elif row.get('speaker_confirmed'):
                row.pop('speaker_name',None);row.pop('speaker_confirmed',None)
                row['speaker_status']='assigned' if row.get('speaker') else 'uncertain'
        if 'text' in edit:
            text=edit['text']
            if not isinstance(text,str) or not text.strip() or len(text)>8000 or '\x00' in text:
                raise ValueError('Turn text must contain 1–8000 characters; exclude an unwanted turn instead of erasing it')
            if text.strip()!=row['text'].strip():
                row.setdefault('original_text',row['text']);row['text']=text.strip()
                row['words']=[];row['user_corrected']=True
        for key,target in (('excluded','user_excluded'),('reviewed','user_reviewed')):
            if key in edit:
                if type(edit[key]) is not bool:raise ValueError('Review/exclude values must be true or false')
                row[target]=edit[key]
        if 'note' in edit:
            if not isinstance(edit['note'],str) or len(edit['note'])>1000 or '\x00' in edit['note']:
                raise ValueError('Review notes must be at most 1000 characters')
            row['review_note']=edit['note'].strip()
    if 'meeting_end_seconds' in obj:
        cut=obj['meeting_end_seconds']
        if cut is not None and (type(cut) not in (float,int) or not math.isfinite(cut) or cut<=0 or cut>max(x['end'] for x in result['segments'])):
            raise ValueError('Meeting end must be within the recording, or blank for the full recording')
        result['meeting_end_seconds']=cut
    cut=result.get('meeting_end_seconds')
    for row in result['segments']:
        manual=row.get('user_excluded',row.get('excluded_from_recap',False) and not row.get('excluded_by_boundary',False))
        row['user_excluded']=bool(manual)
        row['excluded_by_boundary']=cut is not None and row['start']>=cut
        row['excluded_from_recap']=bool(manual or row['excluded_by_boundary'])
    if not any(not x.get('excluded_from_recap') for x in result['segments']):
        raise ValueError('Keep at least one meeting turn for the recap')
    result['text']=' '.join(x['text'].strip() for x in result['segments'])
    return result
