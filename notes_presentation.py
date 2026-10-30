"""Local, inert SVG diagrams and immutable final-review assets. No cloud or model."""
import hashlib
import html
import json
import re
import textwrap
from pathlib import Path
from notes_document import all_blocks,pages,fingerprint,validate_recap


def text_recap(recap):
    names={'summary':'Summary','decision':'Decisions','action':'Actions','open-question':'Open questions'}
    chunks=[]
    for kind,title in names.items():
        items=[i['text'] for i in recap['items'] if i['kind']==kind]
        if items:chunks+=['## '+title,'','\n\n'.join(items),'']
    return '\n'.join(chunks).strip()


def put(directory,raw,extension):
    directory=Path(directory)/'assets';directory.mkdir(mode=0o700,exist_ok=True)
    if directory.is_symlink():raise ValueError('Unsafe asset directory')
    digest=hashlib.sha256(raw).hexdigest();name=digest+'.'+extension;target=directory/name
    if target.is_symlink():raise ValueError('Unsafe diagram asset')
    if target.exists():
        if target.read_bytes()!=raw:raise ValueError('Immutable diagram differs')
    else:
        with target.open('xb') as handle:
            handle.write(raw);handle.flush();__import__('os').fsync(handle.fileno())
    return {'filename':name,'sha256':digest,'mime':{'svg':'image/svg+xml','png':'image/png','jpg':'image/jpeg'}[extension]}


def asset(directory,descriptor):
    name=descriptor.get('filename','')
    if not re.fullmatch(r'[0-9a-f]{64}\.(svg|png|jpg)',name) or name.split('.')[0]!=descriptor.get('sha256'):
        raise ValueError('Invalid diagram asset identity')
    directory=Path(directory)/'assets';target=directory/name
    if directory.is_symlink() or target.is_symlink():raise ValueError('Unsafe diagram asset')
    raw=target.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=descriptor['sha256']:raise ValueError('Diagram asset hash mismatch')
    return {'svg':'image/svg+xml','png':'image/png','jpg':'image/jpeg'}[name.rsplit('.',1)[1]],raw


def build(directory,payload,recap):
    document=payload['page'];validate_recap(recap,document,require_reviewed=True)
    diagrams=[]
    for number,page in enumerate(pages(document),1):
        blocks={b['id']:b for b in page['blocks'] if not b['excluded']}
        relations=[r for r in page['relations'] if r['from'] in blocks and r['to'] in blocks]
        selected={b['id'] for b in blocks.values() if b['kind']=='drawing'}
        for rel in relations:selected.update([rel['from'],rel['to']])
        if not selected:continue
        if len(selected)>60:raise ValueError('Diagram exceeds 60 regions; simplify the reviewed source first')
        ordered=[b for b in blocks.values() if b['id'] in selected];positions={};boxes=[];y=68
        for block in ordered:
            lines=textwrap.wrap(block['text'],65,replace_whitespace=True,drop_whitespace=True)
            height=max(72,len(lines)*20+40);positions[block['id']]=(y,height)
            label=''.join('<tspan x="100" dy="20">'+html.escape(line)+'</tspan>' for line in lines)
            boxes.append(f'<rect x="80" y="{y}" width="620" height="{height}" rx="10" fill="#f1f7f3" stroke="#246348"/><text x="100" y="{y+5}" font-size="14" fill="#173d2d">{label}</text>')
            y+=height+42
        edges=[];descriptions=[]
        for index,rel in enumerate(relations):
            start,sh=positions[rel['from']];end,eh=positions[rel['to']]
            uncertain=bool(rel['uncertainties']);dash=' stroke-dasharray="6 4"' if uncertain else ''
            lane=735+index%8*18
            edges.append(f'<path d="M700 {start+sh/2} H{lane} V{end+eh/2} H700" fill="none" stroke="#246348" stroke-width="2" marker-end="url(#arrow)"{dash}/><text x="{lane+3}" y="{(start+end)/2}" font-size="11">{html.escape(rel["kind"])}</text>')
            descriptions.append(blocks[rel['from']]['text']+' → '+blocks[rel['to']]['text']+(' (uncertain)' if uncertain else ''))
        svg=('<svg xmlns="http://www.w3.org/2000/svg" width="960" height="'+str(y+30)+'" viewBox="0 0 960 '+str(y+30)+'"><title>Reviewed source diagram, picture '+str(number)+'</title><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="#246348"/></marker></defs><rect width="100%" height="100%" fill="white"/><text x="80" y="32" font-family="sans-serif" font-size="18">Picture '+str(number)+' — reviewed regions and relationships</text><g font-family="sans-serif">'+''.join(edges+boxes)+'</g></svg>').encode()
        caption='Picture '+str(number)+'. '+ '; '.join(b['text'] for b in ordered)
        caption+=' Relationships: '+('; '.join(descriptions) if descriptions else 'No explicit connections supplied; none invented.')
        diagrams.append({'asset':put(directory,svg,'svg'),'description':caption,'source_blocks':[b['id'] for b in ordered],
            'origin':'generated-svg','picture':number})
    return {'recap':recap,'final_text':text_recap(recap),'diagrams':diagrams}


def validate(directory,payload):
    approval=payload.get('source_approval') or {}
    if approval.get('page_sha256')!=fingerprint(payload['page']):raise ValueError('Approve the current source before final generation/approval')
    if not isinstance(payload.get('final_text'),str) or not payload['final_text'].strip() or len(payload['final_text'])>60000 or '\x00' in payload['final_text']:
        raise ValueError('Provide a final textual recap up to 60,000 characters')
    validate_recap(payload['recap'],payload['page'],require_reviewed=True)
    diagrams=payload.get('diagrams',[])
    if not isinstance(diagrams,list) or len(diagrams)>10:raise ValueError('Use at most ten diagrams')
    included={b['id'] for b in all_blocks(payload['page']) if not b['excluded']}
    for diagram in diagrams:
        if not isinstance(diagram.get('description'),str) or not diagram['description'].strip() or len(diagram['description'])>30000:
            raise ValueError('Provide a diagram description for Knowledge')
        if not isinstance(diagram.get('source_blocks'),list) or not set(diagram['source_blocks'])<=included:
            raise ValueError('Diagram references an excluded or unknown source region')
        asset(directory,diagram['asset'])
        if diagram.get('original_upload'):asset(directory,diagram['original_upload'])
