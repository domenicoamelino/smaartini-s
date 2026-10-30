"""Read only database-approved Notes snapshots for one explicitly configured owner."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from notes_document import fingerprint,validate_recap,source_digest


def document(directory,root,owner,approved_revision=None):
    directory,root=Path(directory),Path(root).resolve()
    match=re.fullmatch(r'notes-([0-9a-f]{32})',directory.name)
    if not match or directory.is_symlink() or directory.resolve().parent!=root or not owner:
        raise ValueError('Invalid Notes root, owner or directory')
    jid='note-'+match[1]
    with sqlite3.connect((root/'reviews.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        job=db.execute('SELECT * FROM notes_jobs WHERE id=? AND owner=?',(jid,owner)).fetchone()
        if not job or not job['approved']:
            return None
        number=job['approved'] if approved_revision is None else approved_revision
        if type(number) is not int or number<1:
            raise ValueError('Invalid approved Notes revision')
        row=db.execute('SELECT payload FROM notes_approvals WHERE id=? AND revision=?',(jid,number)).fetchone()
        if not row:
            raise ValueError('Notes revision has no committed database approval')
        approval=json.loads(row['payload'])
        revision=db.execute('SELECT sha256 FROM notes_revisions WHERE id=? AND revision=?',(jid,number)).fetchone()
    snapshot=directory/'approved'/f'r{number:06d}'
    for path in [directory/'approved',snapshot,*[snapshot/name for name in ['knowledge.md','payload.json','metadata.json','approval.json']]]:
        if path.is_symlink():
            raise ValueError('Symlink Notes snapshot refused')
    actual=json.loads((snapshot/'approval.json').read_text())
    raw=(snapshot/'knowledge.md').read_bytes()
    payload=json.loads((snapshot/'payload.json').read_text())
    metadata=json.loads((snapshot/'metadata.json').read_text())
    if (actual!=approval or approval.get('owner')!=owner or approval.get('id')!=jid or
        approval.get('revision')!=number or approval.get('source_review_acknowledged') is not True or
        approval.get('image_sha256')!=job['image_sha256'] or metadata.get('owner')!=owner or
        not revision or revision['sha256']!=fingerprint(payload) or
        approval['payload_sha256']!=fingerprint(payload) or
        approval['page_sha256']!=fingerprint(payload['page']) or
        approval['metadata_sha256']!=fingerprint(metadata) or
        approval['knowledge_sha256']!=hashlib.sha256(raw).hexdigest()):
        raise ValueError('Approved Notes snapshot identity/hash mismatch')
    validate_recap(payload['recap'],payload['page'],require_reviewed=False)
    if payload.get('workflow_version')==2:
        import notes_presentation
        notes_presentation.validate(directory,payload)
    manifest_path=directory/'source.json'
    if manifest_path.is_symlink():raise ValueError('Symlink source manifest refused')
    manifest=json.loads(manifest_path.read_text())
    sources=manifest['pages'] if manifest.get('schema')=='smartinis-notes-source/2' else [manifest]
    hashes=[]
    for source in sources:
        name=source['original']
        if Path(name).name!=name or not name.startswith('original') or not name.endswith(('.png','.jpg')):
            raise ValueError('Invalid Notes source path')
        original=directory/name
        if original.is_symlink() or hashlib.sha256(original.read_bytes()).hexdigest()!=source['sha256']:
            raise ValueError('Approved Notes original is missing or changed')
        hashes.append(source['sha256'])
    if source_digest(hashes)!=approval['image_sha256']:
        raise ValueError('Approved Notes picture order changed')
    if not 0<len(raw)<=2*1024*1024:
        raise ValueError('Invalid approved Notes export size')
    sha=hashlib.sha256(raw).hexdigest()
    return {'key':directory.name,'identity':jid,'filename':f'notes__{match[1]}__{sha[:12]}.md',
        'raw':raw,'source':str(snapshot/'knowledge.md'),'sha256':sha,
        'approval_revision':number,'approval_sha256':approval['knowledge_sha256']}
