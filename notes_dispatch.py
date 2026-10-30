"""Enabled Notes uses the existing single worker, oldest ready heavy stage first."""
import os
from heavy_gate import slot
import meeting_review as review
import notes_store as notes
import notes_models


def enabled():
    return os.environ.get('SMARTINIS_NOTES_ENABLED') == '1'


def validate_settings():
    from PIL import Image
    memory=int(os.environ.get('NOTES_MIN_AVAILABLE_MB','8192'))
    context=int(os.environ.get('NOTES_CONTEXT','16384'))
    tokens=int(os.environ.get('NOTES_OUTPUT_TOKENS','4096'))
    if not 512<=memory<=65536 or not 8192<=context<=32768 or not 1024<=tokens<=8192 or tokens>=context-2000:
        raise ValueError('Invalid bounded Notes memory/context settings')


def choose(audio, recap, note):
    candidates=[(stamp,index,kind) for index,(kind,stamp) in enumerate(
        [('audio',audio),('meeting-recap',recap),('notes',note)]) if stamp is not None]
    return min(candidates)[2] if candidates else None


def step(worker):
    with slot(worker.ROOT) as acquired:
        if not acquired:
            return False
        with worker.connect() as db:
            audio=db.execute("SELECT min(created) FROM jobs WHERE state='queued'").fetchone()[0]
        with review.connection(worker.ROOT) as db:
            recap=db.execute("SELECT min(created) FROM tasks WHERE status='queued'").fetchone()[0]
        note=notes.oldest(worker.ROOT)
        kind=choose(audio,recap,note)
        if kind is None:
            return False
        available=notes_models.available_mb()
        if available is None or available<int(os.environ.get('NOTES_MIN_AVAILABLE_MB','8192')):
            # No model is loaded and no task is claimed; the durable queue remains intact.
            return False
        if kind=='audio':
            with worker.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                job=db.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created,id LIMIT 1").fetchone()
                if not job:
                    return False
                db.execute("UPDATE jobs SET state='transcribing' WHERE id=? AND state='queued'",(job['id'],))
            worker.process(dict(job))
            return True
        if kind=='meeting-recap':
            return review.process_next(worker.ROOT,worker.revisions.generate)
        return notes.process_next(worker.ROOT,lambda job,stage,payload,work:
            notes_models.generate(worker.ROOT,job,stage,payload,work,worker.STOP))
