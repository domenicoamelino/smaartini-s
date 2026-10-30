# Notes 0.3.0 — source approval, then final approval

## User flow

1. Upload title/date and ordered pictures through SMARTINI’s Notes. Extraction stops at source review.
2. Correct the transcription, drawing descriptions, exclusions and arrow endpoints. Click **Approve source & generate recap and diagrams**. This records an explicit source fingerprint and queues generation; it does not create Knowledge approval.
3. Review the generated readable text and locally rendered SVG diagrams at the top of the same dashboard view. Expand **Edit final text** to change wording. Edit each diagram's textual description, or replace its image with JPEG/PNG (12 MiB / 20 MP limit). Save the final result. Replacement uploads create new immutable revisions; original bytes and a sanitized PNG are retained.
4. Check that the final text and every diagram have been reviewed, then click **Approve final result for Knowledge**. Only this second approval makes the exact saved revision eligible for the existing 03:00 Europe/Amsterdam ingestion. Later edits/replacements require another final approval. Previously approved snapshots remain eligible until a replacement is approved.

## Diagrams and Knowledge

Diagrams are deterministic, inert SVG graphs of approved source regions and explicit source relationships. No new image model, cloud dependency, CDN or service is required. Text is XML escaped; uncertain relationships use dashed connectors. No missing relationship is invented. Pages without drawing regions or relationships produce no diagram. These are clean source graphs, not an artistic reconstruction of a sketch or a guarantee of semantic accuracy. Large graphs above 60 regions fail visibly for review rather than truncate.

The final text and approved diagram descriptions enter Knowledge as plain text. Images remain content-addressed, hash-checked assets in the private Notes directory and approved revision payload. Image upload/embedding into Open WebUI Knowledge is deliberately deferred. No claim of visual RAG is made.

## Compatibility and operation

Set `NOTES_TWO_STAGE=1` on the existing worker, retaining the current owner/public-origin/model settings. Runtime helpers include `notes_presentation.py`; ingestion needs its matching copy. No changes to meeting transcription/recap processing or the timer are required. Existing approved Notes snapshots remain readable. Existing unapproved drafts need source approval before this new final generation/approval flow; they are not silently migrated or approved.

The importable Function is now 0.3.0; it returns at the source-review checkpoint and describes the two approvals. Existing 0.2.0 cards can still open the dashboard at source readiness, but their chat waiter may continue until the final result; update the Function body manually for the clearer chat behaviour. Keep the same three valve values. Nothing in the backend imports or overwrites the user's stored Function automatically.

Final generation uses the existing local Gemma recap adapter under the same durable heavy queue and memory gate; SVG layout adds no model load. All generated assets and user replacements stay inside the existing private archive/backup coverage. Source changes invalidate the source approval and final result. Final source/evidence/asset hash checks also run during ingestion. Model partial output, source revisions and prior approvals remain preserved.

For rollback, restore the backed-up code/config after queues are idle, retain all data/tables/assets, and hold Notes ingestion if reverting to a runtime that cannot validate the final presentation. Never restore old databases over later work. A worker restart with administrator access loads the new modules and setting.

## Validation

91 Notes/shared/two-stage checks plus the 259 existing regressions pass. Added checks cover two separate approvals, no automatic recap before source approval, final text/description saves, replacement-image revisions, owner-only image reads, source invalidation, stale revision refusal, SVG injection escaping, uncertain arrows, text-only sources, tamper refusal and approved-only text export. Real isolated HTTP routes exercise the full approval/upload sequence.

The loopback-only browser rehearsal used synthetic identity, text and model responses, with no real Telegram or Knowledge calls. It verified source approval, queued generation, final text/diagram preview, edit/save, refusal of unacknowledged final approval, and explicit final approval. No real user source or final result was approved by the agent. Model quality and true visual understanding still require review; this change adds no new quality benchmark.
