# Notes review effort and handwriting adaptation

30 October 2026. Revised product direction; no change to the frozen meeting workflow.

## Daily review

Do not require individual acceptance of every extracted region, list item and arrow. The earlier 31-item diagram count was a reference annotation workflow, not a reasonable daily-use requirement. The v2 reference prototype defaults to flagged regions, retains an All regions view and offers one explicit Confirm page reviewed action. Individual checks are optional. Remaining uncertainty is retained when a page is confirmed, and any subsequent content/flag/endpoint edit invalidates page confirmation. Reference confirmation is distinct from recap approval and Knowledge ingestion.

Production Notes should ask about risky/ambiguous regions. Clear regions need no individual interaction. Keep the original image, complete editable transcription and drawing descriptions accessible. A low-risk page can yield an unapproved recap draft without a mandatory region-by-region or extra transcription approval ceremony; unresolved material that would change a factual claim should be clarified or explicitly omitted/retained as unresolved. Approval of the exact recap revision remains explicit and separate from saving. This revises the proposed Notes UX only; do not change the accepted meeting confirmation flow.

## Doubt threshold

The threshold should control review priority, not act as an automatic approval threshold or a claim of calibrated model certainty. Current models produced errors with empty uncertainty lists; model-reported confidence alone cannot decide which source material is safe.

Candidate signals: reported unreadability; disagreement on a targeted crop reread; unfamiliar personal names and technical labels; dates, amounts and negation; suspected missing text/edge clipping; uncertain arrow endpoints; crossouts and model output limits. Poor OCR may offer text-region coverage hints but cannot supply reliable handwriting ground truth. No second model needs to run on every page: rereads should be targeted and serialized in the same heavy-work queue.

Initially use explainable review flags. After owner-reviewed data is available, compare threshold settings by questions per page, correction time and material errors left unflagged. Do not invent a 90%/95% confidence cutoff before calibration. Include a small sample of apparently clear regions during evaluation so confidently wrong omissions do not disappear from measurement.

The v2 prototype filters the existing human-authored draft flags. It does not run an uncertainty detector, compute calibrated risk scores or implement an inference threshold. An unflagged region is not guaranteed correct. It is a UI experiment demonstrating lower review effort.

## Learning from corrections

Saving a correction does not automatically train or alter the installed model. The current prototype stores reference edits; it does not yet adapt future inference.

First implement a private, owner-scoped, versioned correction memory: original image hash and region/crop, previous reading, corrected text, language/context, explicit confirmation, timestamps and correction revision. Preserve the original and prior revisions. Only owner-confirmed corrections become hints; model guesses and unapproved recaps must not teach the system.

Use that memory conservatively: a short glossary of confirmed names/acronyms, plus a bounded set of relevant corrected handwriting examples where the chosen model supports image exemplars. Condition future extraction on relevant examples and retain uncertainty if source evidence conflicts. Do not install global string replacements: a previously misread personal name may legitimately occur as a different name on another page. Permit correction removal and rollback; keep owners isolated.

Measure improvement on later unseen pages with and without hints. Distinguish better recognition from memorizing the evaluation reference or merely suppressing doubts. This may reduce recurring errors, especially vocabulary, but does not guarantee steady improvement in general handwriting recognition.

Actual handwriting-model adaptation/fine-tuning is a separate later experiment requiring curated crop/text pairs, a compatible training stack and measured hardware requirements. Parameter-efficient training such as LoRA still requires a training step: https://huggingface.co/docs/peft/main/en/conceptual_guides/lora . The installed inference model must not be modified silently after each edit. Do not claim that the UM870 can train the chosen vision model until measured.

## Validation of the prototype revision

Verify: flagged-only and full views; one explicit page confirmation; flags retained after confirmation; edits invalidate confirmation; save alone does not confirm; original v1 tab/work remains untouched. No Notes model, server service, meeting code, approval or ingestion setting changes as part of this UI revision.
