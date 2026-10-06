---
name: iris-vibe-code
description: >
  Vibe-coding in Iris: write/reveal code in the IDE editor, optionally stream chunks
  so the user watches the file grow, then run with full output in IDE and a short
  summary in Iris chat. Use when: 코드 작성, 파일 만들어줘, 보여주면서 작성, 바이브코딩,
  실행해줘, run this, 구구단 만들어 실행, write file and show in Cursor.
---

# Iris vibe code

## Steps

1. `iris_get_state` — need `project_root` and preferably `ui_mode=ide_companion`.
   If no project / not companion: follow **iris-work-start** first (`project.open_similar` / `ide.open_folder` / `project.create_scaffold`).
2. **Write + reveal live:**
   `iris_invoke` → `project.write_file` with
   `args`: `{ project_root?, rel_path, content, open: true }`
   `rel_path` is the file the user named. If they did not name one, ask before writing. Do not invent `iris_generated.py`.
   → Iris opens an empty tab, waits until the filename is visible in the IDE title, then streams small chunks into the file so the IDE file watcher shows the code growing. Do not set `typewriter:false` unless the user wants an instant dump.
2b. **Rename:**
   `iris_invoke` → `project.rename_file` with
   `args`: `{ path, new_path }`
   `path` is the current file (from `project.list_files` or the open editor). `new_path` is the name the user asked for. If either is unknown, ask. Do not rename by matching words in the sentence inside the app.
3. Optional speed: `chunk_delay_ms` and `chunk_chars`. `typewriter:false` / `stream:false` = write all at once after open.
4. **Run:**
   - **Scripts (.py / .js / …):** `project.run` with `{ file: "…" }` or `{ command: "…" }`
     → full output in **IDE integrated terminal**; chat gets short `summary` only.
   - **Static web (.html / .htm):** `project.run` with `{ file: "index.html" }`
     → opens the default **browser** (`file://…`). Set `open_browser:false` to skip.
   - **Dev server** (`npm start`, `npx vite`, `python -m http.server`, …):
     `project.run` with `{ command: "…" }` (optional `preview_url`) → terminal + browser localhost.
5. Confirm from invoke result: `visible`, `typed`, `ide_terminal` / `browser`.
6. **Read the editor before claiming a fix:**
   `ide.diagnostics`. `reported: false` means markers were not pushed — do not say there are no problems.
   An empty `diagnostics` list is clean only when `reported` is true.
   Symbols, references, and definition: `ide.symbols`, `ide.references`, `ide.definition`.
   Do not invent locations when `ok` is false.
7. **Change the open buffer:** `ide.edit` (`op=insert|replace_selection|replace_range|apply`, `text`, optional `path`).
   `via=editor` is the buffer. `via=disk` with `applied=append` is not a selection replace — say so.
   Then `ide.save` (`path`, or `all=true`). `via=editor` flushed the buffer.
8. **Task / debug:** `ide.task` needs `name` from tasks.json. `ide.debug` `op=start` needs `name` (launch configuration); `op=stop` or `continue`.
   No session or no task is not success.

## Do not

- Do not use Hermes `terminal` alone for project runs (skips IDE terminal reveal).
- Do not use `cursor`/`code` CLI alone to write or run.
- Do not open run logs as files in the editor — terminal only.
- Do not double-run the same command.
- Do not say the buffer, the problems list, or a debug session changed unless that action returned ok.
