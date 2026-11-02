# A.3 Research 0.2 candidate — operation and rollback

This candidate was promoted from isolated staging with the user's authorization.
Production Audio 2.7.1, Notes 0.3.0, Text 0.1.0 and the existing Functions are retained.
The production worker gains additive research routes/modules and Traffic Control
integration. Approval/ingestion behavior, Telegram and proxy/appearance assets are
preserved. Private rollback backups precede promotion; the staging worker is paused.
Known date-reconciliation and tutorial-completeness limitations remain open.

## Research modes

Select SMARTINI’s Research in production Open WebUI, or the Research Function in
the test Open WebUI when its staging worker is running. Prefix a text question with
`/knowledge`, `/web`, or `/auto`, or configure its default MODE valve. `/work` is
an alias for `/web`. Research-specific starter cards explain the modes; `/help` or
a bare mode command shows the guide immediately, without starting a research job.
The cards are stored in a Research-only model metadata override, preserving the Pipe
and other model settings. Start a new chat after refreshing to see the cards.

- Knowledge-only reads approved indexed private snapshots and compares/drafts locally.
  It makes no public search or public-page request and skips public planning.
- Web-only supports general public questions: history, products, science, current
  information and tutorials. No private meeting evidence enters its public planner
  or answer. A local identifier index is used only by the privacy boundary.
- Auto/Hybrid routes locally, retrieves approved evidence when needed, produces a
  public brief, then plans public searches from that brief without meeting context.
  It combines the resulting evidence locally with separate K and W citations.

The old eight-topic catalog and automatic curated-documentation fallback are removed.
Search-provider failures or irrelevant results are explicitly reported. They are not
replaced by static source pages or by unsupported facts from model training.

## Public-query boundary

The local privacy index reads only owner-matched indexed approvals and their immutable
validated snapshots. Participant names and private project/code candidates remain
local. Public acronyms/technology names and ordinary headings are distinguished from
private identifiers; explicit participant identities are never exempted this way.
The index is bounded; inability to build it stops public research.

For a private request, the model first produces a public brief with general concepts
and publicly known technologies, omitting private names, quotes and incident details.
Only a local brief enters the general query planner; no meeting evidence is supplied
to that planning phase. An independent local review checks the proposed queries.
Deterministic checks still run regardless of that
review: normalized private names/codes, copied passages and quotations, credentials,
emails, IP literals, controls, URLs and common encoded disclosures are blocked.
Only ApprovedQuery objects can enter the public search adapter. Neither model output
nor page text can directly call it. An uncertain review or name ambiguity pauses the
job before any query is sent and releases the heavy slot. The chat displays the exact
queries in Open WebUI's native confirmation dialog and asks whether they are
public/safe to share. Confirm resumes this same job; Cancel sends nothing. If a
client does not support the callback, or no answer arrives within two minutes,
the durable in-chat question remains available. Reply with the displayed
`approve <job-id> <preview-code>` or `reject <job-id>` command. This approval is separate
from Knowledge ingestion approvals: it permits only those exact searches for that
one job. It does not change the Knowledge base or whitelist terms globally.

The owner-scoped preview is immutable and hash-bound to its queries; it expires after
one hour. Approval cannot regenerate queries, alter their wording or be replayed to
start another job. Another user cannot approve it. On resume, private evidence and
the privacy index are retrieved again locally; source withdrawal is still respected.
The user can mark plain ambiguous names public, but credentials, encoded disclosures
and copied private passages remain blocked even after approval. Rejection sends
nothing. Definite hard privacy failures may return a warned private-only answer if
usable private evidence exists, or stop with a rephrasing message.

These checks are defense in depth, not a mathematical guarantee about arbitrary
semantic disclosures. Unknown identifiers, paraphrases and entity ambiguity remain
red-team/human-review concerns. Do not claim production privacy acceptance based on
the sample tests. Conservative filters may stop legitimate ambiguous questions.

## Search and sources

The dedicated local SearXNG gateway is the sole loopback network exception, fixed to
`http://127.0.0.1:8888/search`. Engine selection is configuration, never model input.
Staging uses Brave, Yahoo and Wikipedia. Its earlier DuckDuckGo CAPTCHA/Google denial
were not bypassed. No search account, browser login or website action is used.

Search results are ranked for query relevance and primary-source provenance; duplicate
domains are bounded. General public HTTPS source discovery replaces the original host
allowlist. Administrators can optionally enable RESEARCH_RESTRICT_HOSTS and provide
an exact host list. Pages must be discovered in the current research task before read.

Every page connection validates all DNS results as public, pins the selected address
through TLS, blocks private/link-local/loopback/transition destinations and credentials,
ignores environment proxies and cookies, and permits GET only. Up to three redirects
are revalidated independently. Login/logout, delete, checkout and token-bearing URLs
are refused. Bodies, time and source counts are bounded. Scripts/styles/navigation
are excluded from extracted HTML; page text is data and is never executed.

Oversized pages can be read as bounded excerpts, with an explicit warning. Static
schema.org recipe JSON is parsed as data only so ingredients, quantities and timing
can be retained without running scripts. Answer shapes cover dates/facts, public
people and ordered instructions; recipes use one coherent source. Current-date
checks distinguish planned events from actual events and previews from stable releases.

The local model compares reliability, dates, conflicting evidence and source coverage.
It drafts structured claims constrained to available citation IDs and source types.
K means private approved Knowledge; W means public web. Interpretations are separate.
Schema checks cannot prove a citation semantically supports its claim. Publication
dates remain unverified unless separately established; retrieval dates are not proof
of publication currency. One authoritative documentation domain can be useful, but
the answer warns when independent public corroboration is limited.

## Jobs, progress and resource bounds

The worker API handles only fast durable submission/status operations. Separate
research processing holds the existing shared heavy slot; no parallel heavy inference
is introduced. RESEARCH_HEAVY_ROOT can reference the production processing lock while
MEETING_ROOT and all research data remain in the staging archive. Do not run a second
worker against the live archive. Busy audio/speaker stages and low-memory waits are
displayed explicitly, without exposing source titles or another owner's information.

The async Function polls every three seconds and replays durable stage events, so
short planning/privacy/search/reading stages are not lost between polls. It displays
waiting time, connection retries, terminal failures/timeouts and a reconnect ID.
Send `status <research-id>` to reconnect without resubmitting or repeating searches.
Stable chat/message identity prevents accidental duplicate jobs. Closing a chat does
not cancel research. Traffic Control can cancel a queued job before claim only.

- Eight outstanding jobs globally, including pending reviews; queued jobs expire after
  30 minutes. Approval starts a fresh queue-wait period without changing creation history.
- At least 8 GiB available memory before claim when Linux memory information exists.
- Three public-search requests total, including any bounded retry; up to two pages
  per query and at most six distinct pages. Unavailable engines are omitted from
  later requests in the same job. No CAPTCHA or rate-limit bypass is performed.
- Source reads at most 768 KB (larger pages produce labeled excerpts); search JSON
  at most 384 KB; no downloaded scripts/PDF execution.
- Local evidence selection at most three private records and bounded public excerpts.
- Model context 8,192; prompt byte ceiling 12,000 with excerpt reduction; output limits
  vary by stage, at most 1,200 tokens. This is a conservative input-size limit, not an
  exact tokenizer count for all languages. Oversized inputs fail rather than expanding context.
- At most one route, local abstraction, public planner, local privacy review, comparison,
  draft and conditional date/person verification call; modes skip unnecessary stages. Approved resumes skip planning and
  execute only the frozen queries. No autonomous follow-up search rounds.
- Model idle retention 30 seconds to release UM870 memory between tasks.
- Killable subprocess bounds: 25 seconds per search/page stage, 30 for private scanning,
  150 per local call within a ten-minute processing budget. Process cleanup adds a few seconds.
- Client disconnect on inference timeout must still be checked against installed Ollama
  cancellation behavior before shared-slot acceptance under timeout load.
- Restart explicitly fails interrupted research and preserves queued jobs. No automatic
  failed retry, automatic web ingestion or Knowledge edits/approvals are introduced.

Research questions, results, identifier data, test credentials and source snapshots
remain private staging data. The public-query audit records approved outgoing queries,
page URLs and safe error categories per research ID. Never publish it or debug logs
without review. The research database is covered by the existing private retention/
backup policy; source control and the downloadable candidate are not data backups.

## Verification

Run `python -m unittest discover -s research_tests -v`, existing Traffic/Knowledge
checks and `python tools/check_roadmap.py`. Tests cover general public subjects, public
technology names, direct/encoded/quoted private leakage, unsafe model verdicts, missing
privacy index, source discovery, SSRF, bounded processes, owner isolation and durable
progress/reconnect behavior. They do not establish universal semantic privacy.

Live acceptance includes historical regional release dates, current software releases,
science, public-person biographies, cooking recipes, software tutorials, the original
private-notes-plus-public-research Hybrid example and a
synthetic password/email exfiltration attempt. Verify claims against cited passages,
appropriate currentness, private/public separation, and the absence of private
identifiers/quotes from the actual outgoing audit. Measure latency/RAM and interact
with the authenticated browser during slow processing and resource waits. Repeat
Audio/Notes/Text, approval/ingestion, Telegram and appearance regressions before release.

## Deployment and rollback

No production adoption is authorized by a passing staging test. Complete privacy,
answer-quality and authenticated UI review first. Then obtain explicit user approval,
wait for existing jobs/ingestion to finish, and privately back up changed worker files,
environment, Function export and databases via SQLite backup API. Compare manifest
baseline hashes; preserve newer/uncommitted files. Deploy only reviewed files.

The staged source before this redesign is preserved in
`rollback-before-general-research/` beside the test worker. To revert staging, first
let active work finish, stop only that test worker, restore those backed-up research
modules/Function, and reconnect using the prior staging configuration. Stage-event
tables are additive; retain jobs, snapshots and results. Do not delete live data.

For a future production rollback, disable the Research Function/feature flag, restore
the private deployment backup and prior environment, then restart only the authorized
worker service. Stop only newly introduced search/test containers if required.
Retain private research data for diagnosis. Existing Knowledge approval/ingestion
databases and original proxy/branding assets must not be rolled back or overwritten.
