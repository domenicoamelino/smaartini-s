> **28 October 2026 update:** the deployed workflow is now frozen Turbo → transcript review → Gemma 12B → recap confirmation → nightly ingestion. Start with [Usage flow](USAGE-FLOW.md), [Usage cheat sheet](USAGE-CHEATSHEET.md) and [2.7.0 implementation/deployment](REVIEW-FLOW-2.7.0.md). Earlier version-specific instructions below are historical where they conflict with those guides.

# Using the meeting review system

Updated 25 October 2026; dashboard 0.1.1 / Open WebUI Function 0.4.0.
The owner has confirmed the chat and dashboard approval flow works on MINISFORUM.

## Normal daily workflow

1. In the existing meeting Function chat, request a new recording card. Enter the
   title, actual meeting date, optional participants and expected EN/NL/IT languages.
   A blank speaker count means automatic estimation; a supplied count means total
   speakers, including you. Names do not automatically identify voices.
2. Upload the audio and wait for processing. Closing chat after upload acceptance
   does not cancel the queued job. Retrieve with `status JOB_ID` if needed.
3. The recap returns in chat; configured Telegram completion notification includes
   a meeting link. Send `dashboard` to open your meeting list at any time.
4. Use the same signed-in Open WebUI account and HTTPS address. Open the meeting,
   inspect recap/transcript, then Edit recap. Correct wording/details and map speaker
   clusters only when you know who spoke. Mapping alone does not rewrite recap prose.
5. Save and close writes a new draft on the server. Reopen to check it. Saving
   does not approve it and retains any previously approved immutable version.
6. Choose Approve for knowledge base and confirm the displayed exact revision.
   Refresh if the revision changed elsewhere. Unsaved edits cannot be approved.
7. Approved means eligible for ingestion, not already indexed. The list distinguishes
   current, approved and indexed versions. The overnight job publishes approved
   snapshots; confirm its outcome before assuming the knowledge base changed.

An unused upload request marked expired means its upload window elapsed without
a file; it does not mean a completed meeting or saved recap expired.

## Editing an already indexed recap

Edit/save creates a draft while the previous approval/index remains available.
Explicitly approve the new revision when ready. Successful ingestion replaces the
previous indexed document; retaining approval history is intentional. This live
replacement lifecycle still needs its final acceptance check after the night run.
Do not edit archived files directly to bypass approval/hash checks.

## Troubleshooting and scope

- Dashboard approval now uses the browser's public origin rather than the proxy's
  rewritten worker Host. After installing 0.1.1, refresh the page to load new assets.
- If approval fails, read the message in its confirmation dialog. Reopen through
  the same Open WebUI origin and account; never supply the worker key to a browser.
- Transcript/individual-turn corrections and AI-assisted feedback use the chat
  commands below. The dashboard transcript is currently read-only.
- AI feedback runs in the background; wait for the new revision before approving.
- Voice labels are estimates, not verified personal identity. Check the original
  recording when attribution matters. Known ASR/recap quality limits remain open.

## Commands inside the existing SMARTINI’s Open WebUI chat

Replace JOB_ID and REVISION with the values shown above the current draft. Do not type the placeholders literally.

View the current draft and review state:

```text
review JOB_ID
```

View the speaker-labelled transcript, including turn IDs such as S000012:

```text
transcript JOB_ID
```

Give natural-language feedback and request a background revision:

```text
feedback JOB_ID REVISION
There is no role documentation. Keep the negation. “Until 27” refers to age, not 2027. Do not combine the two people's biographies.
```

Provide your complete edited recap directly (no model call for saving it):

```text
replace JOB_ID REVISION
Paste your complete reviewed recap here.
```

Confirm voice names for this meeting, after checking the transcript/audio:

```text
speakers JOB_ID REVISION
SPEAKER_00 = Confirmed name for this voice
SPEAKER_01 = Confirmed name for this voice
```

Correct the speaker of one specific displayed turn, without renaming the whole cluster:

```text
speaker JOB_ID REVISION S000012 = Confirmed name
```

Correct misheard words in a displayed turn:

```text
correct JOB_ID REVISION S000012
Paste the corrected wording of this turn here.
```

Voice/word corrections queue a new recap revision. Original audio and ASR are retained; corrected wording has no invented word timestamps.

Correct displayed meeting details (each saves a new draft revision):

```text
date JOB_ID REVISION YYYY-MM-DD
```

```text
title JOB_ID REVISION
Correct meeting title
```

```text
participants JOB_ID REVISION
Confirmed participant name, Another confirmed participant name
```

See recap differences:

```text
changes JOB_ID
```

If a background revision failed, retry its saved feedback/corrections:

```text
retry JOB_ID REVISION
```

When the current displayed revision is satisfactory, explicitly approve exactly that revision:

```text
approve JOB_ID REVISION
```

Ordinary “okay” messages, model-written approval statements and quoted commands do not approve anything. Any newer revision needs fresh approval. The last approved immutable version stays in the knowledge workflow until its approved replacement is ready.
