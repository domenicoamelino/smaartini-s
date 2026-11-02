#!/usr/bin/env python3
"""Durable single-worker audio -> local meeting report service. Python 3.10+."""
import datetime as dt
from contextlib import contextmanager
import gc
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import sqlite3
import threading
import time
from urllib.parse import unquote, urlsplit
import uuid

import meeting_report as report
import meeting_knowledge as knowledge
import meeting_speakers as speakers
import meeting_review as review
import meeting_draft as revisions
import meeting_asr as asr
import meeting_flow as flow
import meeting_notifications as notifications
import meeting_dashboard as dashboard

def _notes_enabled():
    return os.environ.get('SMARTINIS_NOTES_ENABLED') == '1'

ROOT = Path(os.environ.get("MEETING_ROOT", str(Path.home() / "ai-platform/meetings"))).expanduser()
DB = ROOT / "jobs.sqlite3"
API_KEY = os.environ.get("MEETING_API_KEY", "")
MAX_BYTES = int(os.environ.get("MEETING_MAX_BYTES", 512 * 1024 * 1024))
STOP = threading.Event()
UPDATE_LOCK = threading.RLock()
EXTENSIONS = {".m4a", ".mp3", ".wav", ".mpeg", ".mpga", ".mp4", ".ogg", ".webm", ".flac", ".aac"}


@contextmanager
def connect():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    try:
        with c:
            yield c
    finally:
        c.close()


def init():
    ROOT.mkdir(parents=True, exist_ok=True)
    review.init(ROOT)
    if os.environ.get("SMARTINIS_TEXT_ENABLED")=="1":
        import text_store
        text_store.init(ROOT)
    if _notes_enabled():
        import notes_store
        import notes_dispatch
        notes_dispatch.validate_settings()
        notes_store.init(ROOT)
    with connect() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("""CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, token TEXT UNIQUE, owner TEXT, request_key TEXT,
            created REAL, updated REAL, state TEXT, detail TEXT, percent REAL,
            filename TEXT, folder TEXT, error TEXT, UNIQUE(owner, request_key))""")
        columns = {row[1] for row in c.execute("PRAGMA table_info(jobs)")}
        for name, definition in (("audio_language", "TEXT"), ("mixed_languages", "INTEGER"), ("report_language", "TEXT")):
            if name not in columns:
                c.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")


def recover():
    review.recover(ROOT)
    if _notes_enabled():
        import notes_store
        notes_store.recover(ROOT)
    with connect() as c:
        c.execute("UPDATE jobs SET state='queued',detail='Restarted; queued for a fresh processing attempt',updated=? WHERE state IN ('transcribing','analyzing')", (time.time(),))
        c.execute("UPDATE jobs SET state='waiting_upload',detail='Upload interrupted; choose the file again',updated=? WHERE state='uploading'", (time.time(),))


def get_job(jid):
    with connect() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
    return dict(row) if row else None


def update(jid, **values):
    with UPDATE_LOCK:
        values["updated"] = time.time()
        with connect() as c:
            c.execute("UPDATE jobs SET " + ",".join(k + "=?" for k in values) + " WHERE id=?", [*values.values(), jid])
        job = get_job(jid)
        if job and job["folder"]:
            report.save(Path(job["folder"]) / "job.json", public(job))


def public(job):
    return {k: job[k] for k in ("id", "created", "updated", "state", "detail", "percent", "filename", "error")}


def create_session(owner, request_key, audio_language="auto", mixed_languages=False, report_language=None):
    language_codes = {"auto", "en", "nl", "it", "de", "fr", "es", "pt", "zh", "ja", "ko", "ar", "hi", "ru", "uk", "pl", "tr"}
    report_language = report_language or os.environ.get('REPORT_LANGUAGE', 'English')
    if not isinstance(audio_language, str) or audio_language not in language_codes or type(mixed_languages) is not bool or not isinstance(report_language, str) or report_language not in report.REPORT_LANGUAGES:
        raise ValueError('Invalid language preference')
    now = time.time()
    with connect() as c:
        c.execute("INSERT OR IGNORE INTO jobs (id,token,owner,request_key,created,updated,state,detail,audio_language,mixed_languages,report_language) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (uuid.uuid4().hex, secrets.token_urlsafe(32), owner, request_key, now, now, "waiting_upload", "Choose a meeting recording", audio_language, int(mixed_languages), report_language))
        row = dict(c.execute("SELECT * FROM jobs WHERE owner=? AND request_key=?", (owner, request_key)).fetchone())
    return {**public(row), "upload_token": row["token"]}


def process(job):
    jid = job["id"]
    folder = Path(job["folder"])
    audio = folder / ("audio" + Path(job["filename"]).suffix.lower())
    old_log = report.log
    try:
        update(jid, state="transcribing", detail="Loading multilingual Whisper model", percent=None, error=None)
        metadata_path = folder / "meeting_metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
        def asr_progress(value):
            if value.get('phase') == 'transcribing':
                position, duration = value['audio_position'], value['audio_duration']
                update(jid, detail=f"Transcribing {report.stamp(position)} of {report.stamp(duration)}",
                       percent=min(99,100*position/duration) if duration else None)
            elif value.get('cached'):
                update(jid, detail="Using the completed cached transcript; no ASR rerun", percent=99)
        transcript = asr.transcribe(audio, 'turbo', folder/'asr',
                    threads=int(os.environ.get('WHISPER_THREADS','8')),
                    profile='speech-preserving', progress=asr_progress, stop=STOP)
        transcript['workflow'] = 'review-first/1'
        segments = transcript['segments']
        report.save(folder/'transcript.json', transcript)
        # Source ASR is immutable; review edits live in numbered snapshots.
        if not (folder/'transcript.original.json').exists():
            report.save(folder/'transcript.original.json', transcript)
        gc.collect()
        speaker_warning = None
        # Keep the existing transcribing state: queue recovery and ingestion busy checks already know it.
        if speakers.options(metadata)['diarization_enabled']:
            report.save(folder / "transcript.raw.json", transcript)
            update(jid, detail="Identifying different speakers on CPU; recap will follow", percent=None)
            try:
                result = speakers.run(audio, folder, metadata, transcript["audio_duration_seconds"], STOP,
                                      lambda message: update(jid, detail=message, percent=None))
                aligned = speakers.align_words(segments, result['turns'], result['exclusive_turns'])
                if not result['turns']:
                    raise ValueError('No speaker turns found')
                result['alignment_summary'] = {
                    'word_timed_source_segments': sum(bool(row.get('words')) for row in segments),
                    'word_aligned_turns': sum(row.get('alignment')=='word-timestamps' for row in aligned),
                    'segment_fallback_turns': sum(row.get('alignment')=='segment-fallback' for row in aligned),
                    'assigned_words_by_voice': {label: sum(len(row.get('words',[])) for row in aligned if row.get('speaker')==label)
                                                for label in sorted({row['speaker'] for row in aligned if row.get('speaker')})}}
                report.save(folder / "diarization.json", result)
                transcript['segments'] = aligned
                transcript['diarization'] = {'status': 'completed', 'anonymous_labels': True,
                                             'model': result.get('model'), 'alignment': 'word-timestamps-with-overlap-flags'}
            except speakers.Interrupted:
                # Restart recovery requeues this job. Never mark shutdown as success.
                raise
            except Exception as exc:
                speaker_warning = "Speaker separation unavailable; recap uses the original transcript"
                old_log(f"Job {jid}: diarization fallback ({type(exc).__name__}): {exc}")
                report.save(folder / "diarization.json", {'schema': 'meeting-diarization/2.5.2',
                            'status': 'failed', 'reason_type': type(exc).__name__, 'fallback': 'original_transcript'})
                transcript['diarization'] = {'status': 'failed', 'fallback': 'original_transcript'}
            report.save(folder / "transcript.json", transcript)
        report.atomic(folder/'transcript.md', report.transcript_md(report.load_source(folder/'transcript.json')[2]))
        report.atomic(folder/'report.md', 'Transcript ready for review. Confirm it in the dashboard to generate your recap.\n')
        update(jid, state="completed", detail="Transcript ready — review and confirm it to generate the recap" + (". "+speaker_warning if speaker_warning else ""), percent=100)
        review.ensure(ROOT, get_job(jid))
        review.notice(ROOT, 'transcript-ready:'+jid, job['owner'], jid, 'Transcript ready for review: '+metadata.get('meeting_title',job.get('filename','Meeting')))
    except InterruptedError:
        update(jid, state="queued", detail="Interrupted; completed ASR cache retained for restart", percent=None)
    except speakers.Interrupted:
        update(jid, state="queued", detail="Interrupted during speaker separation; queued for restart", percent=None)
    except Exception as e:
        old_log(f"Job {jid} failed: {e}")
        update(jid, state="failed", detail="Processing failed; source and partial results retained", percent=None, error=str(e)[:1500])
        review.notice(ROOT, 'failed:'+jid, job['owner'], jid, 'Meeting processing failed; source retained')
    finally:
        report.log = old_log


def worker():
    while not STOP.wait(1):
        if _notes_enabled():
            import notes_dispatch
            notes_dispatch.step(__import__(__name__))
            continue
        with connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if row:
                c.execute("UPDATE jobs SET state='transcribing',updated=? WHERE id=?", (time.time(), row["id"]))
        if row:
            process(dict(row))
        else:
            review.process_next(ROOT, revisions.generate)


class Handler(BaseHTTPRequestHandler):
    server_version = "MeetingWorker/2.7.1"

    def log_message(self, *_):
        pass  # Never log capability tokens from browser URLs.

    def setup(self):
        super().setup()
        self.connection.settimeout(600)

    def send(self, status, data, content_type="application/json"):
        blob = (json.dumps(data, ensure_ascii=False).encode() if content_type == "application/json" else data.encode())
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(blob)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        if dashboard.is_path(self.path) or self.path.startswith('/meeting-ui/notes') or self.path.startswith('/meeting-ui/text'):
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; media-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
        elif self.path.startswith("/meeting-ui/"):
            # The iframe has an opaque origin. Its scoped bearer capability grants access.
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Filename, X-Meeting-Metadata")
        self.end_headers()
        self.wfile.write(blob)

    def do_OPTIONS(self):
        if dashboard.is_path(self.path) or self.path.startswith('/meeting-ui/notes') or self.path.startswith('/meeting-ui/text'):
            self.send(405, {'error': 'Cross-origin dashboard requests are not supported'})
        elif self.path.startswith("/meeting-ui/"):
            self.send(200, {})
        else:
            self.send(404, {"error": "Not found"})

    def auth(self):
        supplied = self.headers.get("Authorization", "")
        return hmac.compare_digest(supplied, "Bearer " + API_KEY)

    def capability(self, token):
        with connect() as c:
            row = c.execute("SELECT * FROM jobs WHERE token=?", (token,)).fetchone()
        if not row or time.time() - row["created"] > 86400:
            return None
        return dict(row)

    def length(self, limit):
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Invalid Content-Length")
        if not 0 < n <= limit:
            raise ValueError(f"Body must be between 1 and {limit} bytes")
        return n

    def do_GET(self):
        try:
            self.route_get()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except review.Conflict as e:
            self.send(409, {"error": str(e)})
        except Exception as e:
            self.send(500, {"error": str(e)[:500]})

    def route_get(self):
        if os.environ.get('SMARTINIS_RESEARCH_ENABLED')=='1':
            import research_routes
            if research_routes.route(self,__import__(__name__),'GET'):return
        if os.environ.get('SMARTINIS_TEXT_ENABLED')=='1':
            import text_web
            if text_web.route(self,__import__(__name__),'GET'):return
        if _notes_enabled():
            import notes_web
            import notes_card
            if notes_card.route(self, __import__(__name__), 'GET'):
                return
            if notes_web.route(self, __import__(__name__), 'GET'):
                return
        if dashboard.route(self, __import__(__name__), 'GET'):
            return
        parts = urlsplit(self.path).path.strip("/").split("/")
        if parts == ["health"]:
            return self.send(200, {"ok": True, "worker_alive": self.server.worker_thread.is_alive(),
                                   "dashboard_version": dashboard.VERSION, "workflow_version": flow.VERSION,
                                   **({"text_enabled":True,"text_version":"0.1.0"} if os.environ.get("SMARTINIS_TEXT_ENABLED")=="1" else {}),
                                   **({'notes_enabled':True,'notes_version':'0.3.0'} if _notes_enabled() else {})})
        if len(parts) == 4 and parts[:2] == ["v1", "sessions"] and parts[3] == 'review':
            job = self.review_job(parts[2])
            if job is None:
                return
            review.ensure(ROOT, job)
            return self.send(200, review.view(ROOT, job['id'], job['owner']))
        if len(parts) == 3 and parts[:2] == ["v1", "sessions"]:
            if not self.auth():
                return self.send(401, {"error": "Unauthorized"})
            job = get_job(parts[2])
            if not job or job["owner"] != self.headers.get("X-Owner-Id"):
                return self.send(404, {"error": "Not found"})
            result = public(job)
            if job["state"] == "completed":
                folder = Path(job["folder"])
                result.update(report=(folder / "report.md").read_text(encoding="utf-8"),
                              transcript=(folder / "transcript.md").read_text(encoding="utf-8"), archive=str(folder))
                review.ensure(ROOT, job)
                result.update(review.view(ROOT, job['id'], job['owner']))
            return self.send(200, result)
        if len(parts) == 3 and parts[0] == "meeting-ui" and parts[1] in ("view", "status"):
            job = self.capability(parts[2])
            if not job:
                return self.send(404, {"error": "Upload session missing or expired; start a new request"})
            if parts[1] == "view":
                template = (Path(__file__).parent / "upload.html").read_text(encoding="utf-8")
                return self.send(200, template.replace("__TOKEN__", job["token"]), "text/html")
            return self.send(200, public(job))
        self.send(404, {"error": "Not found"})

    def review_job(self, jid):
        if not self.auth():
            self.send(401, {'error': 'Unauthorized'})
            return None
        job = get_job(jid)
        if not job or job['owner'] != self.headers.get('X-Owner-Id'):
            self.send(404, {'error': 'Not found'})
            return None
        return job

    def do_POST(self):
        try:
            self.route_post()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except review.Conflict as e:
            self.send(409, {"error": str(e)})
        except ValueError as e:
            self.send(400, {"error": str(e)})
        except Exception as e:
            self.send(500, {"error": str(e)[:500]})

    def route_post(self):
        if os.environ.get('SMARTINIS_RESEARCH_ENABLED')=='1':
            import research_routes
            if research_routes.route(self,__import__(__name__),'POST'):return
        if os.environ.get('SMARTINIS_TEXT_ENABLED')=='1':
            import text_web
            if text_web.route(self,__import__(__name__),'POST'):return
        if _notes_enabled():
            import notes_web
            import notes_card
            if notes_card.route(self, __import__(__name__), 'POST'):
                return
            if notes_web.route(self, __import__(__name__), 'POST'):
                return
        if dashboard.route(self, __import__(__name__), 'POST'):
            return
        parts = urlsplit(self.path).path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ['v1', 'sessions'] and parts[3] == 'review':
            job = self.review_job(parts[2])
            if job is None:
                return
            review.ensure(ROOT, job)
            obj = json.loads(self.rfile.read(self.length(256000)))
            return self.send(200, review.act(ROOT, job['id'], job['owner'], obj))
        if parts == ["v1", "sessions"]:
            if not self.auth():
                return self.send(401, {"error": "Unauthorized"})
            obj = json.loads(self.rfile.read(self.length(8192)))
            owner = obj.get("owner", "")
            key = obj.get("request_key", "")
            if not isinstance(owner, str) or not owner or not isinstance(key, str) or not key or len(owner) > 200 or len(key) > 300:
                raise ValueError("owner and request_key required")
            return self.send(200, create_session(owner, key, obj.get('audio_language', 'auto'),
                                                obj.get('mixed_languages', False), obj.get('report_language')))
        if len(parts) == 3 and parts[:2] == ["meeting-ui", "upload"]:
            job = self.capability(parts[2])
            if not job:
                return self.send(404, {"error": "Session expired"})
            if time.time() - job["created"] > 1800:
                return self.send(410, {"error": "Choose a new upload session (upload window is 30 minutes)"})
            filename = Path(unquote(self.headers.get("X-Filename", "audio.m4a")).replace("\\", "/")).name[:180]
            if Path(filename).suffix.lower() not in EXTENSIONS:
                raise ValueError("Unsupported audio filename extension")
            raw_metadata = self.headers.get("X-Meeting-Metadata", "")
            if not raw_metadata or len(raw_metadata) > 6000:
                raise ValueError("Meeting title and date are required (metadata header <=6000 characters)")
            metadata = knowledge.validate_metadata(json.loads(unquote(raw_metadata)), require_languages=True)
            size = self.length(MAX_BYTES)
            with connect() as c:
                cur = c.execute("UPDATE jobs SET state='uploading',detail='Receiving recording',updated=? WHERE id=? AND state='waiting_upload'", (time.time(), job["id"]))
                if cur.rowcount != 1:
                    return self.send(409, {"error": "This session already has an upload or job"})
            slug = re.sub(r"[^a-z0-9]+", "-", Path(filename).stem.lower()).strip("-")[:50] or "meeting"
            folder = ROOT / ("processed-" + dt.date.today().isoformat() + "_" + slug + "_" + job["id"])
            folder.mkdir(mode=0o700, exist_ok=True)
            partial = folder / "audio.part"
            try:
                digest = hashlib.sha256()
                remaining = size
                with partial.open("wb") as f:
                    while remaining:
                        block = self.rfile.read(min(1024 * 1024, remaining))
                        if not block:
                            raise ValueError("Upload interrupted")
                        remaining -= len(block)
                        digest.update(block)
                        f.write(block)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(partial, folder / ("audio" + Path(filename).suffix.lower()))
                report.save(folder / "audio_source.json", {"filename": filename, "sha256": digest.hexdigest(), "bytes": size,
                                                           "received_at": dt.datetime.now().astimezone().isoformat(), **metadata})
                report.save(folder / "meeting_metadata.json", metadata)
                update(job["id"], state="queued", detail="Queued for the MINISFORUM worker", filename=filename, folder=str(folder), percent=None)
            except Exception:
                update(job["id"], state="waiting_upload", detail="Upload interrupted; choose the file again")
                raise
            return self.send(202, public(get_job(job["id"])))
        self.send(404, {"error": "Not found"})


def main():
    if len(API_KEY) < 32:
        raise SystemExit("Set MEETING_API_KEY to a random secret of at least 32 characters")
    os.umask(0o077)
    init()
    # One service instance only; prevents duplicate model workers on the same DB.
    import fcntl
    lock = (ROOT / "worker.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Another meeting worker already owns this archive")
    recover()
    server = ThreadingHTTPServer((os.environ.get("MEETING_BIND", "127.0.0.1"), int(os.environ.get("MEETING_PORT", "8765"))), Handler)
    server.daemon_threads = True
    server.worker_thread = threading.Thread(target=worker, daemon=True)
    server.worker_thread.start()
    if os.environ.get('SMARTINIS_RESEARCH_ENABLED')=='1':
        import research_runtime
        server.research_thread = research_runtime.start(ROOT, STOP)
    threading.Thread(target=notifications.loop, args=(ROOT, STOP), daemon=True).start()
    def stop(*_):
        STOP.set()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        print(f"Meeting worker on {server.server_address}; archive {ROOT}", flush=True)
        server.serve_forever()
    finally:
        STOP.set()
        server.server_close()
        # A shutdown interrupts any in-flight model work. Restart requeues that job.


if __name__ == "__main__":
    main()
