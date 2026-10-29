# 2.7.0 implementation, validation and recovery

The 28 October 2026 deployment uses the existing runtime directories:

| Repository | Existing server location |
| --- | --- |
| Root worker/Pipe/dashboard files | `~/ai-platform/transcription/meeting-worker-2.3/` |
| `ingestion/` | `~/ai-platform/ingestion/` |
| `monitoring/` | `~/ai-platform/ingestion-monitor/` |
| `diarization-benchmark/` | `~/ai-platform/diarization-benchmark/` |
| Runtime recordings/jobs/revisions | `~/ai-platform/meetings/` — private, outside Git |

## Components

- `meeting_worker.py`: durable upload/ASR jobs; stops at transcript review instead of automatically generating a recap.
- `meeting_asr.py`: frozen speech-preserving Turbo, pinned Hugging Face cache revision `0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf`; CPU/int8/8 threads, beam 5, multilingual automatic language, word timestamps, no VAD/prompts/hotwords, previous-text conditioning and `[0,.2,.4,.6,.8,1]` fallbacks. Completed cache hits avoid model loading and transcription.
- `meeting_flow.py`: listening flags, validated turn corrections, exclusions, meeting boundary and personally confirmed turn speakers. Original source is retained.
- `meeting_draft.py`: local `gemma4:12b-it-q4_K_M`, 32768 context, bounded full-source chunks and consolidation, model/source/prompt-aware response caches. No automatic factual guarantee or approval.
- `meeting_review.py`: immutable revisions, confirmed-transcript gating, durable recap tasks/retries, separate exact-revision approval and retained prior approved snapshots.
- `meeting_dashboard.py` and dashboard assets: authenticated owner-scoped review, CSRF-protected edits, authenticated byte-range audio playback, revision history and separate current/approved/indexed status.
- `openwebui_meeting_pipe.py` / `upload.html`: existing Open WebUI integration, automatic multilingual audio and review-first messaging. Existing stored Function valves are preserved during deployment.
- `ingestion/ingest_meetings.py`: approval-only content-hash replacement with recovery, retained uploaded resources and new/updated/total recap counts.
- `monitoring/`: existing private run-history dashboard and daily Telegram summaries, including weekends. Ambiguous notifications are retained rather than automatically duplicated.

`meeting_report.py`, `meeting_revision.py` and recovery tools remain for compatible historical report archives. They are not the new automatic recap path. Existing local narrative-reliability/recovery changes were retained when synchronizing this repository.

## Verification

From the repository root:

```bash
python tools/check_review.py
python tools/check_all.py
```

On the server, use `~/ai-platform/transcription/.venv/bin/python`. Tests use temporary synthetic meetings, fake models/APIs and no real Telegram delivery. The full check also runs historical reporter, client and recovery regressions independently to avoid fixture-name collisions.

Deployment checks on 28 October: 124 workflow and 27 monitor/Telegram tests passed. A synthetic browser exercised transcript correction, confirmation, recap generation and separate approval without JavaScript errors. A cached OpenText transcript produced a 327-word local Gemma draft in 77.6 seconds without ASR rerunning. An eight-second live Turbo upload stopped at transcript review, remained unapproved and delivered its Telegram readiness notice. A monitored ingestion run completed and delivered its summary. Both dashboards and the existing timer were healthy; deployed file hashes matched.

Those checks establish workflow behavior, not factual accuracy of every recap. Human review remains required. The short validation recording may still appear as an unapproved meeting.

Repository synchronization on 29 October: **226 offline checks passed** (149 current workflow/reporting/recovery checks, 50 client/reporter/worker/packaging regressions, 27 monitoring/Telegram checks). Historical fixtures now follow the review-first behavior and current verification schemas. The existing local recovery/narrative changes remain; path normalization in the recovery helper also handles Windows junctions consistently.

## Deploying a later source change

The current server is already updated. Do not redeploy just to use it. Build a complete deployment package from this repository rather than copying scripts without their companion files:

```bash
python tools/build_release.py
```

This writes `dist/SMARTINIS-2.7.0-review-flow/` and a ZIP, with the existing `ai-platform` deployment layout, complete files, checks and rollback scripts. `dist/` is ignored by Git. Transfer/extract that package, run its checks with the existing server Python environment, then deliberately run its `deploy.py`.

Deployment refuses active meeting/revision jobs, creates private code/config and SQLite rollback backups, preserves knowledge collection membership, updates the stored Function source while retaining valves, and restores the prior timer state. It does not change Docker volumes or approve reports. It first requests a normal service restart; where root administration is unavailable, it verifies the exact idle user-owned worker and its `Restart=on-failure` policy before allowing systemd recovery. This briefly interrupts the worker.

The deployment is tailored to the current MINISFORUM. If `monitor.json` is missing, it can restore the known private 22 October backup. That file is configuration containing password hashes and chat settings, not disposable status data.

## Private rollback

Original deployment backup:

`/home/um870-server/ai-platform/backups/review-flow-2.7.0-20261028-202405`

The release package’s rollback script restores code, worker model settings and stored Function source while retaining later user edits/approvals and knowledge state:

```bash
PY="$HOME/ai-platform/transcription/.venv/bin/python"
"$PY" rollback.py /home/um870-server/ai-platform/backups/review-flow-2.7.0-20261028-202405
```

Run from the extracted release directory so `deploy.py` is beside `rollback.py`. Database backups require explicit recovery; never restore them over newer review work as a routine code rollback. Keep all private backups/configuration off Git. No server restart, deployment, commit or push is needed merely to publish this repository update.

Repository-only portability fix: ingestion state replacement retries transient Windows file locks with a bounded delay. It reuses the same staged file and never repeats remote API operations. Persistent failures retain the prior state. Linux behavior and the running deployment are unchanged.
