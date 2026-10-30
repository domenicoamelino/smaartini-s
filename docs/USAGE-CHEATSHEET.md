# SMARTINI’s usage cheat sheet

Current workflow: **30 October 2026 · 2.7.1**. Everything is already installed on the MINISFORUM.

| What you want to do | What to do |
| --- | --- |
| Start a meeting | In Open WebUI, choose the SMARTINI’s meeting Function. Start a saved chat, enter the meeting title/date and upload audio. |
| Choose audio languages | No selection is needed. Frozen Turbo detects languages automatically, including EN/NL/IT switching. Recap language is a separate preference. |
| Review the transcript | Open **Meetings → Transcript** after Telegram says it is ready. Listen using the recording player or a turn’s timestamp. |
| Correct an error | Choose **Edit paragraph** in the continuous timestamped document and correct its text. Add an optional uncertainty note. Check names, amounts, decisions, deadlines and owners. |
| Understand highlights | Flags suggest where to listen; they are not proof of an error and cannot identify every mistake. |
| Confirm a speaker | Fill the individual turn’s speaker field only when you recognise the person. Voice clusters alone do not establish identity. |
| Remove chatter from the recap | Select **Exclude from recap**. Original audio and source text stay available. |
| Remove an unattended recording tail | Enter **Actual meeting end** as `minutes:seconds`, for example `18:30`. Check any turn crossing the boundary. |
| Save an unfinished transcript review | Select **Save transcript draft**. This does not generate or approve a recap. Save at most 500 edited paragraphs at once. |
| Generate the recap | Tick **I reviewed this transcript…**, then **Confirm transcript & generate recap**. Gemma 12B runs locally; Whisper is not rerun. |
| Review/edit the recap | Open **Recap → Edit recap**, make corrections and **Save and close**. This creates an unapproved revision. |
| Make it eligible for knowledge | Reopen the saved revision, choose **Approve for knowledge base**, then confirm the dialog. |
| Find it in knowledge | After the next successful **03:00 Europe/Amsterdam** build, check the dashboard’s **Indexed** revision and Open WebUI Knowledge. |
| Update an indexed recap | Edit it in the dashboard, save a new revision and approve that revision. The next build replaces the indexed version. |
| Download the saved transcript | Use **Download transcript** for timestamped text or **Download JSON** for detailed source. Save unsaved corrections first. |
| Recover a failed recap | Open **Generation details & recovery**, inspect the reason/log, then use or download saved partial text. Edit it, or import your own `.txt`/`.md` recap. Save and approve separately. |
| Retry a failed generation | Open Transcript and choose **Retry recap generation**. Saved corrections are retained. |

**Saving is not approval.** Transcript confirmation and recap approval are separate steps. A later transcript edit requires a new recap and its own approval. The previous approved recap remains eligible while a replacement is a draft.

**Telegram:** transcript ready, recap ready, approval confirmation, and a nightly summary of new reports, updated reports, total reports and errors. Scheduled summaries include weekends. Ambiguous deliveries are not automatically resent.

**Dashboards:** open the meeting dashboard from the Function or Telegram. It uses your Open WebUI login. The separate ingestion-history dashboard uses its existing private password. See [the full usage guide](USAGE-FLOW.md), [operations cheat sheet](OPERATIONS-CHEATSHEET.md), and [deployment/recovery notes](REVIEW-FLOW-2.7.0.md).
