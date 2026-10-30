# Notes adapter hotfix 1

30 October 2026. Compatible with the existing Notes 0.2.0 Function, card, database and meeting workflow 2.7.1. Only `notes_models.py` changes at runtime; `VERSION` and future request metadata identify `0.2.0-hotfix-1`. Worker health continues to identify the Notes API as 0.2.0.

Two real-job failures were corrected:

1. A completed vision response returned thirteen drawing regions with empty descriptions. Model string fields now request a nonempty value, and the prompt explicitly requires transcribing words inside diagrams. Invalid page structure receives at most one retry in a separate audit directory. Missing descriptions are never invented. Repeated failure reports the picture number and reason. Completed earlier pictures remain cached.
2. Recap evidence reproduced wrapped source text with spaces instead of line breaks. For a quote that fails exact matching, the adapter accepts only a unique match whose difference is whitespace. It replaces that quote with the exact original source span and records both in a private audit file. Changed words, punctuation/case differences and ambiguous matches remain rejected. This is formatting repair, not semantic verification or fuzzy matching.

Normally completed raw responses can be revalidated after this repair without another inference call, provided their source fingerprint matches. Partial/truncated responses are not accepted as completed work. Originals, previous model attempts, revisions and approval boundaries remain preserved.

The affected four-picture job was recovered under the existing shared heavy lock using its first three picture caches, then its saved recap response. All four pictures and an eleven-item draft recap are saved as revision 2, state `recap-review`, with approval still absent. Manual review remains necessary. No image needed uploading again; no Knowledge ingestion was triggered.

The Notes suite contains 74 checks, including nonempty drawing retry, bounded repeated failure, completed-response reuse, whitespace-only exact-source mapping and refusal of changed/ambiguous quotes. Model quality across unseen handwriting remains an evaluation question.

The prior live adapter was backed up privately under the existing deployment backup's `notes-adapter-hotfix-1/`. Install this module atomically, then restart the idle worker with administrator access to load it. Installing the file does not replace Python's already-imported module in the running worker. No Function/valve update is necessary. Do not roll back meeting databases or delete Notes data as part of code rollback.
