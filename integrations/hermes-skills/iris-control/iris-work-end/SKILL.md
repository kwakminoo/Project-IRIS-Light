---
name: iris-work-end
description: >
  End Iris Light IDE Companion ONLY when the user explicitly asks to close it.
  Trigger phrases: Companion 끄자, IDE 꺼, IDE 닫아, 타일 해제, exit companion,
  leave IDE companion, 기본화면으로 (and they mean leave Companion).
  Do NOT use when coding/scaffold/run simply finished — stay in Companion until asked.
---

# Iris work end

## When

- User **explicitly** asks to close Companion / IDE / leave companion / return to normal layout.
- User asks to leave Companion **and** open another screen (email / wiki / calendar).

## When NOT

- After `project.write_file` / `project.run` / scaffold succeeds.
- After a short “done” status in chat.
- Because the model thinks the task is complete.

## Steps

1. `iris_get_state`
2. If `ui_mode` is `ide_companion`, `iris_invoke` → `ide.exit_companion`
   (restores Iris normal layout; **closes the Companion IDE window Iris opened**,
   never the Cursor that hosts Iris / the user’s own workspace)
3. If the user also asked for another screen, invoke:
   - `workspace.open_email`
   - `workspace.open_obsidian`
   - `workspace.open_calendar`
   - `workspace.open_assistant`
4. Short status from `iris_get_state`
