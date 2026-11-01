# SMARTINI’s

![SMARTINI’s logo](assets/brand/smartinis-logo.png)

*Turn recordings into reviewed notes. Turn reviewed notes into knowledge.*

SMARTINI’s connects Open WebUI, local multilingual transcription, local meeting recaps and explicitly approved meeting knowledge. The current workflow is deployed on MINISFORUM and runs locally.

**Current deployment: meeting workflow 2.7.1 + owner-only Notes 0.3.0 + shared recap dashboard · 30 October 2026**

**Upload → frozen Turbo transcript → human transcript review → Gemma 12B recap → human recap approval → nightly Open WebUI knowledge update.**

## Start here

- [Usage cheat sheet](docs/USAGE-CHEATSHEET.md) — daily actions on one page.
- [Complete usage flow](docs/USAGE-FLOW.md) — upload, listen, correct, confirm, recap, approve and update indexed reports.
- [Operations cheat sheet](docs/OPERATIONS-CHEATSHEET.md) — existing service shutdown/restart and nightly checks.
- [Implementation, tests, deployment and rollback](docs/REVIEW-FLOW-2.7.0.md).
- [Readable transcript, failure reasons and manual recovery](docs/REVIEW-RECOVERY-2.7.1.md).

The meeting dashboard is available at `/meeting-ui/dashboard/` on your existing Open WebUI address and uses your Open WebUI login. Telegram links directly to ready meetings. The separate ingestion-history dashboard retains its private password.

## What is installed

- Frozen speech-preserving Turbo transcription: automatic audio languages, including EN/NL/IT switching; no language-selection controls or VAD. Recap language is a separate preference.
- Review dashboard: one continuous timestamped document, transcript downloads, audio playback and seeking, uncertainty flags, editable paragraphs, personal speaker confirmation, exclusions, actual meeting-end cutoff and revision history.
- Local `gemma4:12b-it-q4_K_M` recaps from the confirmed transcript, with full-source chunk coverage and cached requests.
- Generation failure reasons, response metrics and downloadable logs; preserved partial output, a recovered-draft editor and manual recap import. Bounded compact-output retries reuse completed stages.
- Separate transcript confirmation and recap approval. A saved draft never becomes knowledge automatically.
- Existing durable jobs, immutable review snapshots, owner isolation, CSRF protection, approval hashes and recovery behavior.
- Daily **03:00 Europe/Amsterdam** incremental ingestion. New approved revisions replace earlier indexed versions after verification. Unchanged reports reuse their indexed content.
- Telegram readiness notifications and nightly new/updated/total recap summaries, including weekends.
- Original sources, caches, prior approved snapshots and private rollback backups retained outside this repository.

Recognition flags and model instructions cannot establish perfect accuracy. Review names, numbers, conditions, decisions and owners; confirm only what the source supports. Cloud inference is not introduced. Telegram receives the requested status notifications and meeting titles.

## Source layout

Root Python/Pipe/dashboard files deploy to the existing `~/ai-platform/transcription/meeting-worker-2.3/`. `ingestion/` maps to `~/ai-platform/ingestion/`, and `monitoring/` maps to `~/ai-platform/ingestion-monitor/`. Runtime meetings and secrets stay outside Git. See [the implementation guide](docs/REVIEW-FLOW-2.7.0.md) for exact mappings.

## Test and package

```bash
python tools/check_review.py
python tools/check_all.py
python tools/build_release.py
```

Tests use synthetic data and mocked models/services. Building writes a complete deployment package under ignored `dist/`; it does not deploy, restart services, approve reports, commit or push. The current server is already updated.

## Repository and history

The repository remote is [domenicoamelino/smaartini-s](https://github.com/domenicoamelino/smaartini-s). The local folder is still named `aartins` for compatibility. Earlier AARTINS/SMARTINI’s checkpoints remain documented in [the historical README](docs/HISTORICAL-README-2026-10-25.md) and other dated notes; current guides above supersede their old model/language/workflow instructions.

MIT licensed. Keep audio, transcripts, real reports, private backups, API keys, bot tokens and dashboard configuration out of source control. You can review and push this update yourself; no commit or push is performed by the update process.

## Handwritten Notes and shared recap dashboard — deployed 30 October 2026

Notes 0.2.0 is active for the configured owner alongside the frozen 2.7.1 meeting processing workflow. The existing dashboard lists audio and handwritten Notes together, with source labels and filters. Its Notes review view is at the same dashboard address; existing Function and Telegram Notes links remain compatible.

The dedicated Notes Function accepts a title, date and 1–10 ordered pictures, with explicit confirmation before processing. Extraction runs sequentially through the shared durable queue, using installed local Qwen 4B provisionally and local Gemma 12B for a combined draft. Original images, drawing descriptions, uncertainties, revisions and audit trails are retained. Saving, source review and exact-revision approval remain distinct; only approved snapshots are eligible for the existing 03:00 Europe/Amsterdam Knowledge update. InfoRag uses the existing owner/chat binding.

Notes model hotfix 1 handles empty drawing descriptions with one bounded structural retry and repairs only unique whitespace-only evidence quote differences back to the exact source. The explicit NOTES_PUBLIC_ORIGIN setting supports the existing HTTPS proxy without trusting arbitrary forwarded host headers or weakening owner/CSRF checks.

The complete package passed **80 Notes/shared-dashboard checks plus 259 existing regressions (339 total)**. Live signed-in browser verification showed four audio entries and the recovered four-picture Notes job in the same library; its eleven-item revision 2 remained unapproved. No new Knowledge write, approval or ingestion-timer change was performed for the UI verification. Later approval/indexing state must be checked live.

See [shared dashboard](docs/SHARED-RECAP-DASHBOARD.md), [adoption/rollback](docs/NOTES-ADOPTION.md), [Function import](docs/NOTES-FUNCTION-IMPORT.md) and [adapter hotfix](docs/NOTES-HOTFIX-1.md). Private images, credentials, databases, caches and model weights remain outside Git.

## Notes two-stage final review — 30 October 2026

Approve the reviewed source to generate the final textual recap and clean local SVG diagrams. Edit final text/descriptions or replace an image by JPEG/PNG upload, then separately approve the saved final result for Knowledge. New uploads stop at source review. Images remain private revision assets; only final text and diagram descriptions enter Knowledge. Existing audio processing remains 2.7.1. All 350 package checks passed. See [two-stage operation](docs/NOTES-TWO-STAGE.md).

## SMARTINI’s Text 0.1.0

A new dedicated Function/card stores title, date and Markdown exactly as submitted, without model calls or AI rewriting. Text entries share the Audio/Notes dashboard, safe preview/editor, immutable revisions, owner/CSRF checks and separate approval. Approved text joins the existing 03:00 Europe/Amsterdam ingestion; InfoRag sends a per-Text success notice after verified ingestion and ledger commitment. Draft save and approval do not send an ingestion-success notice.

The monitor-style helper import path is repaired, and temporary picture-upload folders are excluded from ingestion. The previously missed approved Notes/Epic items were successfully caught up through the normal monitored service. The final package passed 32 Text tests plus 350 Notes/meeting checks, 382 total. No new model, dependency or permanent service was introduced. See [Text setup and rollback](docs/TEXT-ADOPTION.md). Import openwebui_text_pipe.py as a new Function with the same three existing valves; stored Open WebUI Functions are not automatically replaced by local files.

## Knowledge removal

The shared dashboard includes a red **Remove from Knowledge** button next to Open for saved Audio, Notes and Text. Confirmed requests are processed by the existing nightly ingestion; sources stay available, and withdrawal persists until explicit restoration. See [Knowledge removal](docs/KNOWLEDGE-REMOVAL.md). Run `python tools/check_knowledge.py` for synthetic lifecycle checks.

## Traffic Control

Open Traffic Control in the shared dashboard to monitor Audio/Notes queues and cancel waiting work. Running jobs are monitoring-only; cancelled work stays stopped with source data retained. See [Traffic Control](docs/TRAFFIC-CONTROL.md).

## Recovery drill

A private off-device archive/state restore passed on 31 October 2026, including Audio, Notes, approved Text, withdrawal settings and ledger references. See [Recovery drill and its scope](docs/RECOVERY-DRILL.md). This does not certify an Open WebUI volume/full-platform rebuild.

## Product roadmap

Explore the [interactive roadmap](roadmap/index.html). For local preview, editable data and manually gated GitHub Pages/CI setup, see [Roadmap guide](docs/ROADMAP.md). The roadmap shows proposed order without dates or durations; later horizons remain TBD.

## CI/CD

[SMARTINI CI and manual Pages delivery](docs/CI-CD.md) provide repository-wide lint, synthetic tests, security/secrets scans and source/static builds. Workflows are prepared locally; activation requires an authorized push and GitHub settings setup. Server deployment remains manual.
