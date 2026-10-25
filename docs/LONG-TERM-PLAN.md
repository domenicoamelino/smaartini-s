# Long-term vision — 25 October 2026

The goal is a local work assistant: record meetings when useful, upload them,
receive useful recaps, review and approve them, then ask dependable questions
across an evolving personal knowledge base. This plan supersedes older MVP
priorities; the numbers below are planning labels, not released versions.

## Current baseline and immediate closure

The owner has validated upload/processing, completion Telegram notifications,
chat review/approval and dashboard editing/approval on the deployed system.
Dashboard 0.1.1 fixes approval behind the existing proxy. The PC is back in NL
and connected by Ethernet. Transcript and summary quality are usable for workflow
validation but remain below the desired Plaud-style experience.

Next gate: validate the scheduled overnight ingestion, its Telegram outcome,
the exact approved content in Open WebUI Knowledge, and an evidence-backed answer.
The installed user ingestion service is wrapped by run_monitor.py and its
service-stopped hook. This proves monitor integration, not successful delivery.
Schedule/lingering and actual indexing still need their runtime checks.

## Main product roadmap

| Stage | Outcome | Work and acceptance |
|---|---|---|
| A — Close the current workflow | Trusted approval-to-knowledge lifecycle | Confirm tonight's approved snapshot is indexed; edit an indexed meeting without approval and retain the old version; reapprove and replace it without duplicates. Confirm notification and restart recovery. |
| B — Improve meeting quality | Better words, speaker boundaries and useful summaries | Establish representative reference recordings and human corrections. Compare ASR/diarization settings and recap templates, change one variable at a time, track missed words, wrong speaker attribution, omissions, unsupported claims and correction effort. No claim of reliable voice identity from a participants list. |
| C — Queue and dashboard | Submit multiple recordings and understand all pending work | Preserve the existing durable serialized worker initially. Add visible queue order/position, stage, waiting reason, failure/retry controls and review-task status. Persist order across restart; isolate owners. Accept several uploads while one processes and prove none are lost or run twice. Cancellation, priority and concurrency are explicit later design choices, not assumed features. |
| D — Second-brain retrieval | Ask useful grounded questions across meetings | Test the existing Knowledge workflow first. Build reference questions covering facts, decisions, actions, dates, people, cross-meeting changes, conflicts and unknowns. Measure retrieval coverage, citation correctness, stale/duplicate content and answer faithfulness before changing architecture. Preserve ownership and exact approved revision provenance. |
| E — Retrieval and model experiments | Improve measured weak points | Compare chunking, multilingual embeddings, metadata filters, lexical/hybrid search and reranking where supported; add a separate integration only if justified. Benchmark latency and memory locally. Compare against the same reference questions and retain a rollback baseline. |
| F — Learning from corrections | Reduce repeated editing effort | Keep versioned, consented correction examples. Evaluate prompts/templates first, then LoRA only when a sufficiently clean dataset and held-out evaluation exist. Compare recap style/action extraction and supported tool use; check factuality regressions and operational cost. |

Stages B and C can be interleaved according to daily friction; knowledge evaluation
starts early with approved real meetings rather than waiting for perfect ASR.
No additional hardware purchase or fine-tuning job is approved by this plan.

## RAG versus LoRA: experiment decision

Use retrieval as the primary mechanism for changing meeting facts, citations,
access control and revision updates. LoRA is an experiment for stable behavior
such as recap format or domain language; do not treat model weights as the
authoritative meeting database. Require measurable improvement over the simpler
baseline, an explicit private training-data policy, and no degradation on held-out
meetings. Whether training should run on the MINISFORUM is still unmeasured.

## Parallel MINISFORUM workstreams

| Workstream | First bounded experiment | Acceptance |
|---|---|---|
| Internet-assisted answers | Add an explicit web-research mode with dated sources, citations and separation from private meeting evidence. Treat fetched text as untrusted input. | Answer current-fact questions with supporting sources; explain missing/conflicting evidence. Internet access does not itself prevent hallucination. |
| Coding agents | Use a disposable repository/worktree, a suitable local model, constrained commands and tests. Start with small fixes and reviewable diffs. | Complete a real small task with passing relevant tests and human review; no automatic pushes or broad host access. |
| RAM and SSD evaluation | Measure peak RAM/swap, model loading, simultaneous services, disk growth and inference contention. Confirm exact device configuration and supported upgrades before selecting parts. | A documented bottleneck, compatible options and a benefit/cost decision; current capacity figures are observations, not proof an upgrade is needed. |

## Operating principles and decisions to revisit

- Keep existing service names and deployment directories; no refactor for its own sake.
- Local private archives remain authoritative; Git contains code and documentation.
- Explicit approval publishes an immutable snapshot; editing alone never publishes.
- Show current draft, approved revision and indexed revision separately.
- Keep useful failures and resumable intermediate results rather than rerunning audio unnecessarily.
- Decide the desired recap format, queue controls, second-brain use cases and upgrade budget before implementing those stages.
- Maintain a frozen evaluation set and record before/after results instead of repeated anecdotal tuning.
