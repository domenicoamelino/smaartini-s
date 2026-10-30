# Audio and Notes sequencing — inspected safeguards

30 October 2026. Design audit; Notes is not connected to the production queue yet.

## What is already protected

The deployed meeting_worker.py and meeting_review.py SHA-256 hashes match the inspected local checkout. The main worker runs one processing thread. HTTP requests can arrive concurrently, but audio processing and recap/revision generation execute serially on that one thread. SQLite BEGIN IMMEDIATE protects job claiming. A non-blocking worker.lock prevents a second service instance from processing the same archive.

Multiple audio requests can therefore queue without the user submitting them one at a time. Review tasks are also durable and run through that same thread. Human review happens outside the heavy processing stage and does not keep the processor busy. Interrupted audio/review work is requeued by existing recovery logic.

The existing scheduler checks queued audio before recap tasks; it is not one fair FIFO across every task type. A sustained stream of audio could postpone recap work.

The deployed ingestion busy check was inspected separately because its full file hash differs from the local ingestion file. It checks review tasks and meeting jobs, including recently opened upload sessions, and defers ingestion when those are busy. A check-before-run is not a host-wide resource lock: new work can arrive after the check. These facts do not prove race-free exclusion of ingestion and inference.

## Required Notes integration

- Keep one heavy processing slot for audio transcription, meeting recap/revision, Notes image extraction and Notes recap/revision. No model call from an upload request or a per-job thread.
- Persist uploaded sources and task metadata first; queue requests while another job is active. Load only the active task's input/model into memory.
- Select the oldest ready stage across the four task types, with deterministic tie breaking. Jobs awaiting upload or human confirmation are not ready stages. Preserve current work; do not preempt a running model call.
- Release the slot when a stage finishes or enters human review. Confirming a transcript creates a new ready recap task; it does not jump the queue.
- Expose Waiting, Processing, Needs review, Failed and Completed states. Show the active job type and that work is waiting without exposing another owner's names, filenames or contents. Any queue position is a snapshot and must be owner-safe; do not show an invented ETA.
- Preserve idempotent submissions and exact-revision task bases. A failed stage must release the slot; restart recovery must not create two claimants or publish output over newer edits.
- Add bounded upload sizes, disk/free-space checks and queue admission limits. Pending work should consume disk/metadata, not preloaded model RAM. Before loading a model, check measured headroom and leave it queued with a clear reason if memory is low.
- Extend ingestion busy checks to Notes stages. If ingestion and inference require guaranteed exclusion, use a shared cross-process resource gate respected by both paths; an advisory check alone is insufficient. Preserve the existing 03:00 Europe/Amsterdam timer.

Use the existing dispatcher and its durable task machinery with narrow type routing; do not create another independent Notes model worker.

## Scope limitation

This safeguard covers SMARTINI-managed flows. Ordinary Open WebUI chats, direct Ollama requests, command-line experiments and other applications bypass the meeting dispatcher. One SMARTINI slot does not cap every host workload. Benchmark experiments have been run sequentially and check the existing queues before starting, but they are not production queue integration. Further host-wide controls require measured contention and a separately tested runtime configuration change.

## Acceptance tests before deployment

1. Submit audio, image and recap requests concurrently from separate chats and two owners. Assert at most one heavy stage is active, every request persists and each owner sees only their own content.
2. Confirm an earlier transcript while another job runs. Verify the resulting recap queues normally and editing/review remains usable.
3. Continuously submit audio while Notes/recaps wait. Prove older ready stages are not starved.
4. Kill/restart the staged worker during extraction/generation; verify recovery, single claim and no duplicate approval/notification/indexed document.
5. Fail or time out one model stage and lower available memory. Verify subsequent work can proceed safely and no second model is loaded to bypass the queue.
6. Exercise the 03:00 ingestion trigger while each type is queued/running, including the check/start race. Verify deferral or mutual exclusion under the chosen gate policy.
7. Run full meeting regression tests after the small dispatcher changes, then verify meeting workflow version/health remains 2.7.1 and approval-only ingestion semantics remain unchanged.

No production queue, model concurrency setting, timer or meeting service was changed during this audit.
