# Notes Function 0.3.0

The existing Notes backend is active at 0.3.0 with two-stage review. For the clearest chat messages, replace the body of the existing Notes Function with openwebui_notes_pipe.py from this repository. Keep WORKER_URL, WORKER_API_KEY and PUBLIC_ORIGIN; do not put credentials in chat or exported source. Keep the audio Function unchanged.

Start a saved chat request, add a title/date and 1–10 ordered pictures, and confirm upload. The Function returns a source-review dashboard link after extraction. First review/correct the source, then click Approve source & generate recap and diagrams. Review the finished text/diagrams, edit text/descriptions or upload a replacement JPEG/PNG, save, and separately approve the final result for Knowledge.

Older Notes 0.2.0 Functions can still use the existing card/dashboard links, but the chat waiter may continue until final generation; updating the Function improves readiness wording and ends the waiter at source review. No backend code automatically replaces the stored Function.

Images stay with private revisions. Only final approved text and diagram descriptions join the existing nightly Knowledge ingestion. See NOTES-TWO-STAGE.md for backup, validation and rollback details.
