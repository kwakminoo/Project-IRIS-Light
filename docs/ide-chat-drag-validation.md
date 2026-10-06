# IDE chat drag and orb fade — 2026-10-06

## Cause and changes

Chat expansion released each preceding widget's minimum height to zero and
changed only its maximum. In the IDE column, these widgets use a Fixed size
policy, so Qt immediately reduced both the orb slot and Live Activity to zero
instead of the requested intermediate height. A 10px drag moved the chat from
y=368 to y=18 in the standalone reproduction.

Preceding widgets now receive their exact intermediate height. Zero-height
sections remain in the layout so removal of layout gaps cannot cause a jump.
The orb uses a backdrop confined to the Companion column, with its original
260px viewport and center maintained while the reserved layout slot shrinks.
The existing main-chat `set_chat_fade_y` blur/alpha renderer is reused.
The backdrop passes mouse input through to the activity/chat controls.

Mount/unmount resets expansion constraints before moving widgets to another
workspace. Reopening an IDE folder preserves an existing expansion instead of
resetting the orb reservation to 260px.

## Verification

- 18 related regression tests passed, including chat scrolling, startup and
  Windows IDE hooks; the IDE tile check also passed.
- Real Qt layout: all 351 pixel positions from 0 through 350px, then back to 0,
  match the requested chat movement exactly. Orb center remains unchanged.
- Blur/fade alpha decreases as the chat edge crosses the fixed orb coordinates;
  collapse restores the original constraints and removes the fade boundary.
- Transfer to another layout and remount discard obsolete drag snapshots.
- `python -m iris.ui._check_iris_ide_companion_tile` passes.
- `python scripts/check_ide_folder_open.py --drag` loads the actual installed
  Theia in QWebEngine, checks continuous dragging and stable orb position,
  reopens the folder, verifies the 180px expansion persists, restores the
  original height, and shuts down normally. It uses an isolated DB and suppresses
  unrelated boot jobs through `MainWindow(test_mode=True)`.
- A rendered screenshot was inspected to check the Companion column, orb fade
  and chat/activity placement. The native docked Theia surface is not included
  in Qt's window grab; its load was verified through the real load signals.
