"""Offline SMARTINI restore verifier. Standard library; never starts apps or calls APIs."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tarfile

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as handle:
        while block:=handle.read(1024*1024):h.update(block)
    return h.hexdigest()

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def fingerprint(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def require(condition,label):
    if not condition:raise ValueError(label)

def safe(root,name):
    p=PurePosixPath(name)
    require(bool(name) and not p.is_absolute() and '..' not in p.parts and '\\' not in name and ':' not in name,'Unsafe recovery path')
    target=Path(root).joinpath(*p.parts)
    require(target.resolve().is_relative_to(Path(root).resolve()),'Recovery path escaped root')
    return target

def verify(snapshot,restored,extract=False):
    snapshot=Path(snapshot);restored=Path(restored)
    manifest=read(snapshot/'MANIFEST.json');transfer=read(snapshot/'TRANSFER.json')
    require(digest(snapshot/'MANIFEST.json')==transfer['manifest_sha256'],'Manifest transfer hash mismatch')
    require(digest(snapshot/'recovery.tar.gz')==transfer['bundle_sha256'],'Backup transfer hash mismatch')
    files=manifest['files']
    require(len({p.casefold() for p in files})==len(files),'Case-colliding restore paths')
    for name in files:safe(restored,name)
    if extract:
        require(not restored.exists(),'Choose a fresh isolated restore directory')
        os.umask(0o077)
        with tarfile.open(snapshot/'recovery.tar.gz') as archive:
            members=archive.getmembers()
            require(len(members)==len(files) and {m.name for m in members}==set(files),'Archive members differ from manifest')
            require(all(m.isfile() and not m.issym() and not m.islnk() for m in members),'Non-regular archive member refused')
            restored.mkdir(parents=True,mode=0o700)
            for member in members:
                target=safe(restored,member.name);target.parent.mkdir(parents=True,exist_ok=True)
                with archive.extractfile(member) as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)
    for name,expected in files.items():
        target=safe(restored,name)
        require(not target.is_symlink() and digest(target)==expected,'Restored file hash mismatch')
    stats={'files':len(files),'audio_sources':0,'audio_revisions':0,'audio_approvals':0,'note_images':0,'notes_revisions':0,'notes_approvals':0,'text_originals':0,'text_revisions':0,'text_approvals':0,'ledger_versions':0,'withdrawal_states':0,'audit_rows':0}
    def mapped(source):
        prefix=manifest['archive_root']+'/'
        require(source.startswith(prefix),'Source reference outside archived root')
        return safe(restored,'archive/'+source[len(prefix):])
    def open_db(name):
        db=sqlite3.connect(safe(restored,'databases/'+name).resolve().as_uri()+'?mode=ro',uri=True)
        db.row_factory=sqlite3.Row
        require(db.execute('PRAGMA integrity_check').fetchall()[0][0]=='ok','SQLite integrity failure')
        require(not db.execute('PRAGMA foreign_key_check').fetchall(),'SQLite foreign-key violation')
        for table,count in manifest['databases'][name].items():
            actual=db.execute('SELECT count(*) FROM "'+table.replace('"','""')+'"').fetchone()[0]
            require(actual==count,'Database table count differs from snapshot')
        return db
    with ExitStack() as stack:
        jobs=open_db('jobs.sqlite3');stack.callback(jobs.close)
        reviews=open_db('reviews.sqlite3');stack.callback(reviews.close)
        owner_by_source={};audio={r['id']:dict(r) for r in jobs.execute('SELECT * FROM jobs')}
        for job in audio.values():
            if not job['folder']:continue
            directory=mapped(job['folder']);owner_by_source[directory.name]=job['owner']
            require((directory/('audio'+Path(job['filename']).suffix.lower())).is_file(),'Audio source missing')
            stats['audio_sources']+=1
        for meeting in reviews.execute('SELECT * FROM meetings'):
            require(audio[meeting['id']]['owner']==meeting['owner'],'Audio owner mismatch')
            directory=mapped(meeting['folder']);state=read(directory/'review.json')
            for revision in reviews.execute('SELECT * FROM revisions WHERE id=?',(meeting['id'],)):
                payload=json.loads(revision['payload']);sub=directory/'review'/f"r{revision['revision']:06d}"
                require(read(sub/'revision.json')==payload,'Audio revision payload mismatch')
                for name,key in [('report.md','report_sha256'),('knowledge.md','knowledge_sha256'),('transcript.json','transcript_sha256'),('meeting_metadata.json','metadata_sha256')]:
                    require(digest(sub/name)==payload[key],'Audio revision hash mismatch')
                stats['audio_revisions']+=1
            a=state.get('last_approved')
            if a:
                sub=directory/'review'/f"r{a['revision']:06d}"
                require(a['owner']==meeting['owner'] and read(sub/'approval.json')==a,'Audio approval identity mismatch')
                require(digest(sub/'knowledge.md')==a['knowledge_sha256'] and digest(sub/'meeting_metadata.json')==a['metadata_sha256'],'Audio approval hash mismatch')
                stats['audio_approvals']+=1
        for job in reviews.execute('SELECT * FROM notes_jobs'):
            directory=safe(restored,'archive/notes-'+job['id'][5:]);owner_by_source[directory.name]=job['owner']
            source=read(directory/'source.json')
            for page in source['pages']:
                require(digest(safe(directory,page['original']))==page['sha256'],'Notes image hash mismatch')
                require(digest(safe(directory,page['derivative']))==page['derivative_sha256'],'Notes derivative hash mismatch')
                stats['note_images']+=1
            for row in reviews.execute('SELECT * FROM notes_revisions WHERE id=?',(job['id'],)):
                require(fingerprint(json.loads(row['payload']))==row['sha256'],'Notes revision hash mismatch')
                stats['notes_revisions']+=1
            for row in reviews.execute('SELECT * FROM notes_approvals WHERE id=?',(job['id'],)):
                a=json.loads(row['payload']);sub=directory/'approved'/f"r{row['revision']:06d}"
                require(a['owner']==job['owner'] and a['id']==job['id'] and read(sub/'approval.json')==a,'Notes approval identity mismatch')
                require(digest(sub/'knowledge.md')==a['knowledge_sha256'],'Notes approved Knowledge hash mismatch')
                require(fingerprint(read(sub/'payload.json'))==a['payload_sha256'] and fingerprint(read(sub/'metadata.json'))==a['metadata_sha256'],'Notes approved payload/metadata hash mismatch')
                stats['notes_approvals']+=1
        for job in reviews.execute('SELECT * FROM text_docs'):
            directory=safe(restored,'archive/'+job['id']);owner_by_source[directory.name]=job['owner']
            first=reviews.execute('SELECT payload FROM text_revisions WHERE id=? AND revision=1',(job['id'],)).fetchone()
            require(read(directory/'original.json')==json.loads(first['payload']),'Text original mismatch');stats['text_originals']+=1
            for row in reviews.execute('SELECT * FROM text_revisions WHERE id=?',(job['id'],)):
                require(fingerprint(json.loads(row['payload']))==row['sha256'],'Text revision hash mismatch');stats['text_revisions']+=1
            for row in reviews.execute('SELECT * FROM text_approvals WHERE id=?',(job['id'],)):
                a=json.loads(row['payload']);sub=directory/'approved'/f"r{row['revision']:06d}"
                require(a['owner']==job['owner'] and a['id']==job['id'] and read(sub/'approval.json')==a,'Text approval identity mismatch')
                require(digest(sub/'knowledge.md')==a['knowledge_sha256'] and fingerprint(read(sub/'payload.json'))==a['payload_sha256'],'Text approved hash mismatch');stats['text_approvals']+=1
        ledger=read(restored/'ingestion/state.json')
        require(ledger['destination']['meetings_root']==manifest['archive_root'],'Ledger archive identity mismatch')
        for entry in ledger['meetings'].values():
            versions=[entry.get('committed'),entry.get('pending'),*entry.get('history',[])]
            for version in filter(None,versions):
                raw=mapped(version['source']).read_bytes();normalized=raw.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n').encode()
                require(hashlib.sha256(normalized).hexdigest()==version['sha256'] and hashlib.sha256(raw).hexdigest()==version['approval_sha256'],'Ledger source/approval hash mismatch');stats['ledger_versions']+=1
        for row in reviews.execute('SELECT * FROM knowledge_lifecycle'):
            require(row['status'] in ('active','pending','removed') and row['generation']>=1,'Invalid withdrawal state')
            require(owner_by_source.get(row['source'])==row['owner'],'Withdrawal owner/source mismatch');stats['withdrawal_states']+=1
        for table in ['knowledge_events','notes_events','text_events','notices']:
            stats['audit_rows']+=reviews.execute('SELECT count(*) FROM '+table).fetchone()[0]
    return {'result':'pass','statistics':stats,'network_calls':0,'services_started':0,'live_state_changed':False,'scope':manifest['scope'],'limitations':['No approved Text record exists in this snapshot' ] if not stats['text_approvals'] else []}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,required=True);parser.add_argument('--restored',type=Path,required=True)
    parser.add_argument('--extract',action='store_true');parser.add_argument('--report',type=Path)
    args=parser.parse_args();result=verify(args.snapshot,args.restored,args.extract)
    if args.report:args.report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
