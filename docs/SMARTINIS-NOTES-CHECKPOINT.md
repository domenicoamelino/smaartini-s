# Notes implementation checkpoint — 30 October 2026

## Implemented source

Two additive files were added to the existing AARTINS checkout:

- notes_document.py: single-page document and evidence-linked recap validation; canonical revision fingerprints.
- review_tests/test_notes_document.py: nine synthetic tests, all passed on the UM870 with Python 3.14.4 in the isolated experiment folder using the same source files.

This is a model-independent foundation, not the completed Notes application. No meeting source file, database, Function, service, approval or Knowledge collection was changed. Changes are uncommitted and unpushed.

The page contract supports stable block IDs, normalized bounding boxes, ordered blocks, typed list/drawing/crossout/illegible regions, uncertainty flags, reviewed/excluded markers and arrow/containment/list-child relations. Original image SHA-256 is mandatory. Crossed-out and illegible blocks are excluded; restoration requires an explicit reviewed kind change. Recaps reference the fingerprint of the exact page revision, including layout and image identity. Every item requires a quote matching a reviewed, included source block.

These checks establish structural traceability, not truth or semantic entailment. Authentication, trusted assignment of human-review flags, immutable persistence, concurrent revision checks and approval remain responsibilities of the eventual integration. Inference output must never be copied directly into trusted reviewed/approved status. No automatic approval exists in this module.

## Verified tests

- Mixed EN/NL/IT synthetic source with supported recap.
- Layout changes invalidate an older recap.
- Text/original image changes invalidate an older recap.
- Unreviewed, excluded and crossed-out evidence is refused.
- Wrong quotes, missing blocks and absent evidence are refused.
- Non-finite, inverted, out-of-range and boolean coordinates are refused.
- Duplicate block IDs and missing relation endpoints are refused.
- Crossouts require exclusion or explicit restoration.
- Unknown model fields, including an invented approval field, are refused.

Run from repo root: python -m unittest discover -s review_tests -p test_notes_document.py -v

Only the new nine tests were run for this additive foundation. Full meeting regressions, browser testing and end-to-end Notes tests remain required when integration begins.

## Local experiment boundary

SSH access succeeded at the user-provided IP using strict host-key verification. The previous hostname trust issue did not recur at this address. Experiments live in a private notes-20261030 folder below ai-platform/experiments. Two original screenshots were copied there for local inference. Originals in OneDrive were unchanged; real images, outputs and OCR weights were not added to Git.

OCR dependencies and downloaded weights are confined to a new experiment virtual environment. The meeting virtual environment was not modified. Inference used the installed local Ollama service and installed Qwen 3.5 models. No image was sent to an external OCR/inference endpoint by these benchmark scripts. Model/package downloads are setup traffic; the current OCR experiment is not yet certified network-disabled reproducible deployment.

## Remaining work

1. Complete representative handwriting evaluation, including Dutch/Italian and unseen photographed pages, plus owner-corrected ground truth. Measure warm runs and actual correction effort; inspect runtime acceleration rather than inferring it from model metadata.
2. Implement durable Notes job/upload and immutable revision persistence through narrow reuse of existing machinery.
3. Implement the dedicated Open WebUI Function, owner-scoped dashboard image/transcription/layout review and local extraction adapter with strict schema and truncation rejection.
4. Add confirmed-source compact recap, manual editing and separate exact-revision approval.
5. Add typed approved-only nightly ingestion/replacement and owner-bound Telegram links; extend private backup/restore coverage.
6. Run full regressions, browser/security/recovery checks and prepare the complete reviewed deployment/rollback package. Deploy only with authorization.

The prior independent operational gates and later product roadmap remain as documented in SMARTINIS-NOTES-PLAN.md.
