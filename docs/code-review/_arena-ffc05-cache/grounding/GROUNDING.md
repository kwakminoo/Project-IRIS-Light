# FFC-05 Extraction Cache — Arena Grounding

## Goal
Safe extraction/OCR result cache for Iris document intelligence (FFC-05).

## Must keep
- PyMuPDF / pypdf / Tesseract paths and existing error codes (PDF_EMPTY, ENCRYPTED, CORRUPTED, RENDER_FAILED, OCR_*, EXTRACTION_CANCELLED).
- Access revalidation on hit; invalidate on change/delete/revoked access.
- Namespace isolation (principal/session). Size + retention limits. Temp cleanup.
- Never reuse cache by filename alone.
- Key includes: file content fingerprint, page/range, extraction method, OCR engine version/language/render settings, relevant config.
- No absolute paths in provider-facing payloads.
- Wire into `extract_from_source` / `read_pdf_pages` callers used by wiki `content.extract`, attachment_context, page_vision paths without breaking existing self-checks.
- AttachmentStore.canonicalize_attachment_ref stays source of truth for basename→id.

## Existing code
- `iris/knowledge/content_extract.py` — extract_from_source, read_pdf_pages, _ocr_*
- `iris/runtime/attachment_store.py` — canonicalize, resolve_file, roots (mtime/size in index)
- `iris/ui/control_actions/wiki.py` — content.extract
- Progress note: docs/code-review/wave17-frc05-progress-2026-11-27.md (cache still open)

## Artifact each candidate produces
`DESIGN.md` only (no code). Name: data shapes, module boundary, get/put/invalidate API, where wired, self-check plan, rejected alternatives.
