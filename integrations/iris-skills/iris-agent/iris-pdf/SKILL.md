---
name: iris-pdf
description: >
  Route PDF intents through Iris SpeakTools: extract text, dump lecture labs,
  import into Wiki, or export chat/notes as a PDF file.
  Use when: PDF 읽어줘, PDF 설명해, 실습 전부 만들어, 랩 스크립트 파일로,
  위키에 PDF 저장, 채팅을 PDF로, explain this PDF, dump lab scripts,
  import PDF to wiki, export note as PDF.
allowed-tools: content.extract content.dump_lab_scripts wiki.import_content note.export_pdf
---

# Iris PDF

PDF work uses product SpeakTools only. Do not invent absolute host paths from
`get_state`. Prefer `attachment_id` from `attachment.list` / chat chips.

## Routing

| User intent | Action | Args |
|-------------|--------|------|
| Explain / read PDF text | `content.extract` | `{attachment_id}` |
| Dump all lecture labs to files | `content.dump_lab_scripts` | `{attachment_id}` (optional `out_dir=labs`) |
| Save PDF into Iris Wiki | `wiki.import_content` | `{attachment_id}` (`mode=raw\|summarize`) |
| Write chat/note out as PDF file | `note.export_pdf` | `{content}` and/or `{sources}`, optional `{path}` |

## Steps

1. Resolve the attachment (`attachment_id` uuid or unique filename). Do not guess
   host paths.
2. Pick the row above from the user intent.
3. Confirm from the tool result (`ok`, written paths, or `rel_path`). Do not
   claim success without it.

## Examples

- "이 PDF 설명해줘" → `content.extract` `{attachment_id}`.
- "실습 전부 만들어" / "프로그램 N-M 파일로" → `content.dump_lab_scripts`
  `{attachment_id}` (optional `out_dir=labs`). Reply with returned paths only.
- "이 PDF 위키에 저장" → `wiki.import_content` `{attachment_id}`.
- "채팅을 PDF로 저장" → `note.export_pdf`.

## Do not

- Do not `local.read_file` a `.pdf` for text extract or lab dump (binary).
- Do not use Iris Agent `terminal` / bash with pdfplumber, PyMuPDF, or reportlab.
- Do not invent absolute host paths from `get_state` for these intents.
- Do not ask the user to paste the full PDF when `attachment_id` is available.
- Explaining a PDF is not a wiki save; wiki save is not `note.export_pdf`.
