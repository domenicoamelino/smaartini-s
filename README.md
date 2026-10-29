# SMARTINI’s

![SMARTINI’s logo](assets/brand/smartinis-logo.png)

*Turn recordings into reviewed notes. Turn reviewed notes into knowledge.*

SMARTINI’s connects Open WebUI, local multilingual transcription, local meeting recaps and explicitly approved meeting knowledge. The current workflow is deployed on MINISFORUM and runs locally.

**Current deployment: 2.7.0 · 28 October 2026**

**Upload → frozen Turbo transcript → human transcript review → Gemma 12B recap → human recap approval → nightly Open WebUI knowledge update.**

## Start here

- [Usage cheat sheet](docs/USAGE-CHEATSHEET.md) — daily actions on one page.
- [Complete usage flow](docs/USAGE-FLOW.md) — upload, listen, correct, confirm, recap, approve and update indexed reports.
- [Operations cheat sheet](docs/OPERATIONS-CHEATSHEET.md) — existing service shutdown/restart and nightly checks.
- [Implementation, tests, deployment and rollback](docs/REVIEW-FLOW-2.7.0.md).

The meeting dashboard is available at `/meeting-ui/dashboard/` on your existing Open WebUI address and uses your Open WebUI login. Telegram links directly to ready meetings. The separate ingestion-history dashboard retains its private password.

## What is installed

- Frozen speech-preserving Turbo transcription: automatic audio languages, including EN/NL/IT switching; no language-selection controls or VAD. Recap language is a separate preference.
- Review dashboard: audio playback and seeking, uncertainty flags, editable turns, personal speaker confirmation, exclusions, actual meeting-end cutoff and revision history.
- Local `gemma4:12b-it-q4_K_M` recaps from the confirmed transcript, with full-source chunk coverage and cached requests.
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
