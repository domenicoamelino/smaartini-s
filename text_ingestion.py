"""Approved text adapter and ingestion-success outbox; no direct Telegram calls."""
import hashlib
import sqlite3
import time
import text_store

def document(directory,root,owner,approved_revision=None):
    return text_store.approved_document(directory,root,owner,approved_revision)

def notify(root,doc,collection):
    if doc.get('kind')!='text':return
    key='text-indexed:'+doc['identity']+':'+str(doc['approval_revision'])+':'+doc['sha256']+':'+hashlib.sha256(collection.encode()).hexdigest()[:16]
    try:
        with text_store.connection(root) as db:
            db.execute('INSERT OR IGNORE INTO notices VALUES (?,?,?,?,?,?)',
                (key,doc['owner'],doc['identity'],'Text '+doc.get('title','')+' (r'+str(doc['approval_revision'])+') successfully ingested into Knowledge.','pending',time.time()))
    except sqlite3.Error:
        raise ValueError('Ingestion committed; text notification will be reconciled on the next successful run') from None
