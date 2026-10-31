# SMARTINI’s Text 0.1.0

## User flow

Import `openwebui_text_pipe.py` as a **new** SMARTINI’s Text Function, preserving the existing Audio and Notes Functions. Copy `WORKER_URL`, `WORKER_API_KEY` and `PUBLIC_ORIGIN` from the working audio Function into its server-side valves. Never paste the key into chat or source exports. The backend must be enabled before using the Function.

In a saved chat, request the Text card. Add a title, a valid date and Markdown text, then click **Save draft & open review**. The card supports Markdown preview, up to 120,000 characters / 512 KiB. It saves the submitted text without a model call, transcription, rewriting or heavy-job queue entry. The original JSON and every saved revision retain the exact submitted strings. Browser text-area newline handling is accounted for; Knowledge transport follows the existing normalized LF policy.

The entry appears beside Audio and Notes at `/meeting-ui/dashboard/`, with source filter **Text**. Review formatted Markdown, edit title/date/body, save revisions and view older revisions read-only. Click **Approve for Knowledge** after explicitly acknowledging the exact saved text. Saving is not approval. Later edits remain drafts until reapproved; older approved snapshots remain eligible until a replacement is approved.

The existing automatic **03:00 Europe/Amsterdam** ingestion processes approved snapshots. The Text-specific InfoRag notification is queued only after successful ingestion is confirmed and the managed ledger is committed. It includes the approved title, revision and dashboard link. Repeated runs do not create duplicate notices. An interrupted outbox write is reconciled on the next verified unchanged run. The existing notifier's uncertain-delivery policy remains: a lost Telegram response is not blindly retried. The normal nightly run summary remains in addition to per-Text success notices.

Draft creation and approval do not themselves send an ingestion-success notification. Knowledge indexing still uses Open WebUI's existing embedding pipeline; no text-generation model is called by Text submission or review.

## Storage and access

New `text_*` tables share the existing private `reviews.sqlite3`. `text-<uuid>/original.json` preserves the first submission; `approved/rNNNNNN/` contains immutable payload/Knowledge/approval snapshots. All content is owner-scoped, hashes are validated, and audit events record submit/save/approve. Existing archive backup coverage must include these folders and tables. Private runtime text and credentials stay outside Git.

The upload card has an expiring, unguessable submit-only capability. It cannot approve or read saved material. Review uses the real WebUI cookie and signed owner/cookie/origin-bound CSRF. Text accepts an explicitly configured public HTTPS origin behind the existing proxy; arbitrary forwarded headers cannot grant access. The existing allowlisted owner/private collection is reused. Other owners require their own explicit private destination.

Preview reuses the local licensed Marked lexer and safe DOM renderer. Raw HTML is displayed as text, image references render as alt text, and no external image is fetched automatically. Executable URL schemes are not made clickable. No CDN or new runtime dependency is introduced.

## Activation and rollback

Review the source package, live-source hashes and idle queues first. Back up the source/config, full private archive, coherent SQLite snapshots, ingestion ledger and notification binding. Install the included runtime payload into the existing worker and ingestion paths. Add only:

```text
SMARTINIS_TEXT_ENABLED=1
TEXT_ALLOWED_OWNERS=<existing intended owner ID>
TEXT_PUBLIC_ORIGIN=<existing public HTTPS WebUI origin, no path>
```

Add `include_text: true` and `text_owner_id` to the existing private ingestion configuration, preserving collection/API key/root/ledger and existing Notes settings. Copy matching `text_store.py` and `text_ingestion.py` helpers into ingestion. Keep the existing timer and monitor override. No new permanent service is needed. Restart the idle `minisforum-meetings.service` with administrator access, then verify health reports Text 0.1.0 alongside Notes 0.3.0 and meeting processing 2.7.1. Import the new Function manually and keep its valves private.

Rollback restores backed-up code/config with the queues idle and retains all newer Text/Audio/Notes data. Do not restore old databases over later user work. Disable Text ingestion in configuration if reverting its adapter. Pending Text outbox rows must remain held by the Text-disabled notifier gate; if restoring older notifier code without that gate, hold those rows privately before restarting it. Never delete unrelated Knowledge resources as a code rollback.

## Nightly loader integration

The monitor imports the ingestion script by file path, so it must resolve its trusted co-located helpers independently of cwd/PYTHONPATH. This release fixes that import path and tests the deployed flat-helper layout under isolated Python. Temporary notes-upload folders are excluded from document scans. The previously failed scheduled run can be retried through the existing monitored service after a read-only verification; the timer schedule is unchanged.

## Verification boundary

Offline synthetic checks cover exact original/revision text, owner/CSRF boundaries, submit idempotency, stale writes, immutable/tamper refusal, separate approval, read-only history, approved-only ingestion, replacement/resume and post-commit notification deduplication/reconciliation. Fake Knowledge and Telegram transports prevent live writes/messages. Browser rehearsal uses fixture identity/content and verifies card preview, inert HTML/images, save, edit/reapprove and historical read-only preview. Actual owner browser access and the first real approved nightly Text ingestion remain separate live checks; do not seed production Knowledge with synthetic test text.
