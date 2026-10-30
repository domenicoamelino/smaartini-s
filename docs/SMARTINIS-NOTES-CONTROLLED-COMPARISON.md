# Notes controlled comparison — source-safe checkpoint

30 October 2026. Development experiments; no final model selection or production deployment.

Two private development pages were compared using identical content crops, a common strict extraction schema/prompt, 8,192 context, maximum 3,000 output tokens, temperature zero and thinking disabled. Owner corrections were not supplied as model hints. Requests were serialized. Private images, literal reference text, name spellings and raw outputs remain outside Git.

| Installed model | Sparse page, seconds | Diagram page, seconds | Outcome |
|---|---:|---:|---|
| Qwen 3.5 4B Q4_K_M | 37.2 | 81.7 | Both strict-schema outputs completed |
| Qwen 3.5 9B Q4_K_M | 78.7 | 117.9 | Both strict-schema outputs completed |
| Gemma 4 12B Q4_K_M | 218.5 | 218.5 | Both reached output limit; incomplete JSON rejected |

These are single runs including load, not stable latency estimates. Cropped-input results are separate from the earlier full-screenshot probes. The two Qwen candidates each matched two of four owner-confirmed name fields in the controlled sparse-page run. That is not a whole-page accuracy score or proof of a model ranking. Gemma's failure here does not change the accepted meeting text-recap model or configuration.

Strict output shape did not ensure faithful content: labels changed, language preservation and completeness varied, and uncertainty lists were unreliable. One candidate omitted useful diagram relationships while the other still changed technical labels and shortened lower responsibilities. The final choice remains open pending corrected references and correction-effort measurement.

Other installed vision candidates include Gemma 26B A4B QAT, Qwen 27B and Qwen 9B Q8. They have not been tested for Notes; larger residency and backend compatibility need measurement. Text-only installed candidates cannot extract images directly.

A private three-page reference draft has 46 unchecked text/drawing blocks, five draft relations and four drawing descriptions. Only previously supplied name corrections are owner-confirmed. All three nested page documents passed notes_document.validate_page. No reference is claimed fully certified; no unseen holdout or substantial Dutch/Italian handwriting evaluation has passed.

The new notes_prototype source contains only a generic self-contained review template and builder, with no private page text or images. It supports source-side editing, uncertainty flags, drawing/arrow review, browser-local revision saves and source-hash-bound JSON import/export. Saving a reference does not approve a recap or ingest Knowledge. Source-region geometry is approximate. This is an unauthenticated local prototype, not production owner isolation or durable job integration.

Six synthetic builder check groups passed. Desktop browser checks covered page/region selection, edit invalidation of checked status, save/reload persistence, drawing/arrow controls and rejection of an invalid self-arrow. Mobile CSS exists but was not tested at a mobile viewport. Real references and generated embedded-image HTML must stay outside Git. See notes_prototype/README.md for build/review instructions.

The deployed worker/review hashes matched inspected source; meeting 2.7.1 stayed healthy. No inference models remained loaded after the runs, available RAM returned to approximately 24.5 GiB and swap use stayed at 1 MiB. No existing working meeting code, service, Function, timer, approval, database or Knowledge entry changed. See SMARTINIS-NOTES-QUEUE-SAFEGUARDS.md for the existing single-worker scope and required Notes queue integration.

Full private results and the draft review deliverables are stored in the current chat outputs and the private experiment directory, not in this repository. The SSH console did not close cleanly at the end; remote process inspection showed no benchmark process remained and all six results were retrieved before closing the idle client.
