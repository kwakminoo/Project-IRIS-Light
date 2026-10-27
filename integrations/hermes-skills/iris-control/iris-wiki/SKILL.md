---
name: iris-wiki
description: >
  Save notes into Iris Wiki (user vault) and open them in the Iris Wiki UI.
  Use when: 위키에 저장, Iris Wiki에 남겨, 사이트 정보 위키에, 메모 저장,
  save to wiki, write wiki note, remember this page in Iris Wiki.
---

# Iris Wiki

## Tools

Prefer Iris Agent native tools when registered. Chat speak path:
`invoke_native_tool` → `speak_invoke_agent_tool` for
`iris.wiki.list_notes` and `iris.wiki.search` (aliases `wiki.list_notes` /
`wiki.search`). That path does not use MCP Control HTTP. If a model still
emits MCP `iris_invoke` for those two actions, Iris redirects them to the
same native handlers. For write/import/open actions still on the control
catalog, call `wiki.write_user_note` / `wiki.import_content` /
`wiki.open_note` through the product tool path — never invent vault paths or
claim a note was saved unless the tool returns `ok`.

User notes live under `~/.iris-light/iris-wiki/` and appear in the UI as `user/...`.

## When

- User asks to save page/site/summary/memo **into Iris Wiki**.
- User pastes a URL and asks to capture the site info in Wiki.

## Steps

1. **PDF / URL / 파일 경로** → prefer `wiki.import_content` with `source` (one-shot extract + save + open Wiki UI).
   - `mode`: `raw` (full text) or `summarize` (LLM summary before save).
   - PDF: local `.pdf` path (user may attach file in chat — path appears in message).
   - URL: `https://...` page text fetch (stdlib; JS-heavy sites may be incomplete).
   - Text: `.md`, `.txt`, etc.
2. Or: `content.extract` first to preview, then `wiki.write_user_note` with `title`+`content`.
3. Manual markdown only: `wiki.write_user_note` with args:
   - `title` (required) — short note title
   - `content` (required) — markdown body (facts, links, bullets)
   - `source_url` (optional) — original URL
   - `rel_path` (optional) — 비우면 Iris가 임베딩 유사도와 모델 JSON으로 분류한다.
     `사용자/`(특징·취미·강점·약점·사고력·가치관), `학습자료/{분야}/`, `인사이트/{주제}/`,
     `projects/{열린 프로젝트}/`, `research/{주제}/`.
     애매하면 `inbox/` 에 남고 `ask_folder` 가 true다. inbox를 기본값으로 넣지 말 것.
   - `open` (optional, default true) — open Wiki UI on the new note
4. Confirm with the returned `rel_path` (e.g. `user/학습자료/수학/note.md`).
5. Search saved notes: `iris.wiki.search` (native) or `wiki.search` with `query`. This is not conversation History.
6. If the user only wants to open an existing note: `wiki.open_note` with `rel_path`.
7. List notes: `iris.wiki.list_notes` (native) or `wiki.list_notes`. The result `total` is the whole vault. `truncated` means this page is not the whole list. Reload UI: `wiki.reload`.
8. Move or classify notes that already exist: `wiki.move_notes` with `sources` (file or folder rel_paths) and `dest_folder`. Iris copies the same bytes and deletes the sources. Folder sources keep their folder name under `dest_folder`. Do not rewrite those notes with `wiki.write_user_note`.

## Rules

- Explaining a PDF, file, folder, or link is not a wiki save. If the user message contains `[자료 본문]`, answer from that excerpt. Do not ask for page screenshots first. Do not say PDF text cannot be read.
- Saving the chat as a PDF file is `note.export_pdf`, not this skill. Do not run PyMuPDF, reportlab, or pdf_create.py.
- Never say “저장했습니다” without a successful `wiki.write_user_note` or `wiki.import_content` result.
- Never say notes were moved or classified out of inbox unless `wiki.move_notes` returns ok and `left` is empty. A shorter new file is not a move.
- Local Iris may handle save without a remote control round-trip when the user attaches a file or pastes a URL with save intent.
- Prefer `mode=summarize` when user asks to 요약/정리; default `raw` for full capture.
- Do not write under `docs/` — user wiki only.
- Prefer the classified folder. Do not set `rel_path` to `inbox/` unless the user named that folder.
- `iris.wiki.search` / `wiki.search` reads saved notes. Do not treat those excerpts as prior chat transcripts.
- After write, Iris opens the Wiki workspace and shows the note when `open=true`.
