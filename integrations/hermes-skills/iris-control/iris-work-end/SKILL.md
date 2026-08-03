---
name: iris-work-end
description: >
  End Iris Light IDE Companion / coding layout session.
  Use when the user says: Companion 끄자, 코딩 끝, IDE 타일 해제, 작업 종료하고 메일,
  exit companion, leave IDE companion mode.
  Restores Iris normal layout and closes the companion IDE window.
---

# Iris work end

## Steps

1. `iris_get_state`
2. If `ui_mode` is `ide_companion`, `iris_invoke` → `ide.exit_companion`
   (closes the IDE window Iris opened for Companion)
3. If the user also asked for another screen (email / wiki / calendar / assistant), invoke:
   - `workspace.open_email`
   - `workspace.open_obsidian`
   - `workspace.open_calendar`
   - `workspace.open_assistant`
4. Short status report from `iris_get_state`
