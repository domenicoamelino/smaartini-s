# SMARTINI’s Notes 0.3.0 — adoption review

This source reflects the owner-only Notes pilot deployed on 30 October 2026, including the shared recap dashboard and adapter hotfix 1. The final package passed 339 checks and live owner browser review confirmed access. Meeting processing workflow 2.7.1 remains the accepted baseline. No new permanent service, model download, automatic approval, cloud inference or handwriting-model training is required or introduced. The activation and rollback instructions below apply to future installations or redeployments; the current pilot has already been activated with user authorization.

## What the candidate adds

The existing recap dashboard lists audio and handwritten Notes together, with source filters and a Notes review view at the same dashboard address. Legacy Notes links redirect to that view. See SHARED-RECAP-DASHBOARD.md.

A dedicated, manually importable Open WebUI Function embeds an upload card in the same style as audio. The card accepts a title, a required notes date and 1–10 ordered JPEG/PNG pictures (12 MiB / 20 MP each, 48 MiB total). Confirm and process uploads the pictures sequentially and commits one durable notes-set job. The backend preserves every original byte/hash, creates separate oriented inference images, and analyses one picture at a time through the shared heavy slot. Text, lists, crossouts, drawings and arrow relationships are editable. Review flags guide attention; region-by-region confirmation is unnecessary. An optional page confirmation can remember clear, explicitly reviewed wording corrections privately. These become bounded vocabulary hints; they do not alter model weights. Forget stops their future use.

With NOTES_TWO_STAGE=1, extraction stops for explicit source approval. That approval queues a final text-and-diagram result; a separate final approval is required before Knowledge ingestion. See NOTES-TWO-STAGE.md. Legacy single-stage behaviour remains for older/test configurations only. The dashboard link appears in the card and chat when that draft is ready; failures expose a recovery link. Existing InfoRag owner bindings receive one recap-ready outbox notice, rather than a notice per picture or an intermediate extraction notice. The legacy dashboard single-page uploader retains its prior clear-page draft rule. Recap items contain exact source IDs/quotes. The user can save a manual recap after generation failure and enter a manual transcription after failed extraction. Saving never approves. Approval requires the exact saved revision and a separate acknowledgement of source review. An earlier approved snapshot stays eligible until a replacement is explicitly approved. Hash checks refuse changed originals or approved files.

Notes tasks/revisions/approvals/corrections/audit events are stored in new notes_* tables in the existing reviews.sqlite3. Original images, inference derivatives, stage logs/partial output and immutable approved exports live in notes-<uuid>/ directories inside the existing archive root. Durable upload sessions and staged originals live in notes_upload_sessions and notes-upload-<id>/; include both in private backups. Do not move or reinterpret existing meeting rows/directories.

## Shared resources and isolation

With Notes enabled, the existing worker chooses the oldest ready audio, meeting recap or Notes stage. One heavy slot is shared across all these tasks and the opt-in ingestion wrapper; process-safe locking closes the check/start race. Human review releases the slot. Low available memory leaves tasks queued. Recent/active Notes tasks participate in busy checks only when the shared feature is enabled, so disabling Notes does not leave legacy ingestion permanently blocked by held Notes jobs.

Uploads have a 12 MiB / 20 MP per-picture and 48 MiB set limit, a per-owner queued limit of ten, a global Notes queued limit of one hundred and a disk reserve. Only the active stage loads a model. Ordinary WebUI chats and direct Ollama calls remain outside this dispatcher; memory admission is a safeguard, not complete host-wide scheduling.

WebUI verifies the cookie identity. Notes reuses the existing signed owner/cookie/origin-bound CSRF helper; browser session setup also matches the requested origin to the host. Owner IDs from upload headers/bodies are ignored. The card uses an unguessable, session-scoped bearer URL (upload window 30 minutes; committed progress at most 24 hours) with no cookies, matching the audio iframe pattern. Its capability cannot approve, fetch originals or read revisions. Backend Function calls require the existing worker key plus authenticated owner ID. Dashboard originals/revisions still require the real WebUI cookie and CSRF controls. The browser receives no worker key. A pilot allowlist can restrict Notes to one existing account. Existing Telegram credentials and owner/chat bindings are reused; Notes notices are held when Notes is disabled, and ambiguous delivery policy remains unchanged.

Notes ingestion is opt-in, filters one configured owner, requires a matching collection owner/write access and refuses any sharing grants. It reuses the existing restricted API key; account-profile permission is not requested or required. The service credential remains trusted like the existing ingester; the privacy boundary is the approved source owner and unshared destination. A separate notes_only owner profile is supported. It reuses the existing content-hash upload/replacement ledger and does not delete unrelated/global files. The 03:00 Europe/Amsterdam timer is unchanged. A deferred run retains exit 75 semantics; it does not imply an added automatic catch-up schedule.

## Models and quality boundary

The provisional extractor is the already-installed qwen3.5:4b; the text recap default is the already-installed gemma4:12b-it-q4_K_M. Configuration can pin both artifact digests. There is no cloud fallback. Bounded context/output, stop reason checks, retained partial text and strict structural/evidence validation refuse incomplete output. Large notes sets use cached bounded recap parts followed by evidence-checked consolidation. If a single block or combined candidate set exceeds the safe bound, the job fails visibly and retains source/partials for review rather than silently discarding pages. This does not establish factual accuracy or calibrated confidence.

Current review flags combine model uncertainty with independent number/identifier, negation, selected name-pattern and exclusion checks. No numerical doubt threshold has been calibrated. Image region geometry and drawing interpretation remain estimates. The first real typed-adapter smoke test produced eight regions and a four-item unapproved recap; it does not certify EN/NL/IT quality or later reviewed references. Correction-memory benefit on unseen pages and actual handwriting fine-tuning remain unproven.

## Before any live deployment

1. Review the package manifest and diff. Existing processing changes are narrowly limited to gated dispatcher/routes/health, Notes notification routing, and typed ingestion/gating. ASR, meeting recap models, source/review algorithms and timer schedule remain unchanged.
2. Verify live source hashes, idle audio/review queues, collection privacy/owner/write access and current service definitions. The deployed ingestion file differs from the checkout; reconcile that diff before copying it. Do not blindly overwrite the deployed ingestion file.

   Development reconciliation found only the already documented Windows-specific atomic-replace retry in the checkout; no server-only ingestion fix would be lost. Recheck hashes before activation in case source changes later.
3. Create a private backup of worker/ingestion/monitor source and configuration, relevant unit/drop-in definitions and coherent SQLite snapshots. Include all notes-* directories and existing immutable meeting directories in routine backup coverage. Preserve current Knowledge ledger and collection membership. Keep secrets/images/correction memories out of Git.
4. Verify the rollback copy is readable. A code rollback must not restore an old database over newer meeting/Notes work. Off-device restore acceptance remains an independent operational gate, not something this feature certifies.
5. Prepare Pillow 13.0.0 in a copied/test environment first. It is the only added worker dependency. No Pillow package was installed into the live meeting environment during development. Do not upgrade the accepted ASR dependencies. If approved, install only the reviewed Pillow wheel with no dependency upgrades after recording the existing environment; preserve its absence/version for rollback.
6. Confirm the owner accepts extraction/correction effort on real references. The reference drafts are not fully owner-certified and no final cross-language winner is claimed.

## Activation plan — only after approval

Merge the reviewed payload into the existing paths. Do not run the older meeting deployment scripts for this Notes candidate. Do not overwrite secrets or runtime folders. Copy Notes helper copies into ingestion as included in the payload; their hashes must match the worker copies. Keep the existing proxy prefix; no new external port is required.

Append only the new settings to the private worker environment, preserving all current ASR/report settings:

```text
SMARTINIS_NOTES_ENABLED=1
NOTES_PUBLIC_ORIGIN=<existing HTTPS Open WebUI public origin, without a path>
NOTES_TWO_STAGE=1
NOTES_ALLOWED_OWNERS=<existing Open WebUI owner ID>
NOTES_MODEL=qwen3.5:4b
NOTES_RECAP_MODEL=gemma4:12b-it-q4_K_M
NOTES_CONTEXT=16384
NOTES_OUTPUT_TOKENS=4096
NOTES_MIN_AVAILABLE_MB=8192
```

Optionally set NOTES_MODEL_DIGEST and NOTES_RECAP_MODEL_DIGEST to the exact reviewed installed artifacts. These settings are validated at startup; model digest/capability checks occur before inference. No model pull occurs.

Enable the same shared-resource flag in an additive user-service drop-in for meeting-ingestion.service, preserving the existing monitor ExecStart/ExecStopPost override. Do not replace the unit or its timer. Add include_notes=true and notes_owner_id to the private ingestion configuration only after verifying the owner/private destination. Keep base_url, collection_id, existing root, API key and ledger. For another owner, use a separate private collection/config/ledger with notes_only=true; do not reuse another owner's destination state.

Restart only the idle worker after backup; re-read health, confirming meeting workflow/dashboard 2.7.1 plus Notes version 0.3.0. Import openwebui_notes_pipe.py as a new owner-restricted Function and copy WORKER_URL, WORKER_API_KEY and PUBLIC_ORIGIN from the existing audio Function valves; set its user recap language as desired. The Function file alone cannot install its backend. Do not share the worker key in chat or include it in exported files. Do not replace the meeting Function. Verify actual signed-in browser identity/CSRF and private-source access through the existing HTTPS proxy. Start with one owner and an unapproved two-picture notes set. Check title/date, ordering, a combined evidence-linked recap, no early dashboard completion link, and one InfoRag completion notification.

Importing into the real Open WebUI runtime and delivery through the real InfoRag bot remain live adoption checks; offline tests do not certify them.

Explicitly test audio/image overlap, interruption/retry, a changed/reapproved Notes replacement, two-owner refusal and Telegram link/deduplication. Observe the existing scheduled 03:00 ingestion. The offline Knowledge tests use a fake client; they are not a live indexed replacement certificate.

## Rollback

Disable the new Function and Notes flag/allowlist routing; retain Notes directories and notes_* tables. Restore reviewed prior code/configuration and only the additive service settings after queues are idle. Notes pending notices must be held rather than sent by older notification code: retaining the gated notifier while disabled is the simplest source rollback. If restoring its exact older source, privately hold pending note-* outbox rows first, preserving them for an explicit future resume. Leave meeting notices alone.

Disabling Notes leaves its queued data intact; do not delete it or drop tables. Existing meeting processing and the original timer continue. Do not restore a stale reviews.sqlite3, jobs.sqlite3 or Knowledge ledger as routine code rollback. Any Knowledge rollback must use the managed snapshot/replacement policy; never delete unrelated resources. Stop the temporary rehearsal separately; it is not a production service.

## Checks and packaging

```text
python tools/check_notes.py
python tools/check_all.py
python tools/build_notes_release.py --output <fresh private directory outside the checkout>
```

The Notes suite requires Pillow and uses synthetic fixtures, mocked model responses, a local HTTP fixture and a fake Knowledge client. No live Telegram message, Knowledge write or approval occurs in these tests. The browser rehearsal uses fixture identity and a supplied reference, clearly labelled; it does not prove real WebUI login or real model accuracy. Source-only packaging excludes private runtime state, images, reference sets, raw results, caches, secrets and model weights.
