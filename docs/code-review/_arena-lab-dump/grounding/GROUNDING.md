# Grounding: chip PDF lab-script dump (Feature)

## Goal

User attaches a lecture PDF (chip) and asks to create every practice script with names as in the PDF (e.g. `7-5.py`, `프로그램 7-7`). Iris must write files without stuffing the full PDF into the 24k model context.

## Policy (locked)

- Keep global limits: `MAX_FILE_BYTES` 20MB, `MAX_CONTEXT_CHARS` 24k, `MAX_PDF_PAGES` 200, `VISION_PAGE_CAP` 4, `content_extract._MAX_CHARS` 80k.
- Lab-dump path does **not** put the full extract into Hermes messages.
- Extract page-by-page (reuse `read_pdf_pages` / OCR hybrid), parse program labels, write files under project root (or a clear default folder).
- Model gets a short summary list of written paths only (or skip Hermes and emit a fixed Iris reply).

## Current path (measured)

```
chip PDF + text
  → AttachmentWorker → prepare_attachments (_read, budget 24000)
  → truncated=true often
  → Hermes sees partial BEGIN ATTACHMENT TEXT
  → asks user for paste instead of writing all labs
```

Key files:

- `iris/runtime/attachment_context.py` — `MAX_CONTEXT_CHARS`, `_read`, `_parts` PDF via `read_pdf_pages`
- `iris/knowledge/content_extract.py` — `read_pdf_pages`, hybrid OCR when page has images
- `iris/ui/window/main_window.py` — `_continue_user_turn_bound` after AttachmentWorker
- `iris/system/project_ops.py` — `write_project_file`
- `iris/ui/_check_chip_pdf_enrich.py` — existing PDF enrich checks

## Data shape (preferred)

```
LabProgram = { label: str, filename: str, body: str, pages: list[int] }
LabDumpResult = { programs: list[LabProgram], written: list[str], errors: list[str], truncated_pages: bool }
```

Organize as a small pure module (parse + dump) + thin UI hook. Not another boolean on MainWindow.

## Non-goals

- Removing global attachment limits
- IDE PDF viewer
- Asking the model to shell out to PyMuPDF
