# MINISFORUM shutdown, restart and nightly ingestion cheatsheet

Current deployment, 28 October 2026. Run these commands on the MINISFORUM as
um870-server in Bash. This does not install or relocate anything. Use the full
MOVE-RUNBOOK.md for transport and private backups. Do not paste secrets into Git.

For everyday usage, see [the usage cheat sheet](USAGE-CHEATSHEET.md) and
[the complete workflow guide](USAGE-FLOW.md).

## Routine safe shutdown

1. Stop submitting uploads and review feedback. Let active work finish, including
   separate report/candidate terminals. Close unused upload cards.
2. Pause the timer; do not kill an ingestion already in progress:

```bash
systemctl --user disable --now meeting-ingestion.timer
systemctl --user status meeting-ingestion.service --no-pager
```

Inactive after a successful oneshot is normal. If activating/active, wait and read
its journal. Do not proceed while ingestion is running.

3. Check the tracked queues with the existing helper:

```bash
~/ai-platform/transcription/.venv/bin/python "$HOME/ai-platform/move_checkpoint.py"
```

If the helper is absent, use the copy in the project's handover bundle; do not
assume missing helper means idle. Exit 2 means active work: wait. Expired unused
upload requests are not running transcription. The helper does not track separate
candidate terminals or replace the ingestion-service check.

4. When idle, stop the worker and web containers, then shut down normally:

```bash
sudo systemctl stop minisforum-meetings.service
sudo docker stop minisforum-meeting-proxy open-webui
sudo poweroff
```

Wait for full power-off before unplugging. For transport or maintenance first make
a private off-device backup, including recordings, SQLite via its backup API,
Open WebUI data/Function export and configuration. Git is not a data backup.

## Restart the existing deployment

Boot with Ethernet connected, then:

```bash
sudo systemctl start docker ollama tailscaled
sudo docker start open-webui minisforum-meeting-proxy
sudo systemctl start minisforum-meetings.service
curl --fail --retry 10 --retry-connrefused --retry-delay 2 \
  http://127.0.0.1:8765/health
sudo docker ps --format 'table {{.Names}}\t{{.Status}}'
curl --fail http://127.0.0.1:8088/meeting-proxy-health
curl --fail http://127.0.0.1:8088/api/version
curl --fail http://127.0.0.1:11434/api/tags
sudo tailscale serve status
```

Worker health should include ok=true, worker_alive=true and dashboard_version
2.7.0 and workflow_version 2.7.0. Initial connection refusal while starting is not a failure if retries
succeed. Open the usual Open WebUI HTTPS address with the same account; check an
existing meeting and dashboard. Start meeting-monitor.service with systemctl
--user if you use its separate run-history dashboard.

## Restore and inspect nightly ingestion

Preview first; this updates local last-run diagnostics but does not write Knowledge:

```bash
~/ai-platform/transcription/.venv/bin/python \
  ~/ai-platform/ingestion/ingest_meetings.py sync
```

If the plan has no errors and its approved meetings are intended, restore scheduling:

```bash
systemctl --user enable --now meeting-ingestion.timer
systemctl --user cat meeting-ingestion.timer
systemctl --user list-timers --all meeting-ingestion.timer --no-pager
loginctl show-user "$USER" -p Linger
```

For unattended operation after logout, if Linger=no:

```bash
sudo loginctl enable-linger "$USER"
```

Repository schedule: 03:00 Europe/Amsterdam; verify the installed next-run time.
Persistent=false means a missed run is not automatically caught up. A busy worker
can defer ingestion; check the outcome instead of assuming every timer firing
indexed content. Keep the PC awake and connected overnight.

The installed service has monitor.conf overriding ExecStart to run_monitor.py run
--trigger service and ExecStopPost to service-stopped. That wrapper runs ingestion
with apply enabled and records/report outcomes. Telegram reports are sent every scheduled night, including weekends
and depend on valid monitor chat/token configuration and network access. Completion
notifications use a separate configuration even if the same bot is reused.

## Next-morning checks / controlled manual run

```bash
~/ai-platform/transcription/.venv/bin/python \
  ~/ai-platform/ingestion/ingest_meetings.py status
~/ai-platform/transcription/.venv/bin/python \
  ~/ai-platform/ingestion-monitor/run_monitor.py status
journalctl --user -u meeting-ingestion.service --since today --no-pager -n 100
```

Confirm the exact approved revision/hash is committed, inspect the document in
Open WebUI Knowledge and ask a question with a verifiable source. Dashboard indexed
status reflects the local ledger, not a live remote membership check. Test later
replacement without duplicates. If a manual apply is needed, use the wrapper:

```bash
systemctl --user start meeting-ingestion.service
```

Do not clear state.json, delete lock files, recreate collections, rerun deployments
or update dependencies to conceal an error. Preserve logs and repair the specific
failure. Worker logs: sudo journalctl -u minisforum-meetings.service -n 80 --no-pager.
