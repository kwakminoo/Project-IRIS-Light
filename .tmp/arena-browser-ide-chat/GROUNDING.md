# Grounding: dedicated browser uses the same ChatPanel as IDE

Repo: C:/Users/serin/Github/Project-IRIS-Light
HEAD: serin @ 7ec6656
origin/main: 74c1a19
merge-base: ee099c2

## What already exists on this branch

Dedicated browser (`_show_dedicated_browser`) remounts `self._companion_page` with `self._chat` (the single ChatPanel) onto `IdeUnifiedShell`. Left occupant is BrowserPanel via `mount_left_browser`. IDE-internal browser stays on IrisIdeWindow._stack. One ChatPanel instance. addWidget remount. No second composer.

## What origin/main changed (chat)

ChatPanel: wiki quote strip, `_presenting` / `set_presenting` / `is_typing_active` / `typing_finished`, GPT matrix fences (`gpt_answer_contract`), chat.exec_python.
DragTab: header TTS toggle (`tts_clicked`, `set_tts_enabled`).
IdeUnifiedShell on main: hover-reveal splitter handle, `mount_workspace`, `COMPANION_CONTENT_RATIO`, `resizeEvent` re-apply ratio. **Deletes** `mount_left_browser` / `left_browser` / `clear_left_browser`.

## Constraints

Do not merge origin/main wholesale (wiki/email/obsidian ~6k lines, user said so).
Preserve uncommitted silero/model_prefs.
Do not clone ChatPanel.
Keep dedicated vs ide_internal separate.
Keep BrowserSession + Hermes tool calling.
Keep mount_left_browser.

## Domain shape

One ChatPanel owned by MainWindow. Screens remount it. ViewHost tagged union already distinguishes dedicated vs ide_internal left occupant. Chat state is the widget + `_history` / ChatRunSlot, not per-screen copies.
