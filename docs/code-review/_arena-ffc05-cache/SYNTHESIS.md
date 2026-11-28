# FFC-05 Extraction Cache — Arena Synthesis

| 항목 | 내용 |
|---|---|
| Base | Candidate B (store-bound memo, process LRU + TEMP spill) |
| Cross-judge | Skipped vendor seat — both runners were `auto`/same parent |
| Grafts from A | (1) skip cache when `vision_reader` / `vision_all` (2) optional full-file hash not grafted — size+mtime+invalidate-on-drift wins |

## Rubric scores (1–5)

| Criterion | A | B |
|---|---|---|
| Key uniqueness (no filename-only) | 5 | 5 |
| Access revalidation + invalidate | 4 | 5 |
| Namespace isolation + size/TTL | 4 | 5 |
| Minimal wire / leaf purity | 3 | 5 |
| Self-check without live OCR | 5 | 5 |
| Laziness / fewest concepts | 3 | 5 |

## Why B

Session `AttachmentStore` already owns access and detach. Binding memo lifetime to the store matches FRC-05 progress (`mtime/size` + window + ocr). Full blake2b on every large PDF (A) costs more than the prompt requires. Caching inside `read_pdf_pages` (A) couples leaf checks to session state.

## Rejected from A

- Persistent `~/.iris-light/cache/extraction` across process (orphan + awkward revoke)
- Primary wrap of `read_pdf_pages` (breaks path-only unit checks)

## Locked for implementers

Follow `candidate-b/DESIGN.md` plus: never put when vision is active; never put errors/cancel.
