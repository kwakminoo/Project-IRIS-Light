# Synthesized design. Dedicated browser is a left occupant of IdeUnifiedShell

## Synthesis decision

Base is candidate-1. Cross-judge totals C1 29 / C2 25. Parent agreed after reading both packages. Disagreement was occupancy vs API size. The rubric asked for smallest reuse and one caller door. Occupancy is a graft, not a second shell.

Grafts from candidate-2:

1. Leave-companion-while-mini rewrites resume to dedicated (`MiniHost(resume="dedicated")`). Expand after home must not `_ensure_iris_ide_window`.
2. `parse_view_host` raises on leftover `"panel"`. No `_ui_mode` default that restores the old guess.
3. `clear_left_browser` then `addWidget` onto the IDE stack before `_enter_ide_companion`, so the panel cannot sit under the Theia HWND.

Rejected from C2: second `IdeUnifiedShell`, `reveal_browser_page` as a public split, `_ui_mode` stays `"normal"` during dedicated, weakened 50% ratio check, parallel `_resume_host` field.

Rejected from C1: `parse_view_host(..., docked_default=_ui_mode)` as a restore path. Calling `_apply_iris_ide_unified_layout` from dedicated.

## Data shape

```text
DockedSite = dedicated | ide_internal
PanelHost(site: DockedSite)
MiniHost(resume: DockedSite)
ViewHost = PanelHost | MiniHost

UiMode = normal | ide_hero | ide_companion | dedicated_browser
uses_unified_shell(mode) -> ide_companion | dedicated_browser
left_occupant(mode) -> none | theia | browser
```

`ViewHost` is where the `QWebEngineView` lives. `_ui_mode` is which screen the shell is in. Do not sync them. `snapshot.mini_player` derives from `is_mini` only.

Default session host is `PanelHost(site="dedicated")`.

## Layout

Dedicated enter uses the existing `_unified_shell`. Left Qt child is `BrowserPanel` via `mount_left_browser`. Right is `_companion_page`. DragTab `set_ide_companion_active(True)`. `_iris_ide_unified` stays false. Do not create `IrisIdeWindow`. No new window.

`show_browser_workspace` stays the one public method:

```text
if _ui_mode == "ide_companion": _show_ide_internal_browser()  # cover Theia
else: _show_dedicated_browser()
```

Delete `BrowserWorkspacePage` in the same wave.

## Mini

`MiniPlayer(on=True)` → `as_mini(current)`. `MiniPlayer(on=False)` / expand → `as_docked` using `resume`. Companion exit while mini: `note_view_host(MiniHost(resume="dedicated"))` if already mini, else leave as today.

## Checks (do not weaken)

Dedicated after `show_browser_workspace` from a fresh window:

- `_ui_mode == "dedicated_browser"`
- `_body_stack.currentWidget() is _unified_shell`
- `left_browser() is panel` and visible
- companion mounted
- IDE window None or not visible
- `_iris_ide_unified` is false
- split about 80:20 and user-draggable
- tabs / popup adopt still hold

Companion stub `_ui_mode = "ide_companion"` still calls `show_browser_workspace()` (not a new public method). Stays companion. Same panel. `return_from_browser` still works.

Mini: `is_mini` / `is_docked`, driver id, `view_in_slot`, chat PIP.

## Fill-in contract

Implement against candidate-1 `SKETCH.md` with the grafts above. Types first, then session, then widgets, then delete the page, then rewrite checks. One worker. Do not invent `_browser_shell`.
