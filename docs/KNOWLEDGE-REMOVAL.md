# Remove or restore Knowledge — 0.1.0

The shared dashboard has a red **Remove from Knowledge** button beside **Open** for each saved Audio, Notes or Text record. Confirm the named record to queue its removal. The original sources, all revisions, approvals and audit history stay available. This is not a delete-source action.

**Removal queued** means it may still appear in answers. The existing nightly ingestion at **03:00 Europe/Amsterdam**, once the processing slot is available, detaches the managed file memberships and confirms their absence. Only then does the dashboard show **Removed from Knowledge**. It never deletes global uploaded files, other collection memberships, old chat answers or backups. RAG answers already in a chat are not erased.

Withdrawal persists across saves, new processing, new approvals and restarts. The nightly run skips withdrawn sources. To add one back, open and review its approved revision, then choose **Restore to Knowledge** and confirm the currently approved revision. Restoration becomes eligible for the next scheduled ingestion. An unapproved source can be excluded in advance; approve a revision before restoration. Removal must finish before restoration is allowed. Restore does not approve an unreviewed draft.

No new service, model, dependencies, timer or credentials. The owner-authenticated dashboard API uses the existing signed CSRF protection. Stale approval revision or lifecycle generation is refused. Other owners cannot manage a record. The ingestion verifies a matching owner/private collection and detaches only file IDs already in that source's ledger; a file identity shared with another managed source is refused. Dry-run does not change requests, files or the ledger. Ambiguous removals retain their durable request and reconcile collection membership on retry. A removal received during an upload is checked again before the run finishes; requests arriving after that final check remain queued for the next run.

Storage: additive `knowledge_lifecycle` and `knowledge_events` tables in `reviews.sqlite3`. Each removal/restoration has a monotonic generation; completion is recorded only after membership verification and durable ledger save. Detached committed/pending entries move to ledger history with `withdrawn_at`; immutable sources and approvals remain untouched. A successful removal is a collection operation, not a guarantee that every retained copy of the material has been erased.

## Deployment and rollback

Back up worker and ingestion source, configuration, the ingestion ledger and archive, including coherent SQLite backups before installation. Install `knowledge_lifecycle.py` beside both worker and ingester; update `meeting_dashboard.py`, `dashboard.js`, `dashboard.css`, and `ingestion/ingest_meetings.py`. Restart the existing meetings service when idle. No Function re-import or valve changes are needed. Keep the existing timer.

Do not restore an older ingester that ignores withdrawals while any request is pending or removed: it would re-ingest the retained approvals. Either retain the lifecycle-aware ingester or stop the ingestion timer before a full code rollback and keep it stopped until withdrawal enforcement is restored. Do not restore old databases, remove lifecycle tables, automatically reattach withdrawn files, or erase sources during rollback.

Synthetic tests cover removal before/after ingestion, multiple managed revisions, pending uploads, retries after a lost response, failure retention, destination ownership, shared-file refusal, dry-run, restore, stale requests, owner isolation and CSRF. Browser rehearsal must use synthetic records in an isolated archive. Live validation must not remove or approve user material merely as a test.
