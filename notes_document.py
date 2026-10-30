"""Notes v1 document contracts. No inference, authorization, storage or approval side effects.

Callers must authenticate the owner and persist immutable revisions separately.
Model confidence is intentionally not used to authorize source material.
"""
import hashlib
import json
import math
import re


KINDS = {'heading', 'paragraph', 'list-item', 'drawing', 'crossout', 'illegible'}
RELATIONS = {'arrow', 'contains', 'list-child'}
CLAIMS = {'summary', 'decision', 'action', 'open-question'}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _keys(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError('Unexpected or missing document fields')


def _text(value, limit=8000, empty=False):
    if not isinstance(value, str) or len(value) > limit or '\x00' in value or (not empty and not value.strip()):
        raise ValueError('Invalid text')


def _flags(values):
    if not isinstance(values, list) or len(values) > 50:
        raise ValueError('Invalid uncertainty flags')
    for item in values:
        _text(item, 500)


def validate_page(page):
    """Validate a single page. Coordinates are [left, top, right, bottom] in [0,1].

    Human-reviewed flags are accepted only from trusted review actions by callers,
    never copied directly from an inference response.
    """
    if isinstance(page,dict) and page.get('schema')=='smartinis-notes-document/1':
        _keys(page,['schema','image_sha256','pages'])
        if not isinstance(page['pages'],list) or not 1<=len(page['pages'])<=10:
            raise ValueError('Use 1–10 source pictures')
        ids=[]
        for source in page['pages']:
            if source.get('schema')!='smartinis-notes-page/1':
                raise ValueError('Nested Notes documents are not supported')
            validate_page(source)
            ids.extend(b['id'] for b in source['blocks'])
        if len(set(ids))!=len(ids):
            raise ValueError('Block IDs must be unique across pictures')
        if page['image_sha256']!=source_digest([p['image_sha256'] for p in page['pages']]):
            raise ValueError('Picture-set hash does not match its ordered sources')
        return fingerprint(page)
    _keys(page, ['schema', 'image_sha256', 'blocks', 'relations', 'edge_clipping'])
    if page['schema'] != 'smartinis-notes-page/1':
        raise ValueError('Unsupported Notes page schema')
    if not isinstance(page['image_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', page['image_sha256']):
        raise ValueError('Invalid original image hash')
    if type(page['edge_clipping']) is not bool:
        raise ValueError('Invalid clipping status')
    blocks = page['blocks']
    if not isinstance(blocks, list) or not 1 <= len(blocks) <= 500:
        raise ValueError('A page requires 1–500 blocks')
    ids = set()
    for block in blocks:
        _keys(block, ['id', 'kind', 'bbox', 'text', 'uncertainties', 'reviewed', 'excluded'])
        bid = block['id']
        if not isinstance(bid, str) or not re.fullmatch('B[0-9]{6}', bid) or bid in ids:
            raise ValueError('Invalid or duplicate block ID')
        ids.add(bid)
        if not isinstance(block['kind'], str) or block['kind'] not in KINDS:
            raise ValueError('Invalid block kind')
        box = block['bbox']
        if (not isinstance(box, list) or len(box) != 4 or
            any(type(n) not in (int, float) or not math.isfinite(n) or not 0 <= n <= 1 for n in box) or
            box[0] >= box[2] or box[1] >= box[3]):
            raise ValueError('Invalid normalized bounding box')
        _text(block['text'])
        _flags(block['uncertainties'])
        if type(block['reviewed']) is not bool or type(block['excluded']) is not bool:
            raise ValueError('Invalid review status')
        if block['kind'] in {'crossout', 'illegible'} and not block['excluded']:
            raise ValueError('Crossed-out/illegible blocks must be excluded; explicit restoration changes their kind')
    if not isinstance(page['relations'], list) or len(page['relations']) > 1000:
        raise ValueError('Invalid page relations')
    seen = set()
    for relation in page['relations']:
        _keys(relation, ['kind', 'from', 'to', 'uncertainties', 'reviewed'])
        if (not isinstance(relation['kind'], str) or relation['kind'] not in RELATIONS or
            not isinstance(relation['from'], str) or not isinstance(relation['to'], str) or
            relation['from'] not in ids or relation['to'] not in ids or relation['from'] == relation['to']):
            raise ValueError('Invalid relation endpoints')
        key = (relation['kind'], relation['from'], relation['to'])
        if key in seen:
            raise ValueError('Duplicate page relation')
        seen.add(key)
        _flags(relation['uncertainties'])
        if type(relation['reviewed']) is not bool:
            raise ValueError('Invalid relation review status')
    return fingerprint(page)


def validate_recap(recap, page, *, require_reviewed=True):
    """Check traceability, not semantic entailment. Human review remains required."""
    source_hash = validate_page(page)
    _keys(recap, ['schema', 'page_sha256', 'items'])
    if recap['schema'] != 'smartinis-notes-recap/1' or recap['page_sha256'] != source_hash:
        raise ValueError('Recap belongs to a different source revision')
    if not isinstance(recap['items'], list) or not 1 <= len(recap['items']) <= 100:
        raise ValueError('Recap requires 1–100 supported items')
    blocks = {b['id']: b for b in all_blocks(page)}
    for item in recap['items']:
        _keys(item, ['kind', 'text', 'evidence'])
        if not isinstance(item['kind'], str) or item['kind'] not in CLAIMS:
            raise ValueError('Invalid recap item kind')
        _text(item['text'], 2000)
        if not isinstance(item['evidence'], list) or not 1 <= len(item['evidence']) <= 20:
            raise ValueError('Every item requires evidence')
        for evidence in item['evidence']:
            _keys(evidence, ['block_id', 'quote'])
            if not isinstance(evidence['block_id'], str):
                raise ValueError('Invalid evidence ID')
            block = blocks.get(evidence['block_id'])
            _text(evidence['quote'])
            if not block or (require_reviewed and not block['reviewed']) or block['excluded']:
                raise ValueError('Evidence requires a reviewed, included source block')
            if evidence['quote'] not in block['text']:
                raise ValueError('Evidence quote does not match the reviewed source')
    return fingerprint(recap)


def pages(document):
    return document['pages'] if document.get('schema')=='smartinis-notes-document/1' else [document]


def all_blocks(document):
    return [block for page in pages(document) for block in page['blocks']]


def all_relations(document):
    return [relation for page in pages(document) for relation in page['relations']]


def source_digest(hashes):
    if not hashes:
        raise ValueError('At least one source picture is required')
    return hashes[0] if len(hashes)==1 else fingerprint({'ordered_original_sha256':hashes})


def combine_pages(sources):
    import copy
    result=[];counter=0
    for original in sources:
        source=copy.deepcopy(original);mapping={}
        for block in source['blocks']:
            counter+=1;mapping[block['id']]=f'B{counter:06d}'
        for block in source['blocks']:
            block['id']=mapping[block['id']]
        for relation in source['relations']:
            relation['from']=mapping[relation['from']];relation['to']=mapping[relation['to']]
        result.append(source)
    if len(result)==1:
        validate_page(result[0]);return result[0]
    document={'schema':'smartinis-notes-document/1','image_sha256':source_digest([p['image_sha256'] for p in result]),'pages':result}
    validate_page(document);return document
