---
name: iris-work-start
description: >
  Start an Iris Light coding / vibe-coding session with IDE Companion and a project folder.
  Use when: 아이리스 라이트 작업 시작, 코딩 시작, IDE에서 프로젝트 열어, AI guitar tab 작업 시작,
  Companion 켜고 폴더 열기, start Iris work, open project in Cursor via Iris.
  Prefer project.open_similar or ide.open_folder — NOT terminal cursor alone, NOT ide.enter_companion
  alone (enter_companion opens welcome window without switching folder).
  Also use when: ide 켜줘, IDE 열어, Companion 켜줘 (then ide.enter_companion).
---

# Iris work start

## Steps

1. `iris_get_state` — note `project_root`, `project_parents`, `ui_mode`. Do **not** treat Hermes cwd as Iris work path.
2. If user named a project vaguely (e.g. "AI guitar tab"):
   `iris_invoke` → `project.open_similar` with `args.query`
3. Else if user said only "아이리스 라이트 작업 시작" / start Iris work (no other project name):
   `iris_invoke` → `project.open_similar` with `args.query` = `iris light`
   (prefer **Project-IRIS-Light-main** under configured parents — not the old `IRIS` / Project---IRIS repo)
4. Else if user gave an absolute path:
   `iris_invoke` → `ide.open_folder` with `args.path`
5. Else if user only asked to open IDE / Companion (no folder):
   `iris_invoke` → `ide.enter_companion`
   (Iris opens IDE first, then tiles IDE 70% + Iris 30% companion — do not use terminal `cursor`)
6. Else if creating new work (구구단 테스트 등):
   `iris_invoke` → `project.create_scaffold` with `name`, `template` (`gugudan`|`python-hello`), `open=true`
   (scaffold opens the folder in Companion and reveals the first source file in the editor)
7. If `project.open_similar` fails with `reason=ambiguous` or `low_score`:
   show `matches` to the user → then `ide.open_folder` with the chosen `path`
   (or retry `project.open_similar` with `force=true` only if user confirms the top match)
8. Confirm with `iris_get_state` (`ui_mode=ide_companion`, `project_root`)
9. After the project is open, coding / run requests → follow skill **iris-vibe-code**
   (`project.write_file` with `open=true`, `project.run` for execution).

## Do not

- Do not use terminal `cursor`/`code` alone (skips Iris Companion tiling).
- Do not rely on `ide.enter_companion` to switch folders — use `ide.open_folder` / `project.open_similar`.
- Do not invent a fixed project path when Iris control tools fail — say tools are unavailable and ask the user to open Iris + sync MCP in Settings.
