# Notes — initial UM870 benchmark

30 October 2026. Development probes, not production acceptance or a final model selection.

## Observed host and preserved baseline

SSH succeeded at the supplied IP with strict host-key verification. AMD Ryzen 7 8745H, eight cores / sixteen logical CPUs; 29,341 MiB usable RAM, initially 25,027 MiB available; 8,191 MiB swap with 1 MiB used. The runtime reported Ollama 0.40.6. Its advertised vision support was verified with actual image requests to the installed Qwen 3.5 4B and 9B Q4_K_M artifacts. No hardware acceleration claim is inferred from the runtime’s size_vram field.

Meeting workflow/dashboard remained 2.7.1 with ok=true and worker_alive=true before and after experiments. The existing user timer still lists 31 October 2026 at 03:00 CET as its next ingestion, with a last run at 30 October 03:00:53 CET. This verifies scheduling, not ingestion success or indexed replacement. No service was restarted. All inference models had unloaded at the final check; available RAM returned to 25,021 MiB and swap use remained 1 MiB.

## Vision compatibility runs

One request per model/page, serialized; not a repeated warm/cold performance study. Image inputs were original full screenshots. Local chat requests used context 8,192, maximum output 3,000 tokens, temperature zero, thinking disabled and keep_alive=0. No request hit its output cap. Approximate whole-host available-memory minima were sampled every second; these are not model peak RSS figures.

| Model | Page | Seconds including load | Minimum available RAM, GiB |
|---|---|---:|---:|
| qwen3.5:4b | IMG_0002.PNG | 65.5 | 21.2 |
| qwen3.5:9b | IMG_0002.PNG | 99.4 | 18.4 |
| qwen3.5:4b | IMG_0004.PNG | 101.7 | 21.2 |
| qwen3.5:9b | IMG_0004.PNG | 141.7 | 18.4 |

Both runs on the sparse page used about 4,059 prompt tokens. Load times varied from roughly two to ten seconds. The 4B sparse run generated 319 tokens, 9B sparse 291, 4B diagram 813 and 9B diagram 643; output lengths differ, so raw wall time is not a controlled speed ranking.

The probe requested a JSON object, but did not enforce a strict JSON schema. The 4B model returned object-based layout entries where the prompt requested strings. Therefore its status=completed means an image request ended normally and returned parseable JSON; it does not mean the future Notes page contract passed. No probe result was trusted as reviewed or approved.

## OCR baseline

RapidOCR 3.10.0 / ONNX Runtime 1.31.1 installed successfully on Python 3.14.4 in a new experiment-only virtual environment. Latin PP-OCRv5 mobile recognition and PP-OCRv5 mobile detection ran locally. Package versions and model SHA-256 hashes were recorded privately. Initial model downloads were setup traffic; the handwriting inference itself was local. The existing meeting environment was not modified.

Unlike the vision probes, OCR used a manually specified content crop, [60,350,1608,2348], removing most app chrome. Crop-relative boxes were retained. This input difference and the single-run design limit a direct quantitative accuracy or timing comparison.

Default detection/line rotation: sparse page 5.85 seconds / 35 regions; diagram page 1.74 seconds / 151 regions. A follow-up disabled line rotation and raised detection resolution: sparse page 0.82 seconds / 18 regions; diagram page 1.25 seconds / 132 regions. Process peak RSS was roughly 0.5–0.8 GiB across these runs. These timings exclude engine initialization/model download and do not establish stable throughput. Both settings heavily fragmented and misrecognized the handwriting. The crop also retained a page-counter overlay; chrome exclusion needs explicit testing.

An initial adapter call failed because this package requires enumeration values for model configuration. The adapter was corrected and both configurations completed. No meeting code was involved in the failure.

## Qualitative findings

The sparse page: vision recovered most readable prose and list structure; models disagreed on personal names, acronyms and wording. The 4B model supplied no uncertainty flags despite visible mistakes. The 9B model flagged some names but did not flag all discrepancies. Neither output is ground truth.

The diagram page: 4B extracted the main client → gateway → application → connector → document system flow, but changed labels, altered technical language and translated some Italian into English despite preservation instructions. The 9B output recovered some labels better but still changed terminology and gave weak uncertainty explanations. Do not promote its apparent fluency into factual accuracy. Both require source-side review of relationships and labels.

The OCR configurations were fast but text quality was poor on these two pages. This is evidence against these specific OCR configurations as the primary transcriber, not proof that every handwriting recognition system fails. OCR bounding boxes might still help locate review regions, but this has not been evaluated against annotated ground truth.

## Current decision

Continue with pluggable, vision-first extraction as the next engineering experiment. Retain OCR as an optional region/location candidate; do not automatically feed its noisy text into the recap. Do not lock 4B or 9B as the final extraction model yet. A mixed architecture remains conditional on measured benefit, not a requirement to run two models on every page.

Image generation is unnecessary for extracting drawings. Preserve the source drawing and review its description, labels and directional relationships. Any later clean generated illustration must be a separate reviewed artifact and cannot become evidence for the recap.

## Remaining acceptance evidence

Owner-corrected literal reference transcription, especially names/acronyms; annotated reading order/arrow endpoints/crossouts; substantial Dutch and Italian samples and unseen phone photographs; matched crops/resolution and repeated runs; measured correction effort; strict schema/truncation validation; confirmed-source recap quality; runtime acceleration inspection; coexisting workload checks. No verified word/character accuracy percentage or universal model ranking is reported.

The independent meeting gates—population, indexed revision replacement, cross-meeting cited RAG and isolated off-device restore—remain separate and unverified by these probes.

## Implementation completed alongside the probes

notes_document.py and review_tests/test_notes_document.py were added to the existing source repo; nine synthetic tests passed on the UM870. Exact source hashes matched the local repo files. No existing meeting source file was modified. See SMARTINIS-NOTES-CHECKPOINT.md for implemented contracts and remaining integration work. This is an early implementation milestone; upload, durable Notes scheduling, dashboard, approval and ingestion integration are not yet implemented or deployed.

## Primary technical references consulted

- [Ollama API specification](https://github.com/ollama/ollama/blob/main/docs/openapi.yaml): image request fields and structured output support.
- [Qwen 3.5 model library](https://ollama.com/library/qwen3.5): family capabilities; local installed artifacts and actual probes were used for compatibility evidence.
- [RapidOCR source](https://github.com/RapidAI/RapidOCR): toolkit/runtime implementation. Installed package API/configuration was inspected directly before use.
- [PaddleOCR multilingual recognition documentation](https://paddlepaddle.github.io/PaddleOCR/main/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html): candidate language scope, not validation of this user’s handwriting.

