# Learnings and decision log — 25 October 2026

## What the experiment has established

- The durable local workflow connects Open WebUI upload, archived audio, timestamped
  transcription, CPU diarization, report generation, Telegram completion, review,
  immutable approval and a meeting dashboard. The owner validated the review and
  dashboard approval flow. Scheduled Knowledge ingestion remains the next live gate.
- A 400.94-second two-speaker benchmark on the Ryzen 7 8745H used four threads and
  took about 276 seconds per diarization run: real-time factor about 0.688,
  approximately 41 minutes of inference per audio hour by linear extrapolation.
  Peak whole-process RSS was about 2,491 MiB. This is one sample, not a service SLA.
  Supplying num_speakers=2 did not materially accelerate that sample.
- The isolated diarization environment successfully loaded community-1 on CPU.
  Keep it separate from the working transcription environment. Successful imports
  do not prove every package combination is generally supported.
- Hugging Face gated-model access requires both appropriate token permissions and
  acceptance of the model conditions by the token's account; a token alone was
  insufficient. Never store tokens in shared logs or source.
- Multiple expected languages are metadata/hints, not a strict ASR whitelist.
  Transcription preserves spoken language; automatic speaker clusters do not prove
  identities, and a participant list does not establish the speaker count.

## Failures that changed the implementation

- NumPy scalar booleans/numbers can break JSON serialization even when a traceback
  describes a bool. Convert boundary data to native Python types and test the actual
  serialized output; seeing a conversion elsewhere is not proof the failing path is fixed.
- Evidence generation can fail late on unsupported dates or claims. Retained
  transcripts/diarization and report-only recovery avoided rerunning the recording.
  Repeated recap guard patches did not establish the desired quality: use a fixed
  human-reviewed evaluation set before further tuning.
- Service active status can precede a listening HTTP endpoint. Bounded health
  retries distinguish normal startup delay from a persistent failure.
- Explicit module paths and test isolation matter: installed ingestion tests once
  shadowed staged review tests. Validate the staged and installed layouts separately.
- Replacing source files does not update an Open WebUI Function stored in its
  database. Back up/export the installed Function and preserve its valves privately.
- Proxy-rewritten worker Host is not the browser's public origin. Dashboard 0.1.1
  binds approval protection to the signed browser origin while retaining owner,
  session, signature and expiry checks. Approval errors must stay visible in the dialog.

## Operational lessons

- Keep runtime folders stable. Repository layout is a source layout, not permission
  to move services or create new deployment directories.
- Show draft, approved and indexed revisions separately. A save is not approval;
  approval is not proof of remote indexing; local index provenance is not a live query.
- Old unused upload windows can expire without losing a completed recap. Do not
  confuse expired requests with active processing work.
- A user timer needs a running user manager; verify lingering for logout operation.
  The current timer does not catch up missed runs. A configured monitor wrapper is
  not proof of delivery, and weekday reports differ from completion notifications.
- Source control is not a backup of Open WebUI data, recordings, review databases,
  credentials or approved snapshots. Test a private off-device recovery separately.
- Keep known legacy test failures visible. A passing focused suite is not an
  all-green release or a quality evaluation of real meeting summaries.

## Current hardware observations

User-reported inventory: Ryzen 7 8745H, 16 logical CPUs; about 28 GiB usable RAM,
8 GiB swap; 468 GiB filesystem with about 401 GiB available at the earlier check.
After relocation the connection measured about 105 Mbps down / 50 Mbps up.
These are historical snapshots. Measure current contention, swap, model size and
archive growth before deciding on RAM/SSD expansion; verify physical compatibility.
