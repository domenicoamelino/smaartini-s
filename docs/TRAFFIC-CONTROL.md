# Traffic Control 0.1.0

Open Traffic Control from the shared recap dashboard. It shows your running, waiting and cancelled Audio transcription, Audio recap and Notes stage jobs. It refreshes every five seconds while visible. Queue positions account for shared work without exposing other owners’ records. Text uses no generation slot. The RAM reading and shared-slot state are observations, not promises of completion time. Audio reports its last progress update; recap/Notes stages without progress reports explicitly say that activity is not reported. No false heartbeat or stalled-job verdict is generated.

Only a waiting job has a Cancel waiting job button. Confirmation permanently stops that queued task from starting, retains its source/revisions/approvals, and records an audit event. This does not withdraw approved Knowledge or stop a model/process. There is no force-stop, automatic restart, reprioritisation, pause/resume or automatic retry. A running or completed job is refused even if the screen still showed Waiting when clicked. Repeated cancellation is idempotent. Worker claims and cancellations share SQLite write transactions.

Cancellation applies to the selected stage: cancelling Notes extraction, recap or final generation does not erase earlier results. Cancelling Audio recap clears its pending marker while retaining approved snapshots. Cancelled tasks remain excluded from existing queued-only worker selection and running-only restart recovery. Source files stay available; resubmission is an explicit new request rather than an automatic resume.

Access reuses the signed-in owner and existing origin-bound CSRF; clients cannot supply an owner or stop another owner's task. Additive traffic_events tables live in the relevant jobs.sqlite3 or reviews.sqlite3 database. Keep both in normal backups.

Install traffic_control.py, traffic.html and traffic.js with the worker; update meeting_dashboard.py, dashboard.html and notes_library.py. No model, dependency, service, timer, Function or valve changes. Activate with a restart only when processing is idle. Rollback must retain cancelled task states and audit tables; do not restore older databases or requeue cancelled work. The existing worker already selects queued work only.

Run python tools/check_traffic.py for synthetic ownership, CSRF, cancellation/claim race, restart persistence and source-preservation checks. Use a separate synthetic archive for browser testing, and do not cancel a real job as a deployment test.

The Traffic Control page is authoritative for cancellation. Existing imported chat Functions may continue polling or show an older status until refreshed; cancelling a task never turns that polling into permission to restart it.
