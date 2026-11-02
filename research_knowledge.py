"""Read existing indexed, approved immutable snapshots; never writes Knowledge."""
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3

import knowledge_lifecycle
from ingestion import ingest_meetings
import notes_ingestion
import text_store


def policy_identifiers(root,ledger_path,owner):
    """Local privacy index only; never supplied to public query planning as evidence."""
    from research_privacy import identifiers_from_private
    root=Path(root).resolve()
    ledger=json.loads(Path(ledger_path).read_text(encoding='utf-8'))
    if Path(ledger['destination']['meetings_root']).resolve()!=root:raise ValueError('Knowledge ledger archive differs')
    states=knowledge_lifecycle.all_states(root);values=set()
    with closing(sqlite3.connect((root/'reviews.sqlite3').as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        audio={Path(r['folder']).name:dict(r) for r in db.execute('SELECT * FROM meetings WHERE owner=?',(owner,))} if 'meetings' in tables else {}
        notes={'notes-'+r['id'][5:]:dict(r) for r in db.execute('SELECT * FROM notes_jobs WHERE owner=?',(owner,))} if 'notes_jobs' in tables else {}
        texts={r['id']:dict(r) for r in db.execute('SELECT * FROM text_docs WHERE owner=?',(owner,))} if 'text_docs' in tables else {}
    for key,entry in list(ledger.get('meetings',{}).items())[:500]:
        record=entry.get('committed') or {};revision=record.get('approval_revision')
        if type(revision) is not int or not record.get('file_id') or not record.get('indexed_at'):continue
        if states.get(key,{}).get('status','active')!='active':continue
        if key in audio:
            folder=Path(audio[key]['folder']);doc=ingest_meetings.document(folder,root,approved_revision=revision)
            metadata=json.loads((folder/'review'/f'r{revision:06d}'/'meeting_metadata.json').read_text())
            for name in metadata.get('participants',[]):
                if isinstance(name,str):
                    values.add(name)
                    values.update(x for x in name.split() if len(x)>2)
        elif key in notes:doc=notes_ingestion.document(root/key,root,owner,revision)
        elif key in texts:doc=text_store.approved_document(root/key,root,owner,revision)
        else:continue
        if doc and doc['approval_sha256']==record.get('approval_sha256'):
            values.update(identifiers_from_private(doc['raw'].decode('utf-8')))
    if len(values)>2000:raise ValueError('Privacy index exceeds configured bound')
    return sorted(values)


def retrieve(root, ledger_path, owner, question):
    root = Path(root).resolve()
    ledger = json.loads(Path(ledger_path).read_text(encoding='utf-8'))
    if Path(ledger['destination']['meetings_root']).resolve() != root:
        raise ValueError('Knowledge ledger archive differs')
    states = knowledge_lifecycle.all_states(root)
    terms = set(re.findall(r'[a-z0-9]{3,}', question.lower()))
    anchors = {word.lower() for word in re.findall(r'\b[A-Z][A-Z0-9]{1,8}\b',question)}
    results = []
    with closing(sqlite3.connect((root/'reviews.sqlite3').as_uri()+'?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        audio = {Path(r['folder']).name: dict(r) for r in db.execute('SELECT * FROM meetings WHERE owner=?', (owner,))} if 'meetings' in tables else {}
        notes = {'notes-'+r['id'][5:]: dict(r) for r in db.execute('SELECT * FROM notes_jobs WHERE owner=?', (owner,))} if 'notes_jobs' in tables else {}
        texts = {r['id']: dict(r) for r in db.execute('SELECT * FROM text_docs WHERE owner=?', (owner,))} if 'text_docs' in tables else {}
    # Bounded archive scan, newest indexed records first. Do not read another owner's files.
    entries = sorted(ledger.get('meetings', {}).items(), key=lambda pair: (pair[1].get('committed') or {}).get('indexed_at', 0), reverse=True)
    for key, entry in entries[:500]:
        state = states.get(key)
        if state and (state['owner'] != owner or state['status'] != 'active'): continue
        record = entry.get('committed') or {}
        if not record.get('file_id') or not record.get('indexed_at'): continue
        revision = record.get('approval_revision')
        if type(revision) is not int or revision < 1: continue
        if key in audio:
            folder = Path(audio[key]['folder'])
            doc = ingest_meetings.document(folder, root, approved_revision=revision)
            approval = json.loads((folder/'review'/f'r{revision:06d}'/'approval.json').read_text())
            if approval.get('owner') != owner: continue
        elif key in notes:
            doc = notes_ingestion.document(root/key, root, owner, revision)
        elif key in texts:
            doc = text_store.approved_document(root/key, root, owner, revision)
        else: continue
        if not doc or doc['approval_sha256'] != record.get('approval_sha256'): continue
        raw = doc['raw'].decode('utf-8')
        if anchors and not any(re.search(r'\b'+re.escape(word)+r'\b',raw,re.I) for word in anchors): continue
        score = sum(min(raw.lower().count(t), 5) for t in terms)
        if score:
            # Anchor on the most discriminating matching term, retain provenance separately.
            matched = sorted((t for t in terms if t in raw.lower()), key=lambda t: (-len(t), t))
            at = max(0, raw.lower().find(matched[0])-400)
            date = re.search(r'^Date:\s*(\d{4}-\d{2}-\d{2})',raw,re.M)
            source_date = date[1] if date else ''
            results.append((score, source_date, record['indexed_at'], {'kind': 'knowledge', 'key': key,
                'revision': revision, 'sha256': doc['sha256'], 'text': raw[at:at+4000],
                'url': '', 'title': doc['filename'], 'source_date':source_date,
                'indexed_at': record['indexed_at']}))
    results.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
    # For "latest" requests preserve recent relevant records rather than claiming all history.
    if re.search(r'\b(latest|recent)\b', question, re.I): results.sort(key=lambda row: (row[1],row[2]), reverse=True)
    return [row[3] for row in results[:3]]
