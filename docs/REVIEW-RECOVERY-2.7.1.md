# Readable transcript and recap recovery — 2.7.1

Deployed 30 October 2026. The owner confirmed processing, transcript/recap review, Telegram, ingestion and the general dashboard interface work. This update addresses two specific remaining pain points without changing the approval/ingestion contract.

## Transcript review

The diarized source can contain many one-word segments. The old 50-turn editor turned that into numerous pages of individual inputs. The new view groups those fragments into readable paragraphs (bounded by time/length, confirmed identities and exclusions) and renders them in one scrollable timestamped document. Paragraph text is plain data, not executable HTML. Timestamp buttons seek the original audio; editing controls appear only on demand. Global save/confirm/generate buttons remain.

Grouping is a read-only view. On the failed real meeting it reduced 2,468 fragments to 113 paragraphs, with full source coverage. A user wording replacement creates a new source-bound revision, retains the prior immutable snapshot and records original turn IDs. It does not invent word timings or assume the identity of mixed speakers.

Owner-authenticated exports provide the current saved revision as readable `.txt`/`.md` or detailed `.json`. Downloaded text marks excluded material. Save unsaved changes first to include them in the download.

## Why the reported recap failed

The first saved response completed at 463 generated tokens. The second reported `done_reason=length` at exactly 2,400 tokens, with 6,924 prompt tokens. The earlier worker discarded the exception detail from the UI and offered no manual-draft path when `recap_ready` was false, even though completed notes and raw partial response files existed.

The new owner-scoped panel exposes persisted stage events, useful failure categories, stop reasons and available token counts. It also reconstructs incomplete working text from saved successful stages and interrupted JSON responses. This text is explicitly incomplete/unreviewed; it is never automatically published. Older failures without retained exception details say so, rather than guessing a cause. Prompts, keys and private filesystem paths are not exposed by the diagnostic log.

## Bounded output pipeline

Each source chunk produces concise notes, capped by a 350-word instruction. Successful source stages remain cached. If a response is truncated or malformed JSON, the generator performs one bounded compact recovery request, capped at 250 words with an output allowance no greater than 4,800 tokens and the remaining safe context. The result is then consolidated with the other saved notes. This reduces output-limit failures; it cannot guarantee every model response will complete or be factually correct.

Streamed partial text is periodically checkpointed and saved in a `finally` block when a request ends. Retrying a task starts new numbered request/response files rather than overwriting the earlier attempt. Logs and saved outputs therefore survive retries. The completed first source stage of the real failed meeting was verified reusable before retrying its remaining stages. ASR is not rerun.

## Manual recovery

The retry was subsequently verified end-to-end on the real failed meeting: the first cached stage was reused, the second stage completed through compact recovery, the remaining source stages and final consolidation completed, and revision 3 was published as an unapproved draft. Its Telegram readiness notice was recorded as sent. All 63 pre-existing saved-source and immutable-review hashes remained unchanged. This is recovery evidence, not a claim of recap factual accuracy.

With the transcript confirmed, use **Use recovered partial draft**, download the saved working text, paste your own recap or import `.txt`/`.md`. Review it against the downloadable transcript and save it as a new draft. An unchanged placeholder cannot be promoted by a metadata-only save. An explicit edited manual recap becomes approvable even when AI generation failed; approval remains a separate exact-revision action.

Recovery text is bound to the failed task's transcript revision. It is not automatically offered for a later corrected transcript. Previous approved/ingested snapshots stay intact until a new revision is explicitly approved and ingested. Ingestion code, destination, timer and Telegram configuration were not changed by this deployment.

## Verification and rollback

Windows full suite: 257 checks passed before two additional focused stream/reason tests were added; all four focused generation/recovery tests then passed. Linux package suite: 185 checks passed. Synthetic browser exercise covered continuous scrolling, edit retention across filtering, downloads, failure logs, recovered text, manual file import and separate approval. Final packaging includes the additional tests.

The targeted deployment made a private worker/config and SQLite backup under `~/ai-platform/backups/review-usability-20261030/rollback-1793348761204654094`. All pre-existing transcript and immutable review file hashes were verified unchanged after restart. The server's `latest-rollback.txt` records this directory. Source-only package building and repository checks remain available through `tools/build_release.py` and `tools/check_all.py`; no source commit/push is performed automatically.

To deliberately roll back this targeted worker update, first finish active jobs/review generation, then run:

```bash
PY="$HOME/ai-platform/transcription/.venv/bin/python"
"$PY" "$HOME/ai-platform/backups/review-usability-20261030/rollback_review_usability.py"
```

That script restores only worker code/assets and restarts while idle. It retains current meeting databases, source, edits, approvals, knowledge and settings. The generic release `rollback.py` applies to a full deployment archive; do not point it at this differently structured targeted backup.
