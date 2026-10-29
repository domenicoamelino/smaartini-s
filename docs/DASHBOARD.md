> **28 October 2026 update:** the deployed workflow is now frozen Turbo → transcript review → Gemma 12B → recap confirmation → nightly ingestion. Start with [Usage flow](USAGE-FLOW.md), [Usage cheat sheet](USAGE-CHEATSHEET.md) and [2.7.0 implementation/deployment](REVIEW-FLOW-2.7.0.md). Earlier version-specific instructions below are historical where they conflict with those guides.

> Live acceptance update, 25 October: the owner confirmed dashboard 0.1.1 works, including approval. Overnight Knowledge ingestion and replacement remain separate checks.

> Approval fix 0.1.1: binds the CSRF token to the browser's public origin, not
> the worker Host header rewritten by the proxy. Session, owner, cookie, signature
> and expiry checks remain required. Approval failures stay visible in the dialog.
> Existing Function 0.4.0 does NOT need updating again for this fix. After installing,
> refresh the dashboard page before retrying. No proxy configuration change needed.

# SMARTINI’s meeting dashboard 0.1.1

This adds a dashboard to the existing meeting worker. It does not tune or replace
transcription, diarization or recap generation. The original approved meeting and
all immutable revisions remain in place. No meeting is approved by installation.

## 1. Copy the complete update to MINISFORUM

Extract meeting-dashboard.zip so this file exists:

    ~/meeting-dashboard/install.sh

The package contains source/ with complete source files and synthetic tests.
This is a staging folder, not a new service location. Runtime remains:

    ~/ai-platform/transcription/meeting-worker-2.3/
    ~/ai-platform/ingestion/
    ~/ai-platform/diarization-benchmark/
    ~/ai-platform/ingestion-monitor/

The installer replaces only these worker-directory files:
meeting_worker.py, meeting_review.py, meeting_notifications.py,
configure_meeting_notifications.py, openwebui_meeting_pipe.py,
meeting_dashboard.py, dashboard.html, dashboard.js, dashboard.css.

Other source/ files are included for staged validation, not deployed over your
existing report, ingestion, environment or model code. Existing proxy routes and
systemd units are retained. No new Python dependencies are required.

## 2. Install while idle

Finish active recordings, candidate-generation terminals and review tasks. Avoid
new uploads or edits during deployment. Export the current Open WebUI Function
as a private backup first; its database content is separate from files on disk.

```bash
bash "$HOME/meeting-dashboard/install.sh"
```

The installer tests the staged code, pauses an already-active nightly timer,
checks for active processing/ingestion, backs up source and SQLite, stops the
worker, installs atomically per file, tests against the installed modules,
restarts and checks the loaded dashboard version. It restores the timer's prior
active state. If your timer was already paused, it stays paused.

Expected final health line:

    Healthy worker loaded dashboard 0.1.1

Backup is under the existing worker's backups/pre-dashboard-TIMESTAMP-PID.
Those private SQLite copies may contain upload capabilities; keep them out of Git.
They are not automatically restored on rollback, because that could lose later
reviews/approvals. Source rollback attempts to preserve all live data.

## 3. Update the EXISTING Open WebUI Function

As with the previous update, replacing a .py file does not update the Function
stored by Open WebUI. Open its editor, replace all code with:

```bash
cat "$HOME/ai-platform/transcription/meeting-worker-2.3/openwebui_meeting_pipe.py"
```

Save, preserve WORKER_URL/WORKER_API_KEY/PUBLIC_ORIGIN and keep the Function active.
The new Function header is version 0.4.0. Do not create a second Function just to
update this one. Export/restore instructions remain in the local AI handbook.

## 4. Open the dashboard

Sign in to the usual Open WebUI HTTPS address first. In a new chat with the meeting
Function, send exactly:

    dashboard

It returns a link to your own meetings. Review/approval and completion replies
also end with a direct meeting link. The dashboard is on the same origin:

    /meeting-ui/dashboard/

A direct link ends with # followed by the job ID, without any secret token.
Only meetings owned by the currently signed-in account are returned, including
for admin accounts. Use the SAME Open WebUI account that uploaded the recording.

If it asks you to sign in despite a recent login, open Open WebUI on the SAME
origin and sign in again so its session cookie is available. Do not paste the
worker API key into the browser. This release deliberately does not fall back
to a shared owner ID, anonymous Tailscale identity or a shared bearer capability.

## 5. Telegram links

The existing bot keeps its owner-to-chat binding. If its openwebui_url is already
set to the same HTTPS origin, new notifications now link directly to the meeting.
If it was blank, update only that URL using the exact PUBLIC_ORIGIN from the
Function Valves (replace the example with your real HTTPS address):

```bash
~/ai-platform/transcription/.venv/bin/python   ~/ai-platform/transcription/meeting-worker-2.3/configure_meeting_notifications.py   --update-url --openwebui-url 'https://YOUR-EXISTING-OPENWEBUI-HOST'
```

This backs up the old binding and preserves bot/chat/owner settings. It sends no
test message and does not resend already delivered notifications. It requires
an existing binding; ordinary notification setup still works as before.

## 6. Validate with your approved meeting

Use bb31355627f44981a5de0cef375ff53c. In Open WebUI send:

    review bb31355627f44981a5de0cef375ff53c

Follow the dashboard link. If nothing else has changed, current and approved
should both be r1. If your actual revision is higher, use what the page shows;
do not reset it just to match this example.

1. Open the recap and compare its text with Open WebUI.
2. Click Edit recap. Make a small reviewed change (for example improve the title
   or correct existing wording, rather than adding a fictional meeting fact).
3. Choose Save and close. The page returns to the meeting list.
4. Reopen. Current should advance to the next revision and approved should still
   show the previous revision. Unsaved text cannot be approved.
5. Check Revision history: the prior report remains viewable. Check Transcript
   and Details & speakers. Name mappings apply to that meeting only and do not
   automatically rewrite names in your edited recap.
6. When satisfied, choose Approve for knowledge base. Confirm the exact revision.
7. The approved number advances. Indexed does NOT advance just from approval.
8. Send review JOB_ID in Open WebUI and confirm it shows the same current state.

Live dashboard editing/approval was accepted by the owner on 25 October. Continue
with the overnight indexing and replacement checks in the current operations guide.

## Meaning of statuses

- Processing: upload/queue/transcription/report generation still active.
- Ready for review: completed recap with no approved current revision.
- Update awaiting review: new draft exists while the older approval is retained.
- Approved · awaiting ingestion: exact current revision is approved, not recorded
  as indexed yet.
- In knowledge base: a successful local ingestion record refers to that approved
  immutable revision/hash. The page is not querying the remote collection live.
- Indexing needs attention: last ingestion recorded an error for this meeting.
- Revision in progress: a background chat feedback/correction task is running;
  editing/approval waits for completion.
- Processing failed / unused upload request expired: source/state retained; no automatic
  deletion. Old waiting_upload sessions are not active processing jobs.

The list shows current, approved and indexed revision separately. An older indexed
revision remains visible while you edit a new draft. If local ingestion state is
missing, unreadable or predates approval-aware indexing, indexed stays unconfirmed;
pre-existing legacy knowledge content is not assumed absent or newly approved.

## Scope and limits

Recap editing, title/date/participants, cluster-name mappings and exact-revision
approval are supported. Transcript is displayed read-only in this dashboard;
individual transcript/turn identity corrections and AI feedback are still available
through the existing Open WebUI commands. Mapping changes do not generate another
AI report; edit the recap text yourself as needed. There is no new upload form;
use the existing Open WebUI recording card.

Markdown is edited as text. The preview safely renders headings/paragraphs and
quote blocks; it does not execute HTML or fetch images embedded in meeting text.
Meetings cannot manually mark themselves indexed or processing-complete.

Authentication is verified on every API call through the local WebUI session
endpoint; no session cache or worker secret is exposed to browser JavaScript.
The default WebUI URL is http://127.0.0.1:8080. If the existing installation differs,
set MEETING_WEBUI_URL to its loopback HTTP origin in worker.env and restart the
worker. Do not point this setting to a public or remote host. With a nonstandard
same-origin subpath, proxy/trusted-header auth or external database, deliberately
review the deployment before assuming this reference cookie flow applies.

If ingestion is elsewhere, MEETING_INGESTION_HOME selects its existing state
folder. The default is the ingestion sibling of MEETING_ROOT. This setting is
read-only dashboard configuration, not an ingestion destination change.

## Rollback

Run only while processing/review/ingestion are idle. Use the exact backup path
printed during installation, replacing BACKUP_PATH:

```bash
bash "$HOME/meeting-dashboard/rollback.sh" 'BACKUP_PATH'
```

Source is restored and the worker restarted. Review revisions, approvals, audio,
transcripts and indexing records are preserved. New helper/assets may remain
unused on disk. Restore the exported old Function separately if desired. If
needed, restore the notification URL from its private pre-dashboard JSON backup;
no bot token was modified. Never restore an old SQLite backup casually over
live reviews, because that would discard later user work.

## Validation

43 current offline tests pass: previous 31 plus dashboard auth/owner isolation,
CSRF owner/cookie/origin/expiry checks, content headers, atomic save/old approval,
stale revisions, history, invalid inputs, indexed-hash provenance, pagination,
minimal upstream credentials, notification URL preservation and Pipe links.

A real browser with synthetic local records exercised open -> edit -> Save and
close -> reopen -> explicit approve, confirming that the older approval survives
saving. dashboard-preview.png shows synthetic data, not a live MINISFORUM record.
JavaScript syntax checked with Node. The owner subsequently confirmed live deployment and dashboard approval through
the Open WebUI proxy on MINISFORUM. Overnight indexing remains to be validated.
Legacy repository suites have already documented failures; this dashboard update
does not claim those legacy fixtures or recap quality are now resolved.

Technical reference for the authentication integration:
https://github.com/open-webui/open-webui/blob/v0.12.3/backend/open_webui/routers/auths.py
The session endpoint validates the human user and reads the token session cookie.
No changes to that upstream application are bundled here.

## Installer import-path correction

This corrected package explicitly selects source/ for staged preflight and keeps
review_tests/ before older test modules in the installed ingestion folder. The
post-install pass still selects ~/ai-platform for application code, while using
this package's own test suite. All 43 tests also passed with deliberately
conflicting ingestion test modules. Dashboard and Pipe versions are unchanged.
