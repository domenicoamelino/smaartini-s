# SMARTINI’s Notes reference review prototype

Open the delivered SMARTINIS-NOTES-REVIEW.html in a browser. It includes three private source images, draft text, drawing descriptions and uncertainty flags. It runs no model and makes no external requests. Keep the generated HTML and reference exports private.

## Review

1. Choose a page, then a region. The amber outline locates its approximate source region. Zoom the original as needed.
2. Correct wording literally; retain original languages, questions and negation. Keep [unclear] for unreadable text. Correct/remove uncertainty flags only after inspecting the source.
3. Mark the region checked. Editing wording, flags or exclusion status clears that marker.
4. Review drawing descriptions and arrow endpoints in Drawings & arrows. A self-arrow cannot be saved.
5. Save reference revision for browser-local persistence; export the reference set for a portable record. A browser save is not a backup, production immutable revision, recap approval or Knowledge ingestion.
6. Import the complete reference set or a single-page export into this same source-image set. Original hashes must match. Exports contain no embedded image bytes.

All supplied text and geometry are draft annotations except the four previously confirmed names on the sparse page. Browser tests do not certify handwriting accuracy. Region-based editing is deliberately a prototype to evaluate correction effort. No recap generation/approval/ingestion is connected.

## Rebuild from private source material

Requires Node.js 18+; no package installation is needed:

node build_notes_review.cjs reference.json path-to-private-original-images new-review.html

Place the builder beside notes_review_template.html. Input reference schema is smartinis-notes-reference-set/1; each page has a basename and exact original SHA-256. Output must not already exist. The builder rejects mismatched hashes, paths outside the supplied image directory and oversized images. The built HTML embeds originals without changing them. Real references and generated embedded-image HTML must not be committed to the source repo.

Run the synthetic builder checks with:

node test_notes_review_builder.cjs

The tests leave synthetic fixtures in a builder-test-* directory beside the script. Six check groups passed in the supplied environment. All three supplied page documents also passed the Python Notes contract validator. Desktop browser interactions were checked; mobile CSS has not been tested at a mobile viewport.

The source template/builder are model-independent. This is an unauthenticated local research prototype, not the production owner-isolation or durable-job implementation.

## v2 review update

Individual region confirmations are optional. The default Flagged regions only view directs attention to existing draft uncertainty; All regions exposes the complete transcription and relations. A single Confirm page reviewed action covers the page and retains unresolved flags. Subsequent text, flag, arrow, exclusion or clipping changes invalidate page confirmation. Saving alone does not confirm the page or approve a recap. The supplied flags are draft annotations, not a calibrated model confidence threshold. The separate Notes review/learning design describes future inference triage and correction memory; neither is implemented by this offline prototype. Do not treat fewer visible flags as verified model improvement.
