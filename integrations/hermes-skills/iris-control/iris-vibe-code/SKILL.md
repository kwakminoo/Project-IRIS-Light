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
2. **Write + reveal + type:**
   `iris_invoke` → `project.write_file` with
   `args`: `{ project_root?, rel_path, content, open: true }`
   → Iris opens an empty tab, waits until the filename is visible in the IDE title, then **types** the code into the editor (typewriter). Do not set `typewriter:false` unless the user wants an instant dump.
3. Optional speed: `delay_ms` (per character). `typewriter:false` / `stream:false` = write all at once after open.
4. **Run in IDE terminal:**
   `iris_invoke` → `project.run` with
   `args`: `{ file: "rel/path.py" }` or `{ command: "python …" }`, `reveal_terminal: true`
   - Full output appears in the **IDE integrated terminal** (Build Task / Ctrl+Shift+B).
   - In Iris chat: only `summary` + short tails. Never open `.iris/last_run.log` as an editor tab. Never paste full logs into chat.
5. Confirm from invoke result: `visible`, `typed`, `ide_terminal` (`ok` = terminal).

## Do not

- Do not use Hermes `terminal` alone for project runs (skips IDE terminal reveal).
- Do not use `cursor`/`code` CLI alone to write or run.
- Do not open run logs as files in the editor — terminal only.
- Do not double-run the same command.
