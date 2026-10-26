# DESIGN. Dedicated browser is a left occupant of IdeUnifiedShell

## Problem

The user wants the dedicated browser screen to match IRIS IDE after a folder is open. Left region fills with the webpage. Right column is the same Iris chat. Top DragTab stays so home and the other screens remain reachable. Address bar stays on the browser chrome in that left region. No new window.

HEAD does something else. After a folder is open, MainWindow shows `_unified_shell` on `_body_stack`. Left is a Theia HWND over `ide_host`. Right is `IdeCompanionPage`. Dedicated browser is `BrowserWorkspacePage` on `_workspace_stack`, sizes `[820, 420]`, left sidebar still up. `show_browser_workspace` is one function for two screens. If `_ui_mode == "ide_companion"` it covers Theia on `IrisIdeWindow._stack`. Otherwise it shows the mail-style page.

`ViewHost` is `Literal["panel", "mini"]`. Dedicated and IDE-internal are both `"panel"`. That is the mixup. A later edit that treats `"panel"` as one place will send the shared `BrowserPanel` to the wrong screen.

Constraints from HEAD that stay. One `BrowserSession`. One `BrowserPanel` / `QWebEngineView`. Mini is a chat-anchored `Qt.Tool`. Chat remounts with `addWidget` only. `setParent(None)` is forbidden. IDE-internal browser stays a stack page on `IrisIdeWindow`. Command bus stays. `_check_browser_workspace` and `_check_mini_player` keep their observable contracts.

## Usage (caller's view)

Callers do not pick a layout widget. They ask for a full-size browser or they toggle mini. MainWindow decides the screen from `_ui_mode`.

**Open from chat or `browser.open` while the user is on home.**

```python
# iris/ui/control_actions/browser.py, unchanged call
panel = window.show_browser_workspace()
# _ui_mode == "dedicated_browser"
# _body_stack.currentWidget() is _unified_shell
# BrowserPanel is a Qt child of _unified_shell.ide_host()
# IdeCompanionPage on the right holds the same ChatPanel
# _iris_ide_window is None, or created later and still hidden
# DragTab.set_ide_companion_active(True) so the IDE button returns home
# left sidebar is gone because body_stack left the main splitter
```

**Open a page while companion is already up.**

```python
# same public method, different occupant
window._ui_mode == "ide_companion"
panel = window.show_browser_workspace()
# still ide_companion, Theia HWND still the left occupant
# panel is current on IrisIdeWindow._stack, covering Theia
# companion chat does not remount
# this is not dedicated_browser
```

**Mini, then restore.**

```python
session.execute(MiniPlayer(on=True))   # ViewHost becomes MiniHost(resume=<current dock>)
session.execute(MiniPlayer(on=False))  # ViewHost becomes PanelHost(site=resume)
# MainWindow.apply_browser_view_host places the same QWebEngineView
# resume dedicated -> left of unified shell
# resume ide_internal -> IrisIdeWindow._stack
# driver id does not change
```

**IDE button and other DragTab icons.**

```python
# dedicated_browser + DragTab IDE button
window._on_ide_icon()
# exits dedicated chrome, remounts chat to assistant, does not create Theia

# dedicated_browser + calendar icon
window._on_calendar_icon()
# same exit, then calendar page. YouTube watch URL still goes to mini.

# dedicated_browser + BrowserPanel IDE button
window._on_browser_ide_requested()
# may detach media to mini, then enter real companion with Theia
```

`browser.*` commands stay the same. No new control action. `HostApplier` now takes a `ViewHost` value, not the string `"panel"`.

## Shape

Dedicated browser is a mode of the existing `IdeUnifiedShell`. It is not a clone of that shell and not a third `_body_stack` page. Left host shows `BrowserPanel` as a Qt child. Right column is the same `IdeCompanionPage`. `show_browser_workspace` in normal or hero-exited mode enters this shell without `IrisIdeWindow`.

This is fork 1. The data shape makes the other forks unrepresentable.

**Core types.** Per model-the-domain and type-system-discipline.

`ViewHost` stops being `"panel" | "mini"`. It becomes a tagged pair.

```text
DockedSite = dedicated | ide_internal
PanelHost(site: DockedSite)
MiniHost(resume: DockedSite)
ViewHost = PanelHost | MiniHost
```

`"panel"` is not a member. `parse_view_host` at the widget boundary is the only place a leftover string is accepted. MainWindow parses with default site from `_ui_mode`. `IrisIdeWindow` parses with default `ide_internal` and rejects `PanelHost(dedicated)`.

`_ui_mode` gains `"dedicated_browser"`. It is the single source of truth for which left occupant the shell has.

```text
normal | ide_hero | ide_companion | dedicated_browser

uses_unified_shell(mode) -> ide_companion | dedicated_browser
left_occupant(mode) -> none | theia | browser
```

`ViewHost` answers where the `QWebEngineView` lives. `_ui_mode` answers which screen the shell is in. They can differ. Mini over dedicated is `MiniHost(resume=dedicated)` plus `_ui_mode == "dedicated_browser"`. Do not sync them. `snapshot.mini_player` derives from `is_mini(view_host)` only.

**Left occupant.** `IdeUnifiedShell` already has `mount(ide, companion)` for Theia as HWND placeholder, `ide=None`. Add `mount_left_browser(panel)` that `addWidget`s `BrowserPanel` into `_ide_lay`. Insets go to 0 so the page fills the left region. Theia insets stay on the Theia path. Split callback `_sync_docked_iris_ide_geometry` already returns when there is no visible IDE window. Dedicated never sets `_iris_ide_unified`.

**Entry split is policy, not a second layout.** `show_browser_workspace` stays the one public method. It dispatches.

```text
if _ui_mode == "ide_companion": show_ide_internal_browser()
else: show_dedicated_browser()
```

`show_dedicated_browser` mounts unified chrome, places the panel on `ide_host`, sets `_ui_mode = "dedicated_browser"`, and does not call `_ensure_iris_ide_window`. `show_ide_internal_browser` is today's `_show_browser_in_ide`. Cover Theia. Do not leave companion.

That dispatch is the only place those two screens meet. Per encode-lessons-in-structure, a later agent that opens `show_browser_workspace` cannot treat them as one `"panel"`.

**Chrome reuse.** Dedicated enter remounts orb, live activity, and chat onto the existing `_companion_page`, then `_unified_shell.mount(None, companion)` plus `mount_left_browser`. DragTab keeps `set_ide_companion_active(True)`. The IDE button already means "return to normal layout". `_on_ide_icon` gains a `dedicated_browser` branch that exits dedicated and does not enter companion.

Extract the remount that `_apply_iris_ide_unified_layout(True)` already does into `_mount_unified_companion_body`. Companion enter and dedicated enter both call it. Do not call the Theia layout function from dedicated. That function sets `_iris_ide_unified` and assumes a docked HWND.

**Delete `BrowserWorkspacePage`.** Per subtract-before-you-add and migrate-callers-then-delete-legacy-apis. Remove it from `_workspace_stack` in the same wave. `_workspace_chat_page` no longer returns a browser page. Dedicated chat lives on `IdeCompanionPage`. Mail and calendar keep `WorkspaceIrisPanel`.

**Placement ownership.** Per separate-before-serializing-shared-state. MainWindow is the only writer of panel parenting for the running app. `IrisIdeWindow` writes only its own stack, Theia vs cover. Session writes `ViewHost` and never parents widgets. Mini attach and detach stay on MainWindow for the app, and on `IrisIdeWindow.apply_browser_view_host` for the existing IDE-only check.

**Idempotent transitions.** Per make-operations-idempotent.

- Dedicated enter while already dedicated. Place the panel if it left `ide_host`. Return the same panel.
- IDE-internal enter while already covering. Reclaim if needed. Stay companion.
- `MiniPlayer` to the host already in effect. Keep today's `"idempotent"` detail.
- Exit dedicated twice. Second call sees `_ui_mode != "dedicated_browser"` and returns.
- Crash halfway through remount. The next enter reads current parents and `addWidget`s. It does not assume the previous enter finished.

**Call chain.** Per laziness-protocol and minimize-reader-load.

1. `control_actions.browser` → `MainWindow.show_browser_workspace`
2. dispatch → `show_dedicated_browser` or `show_ide_internal_browser`
3. dedicated → `IdeUnifiedShell.mount_left_browser` + companion remount. Internal → `IrisIdeWindow.reclaim_browser_panel` + `show_browser`

A reader does not walk a third body page or a cloned splitter.

**Public methods stay small.** Callers keep `show_browser_workspace` and `apply_browser_view_host`. They do not see left insets, HWND sync, or stack indexes. `mount_left_browser` is on `IdeUnifiedShell` only. Control actions do not import it.

**Validation lives at the widget boundary.** `parse_view_host` and `_ui_mode` checks sit on MainWindow and `IrisIdeWindow`. Session constructs `PanelHost` / `MiniHost` from the host it already holds. `Open` applies `as_docked(current)`. `MiniPlayer` applies `as_mini` or `as_docked` using `resume`. Inside session, trust the type. Per boundary-discipline.

**Deliberately not done.** No new `QMainWindow`. No Theia under a dedicated cover. No command-bus rewrite. No second `IdeUnifiedShell` instance. No `_ui_mode == "ide_companion"` reuse for dedicated. That reuse would send the next `show_browser_workspace` into `_show_browser_in_ide` and create Theia.

## Synthesis decision

This file is candidate-1, not the arena synthesis. The committed fork is 1. Dedicated browser is a mode of the existing `IdeUnifiedShell`.

## Tradeoffs accepted

- We accept a fourth `_ui_mode` value in exchange for never letting dedicated share `ide_companion`. Many `== "ide_companion"` sites stay Theia-only. Sites that mean "unified chrome is up" switch to `uses_unified_shell`.
- We accept extracting `_mount_unified_companion_body` from `_apply_iris_ide_unified_layout` in exchange for not inventing a new chrome widget.
- We accept deleting `BrowserWorkspacePage` and rewriting `_check_browser_workspace` observables in exchange for one layout. The new asserts are stronger. 80:20 on the real shell, no visible `IrisIdeWindow`, companion chat mounted.
- We accept `IrisIdeWindow` rejecting `PanelHost(dedicated)` in exchange for keeping the IDE-only mini check expressible without a hidden coerce back to `"panel"`.
- We accept DragTab's `set_ide_companion_active` name staying for this change. The method already hides the status column and shows the return button. A rename is a later sweep, not this design.

## Alternatives considered

**Fork 2. Keep `BrowserWorkspacePage` and rebuild it as an `IdeUnifiedShell` clone.** Rejected. Two 80:20 splitters and two chat remount paths. An agent copies whichever page it opens first. Callers would learn two layout objects to do one job. The clone hides nothing the real shell does not already hide.

**Fork 3. Add a third `_body_stack` page that is another unified layout without `IrisIdeWindow`.** Rejected. `_unified_shell` is already that page. A second instance splits ownership of ratio, insets, and companion mount. Enter and exit grow a third index to keep in sync with `_ui_mode`.

**ViewHost bookkeeping only, leave `BrowserWorkspacePage`.** Rejected by the brief and by the red flags. A three-way literal on a mail-style page still shows the wrong layout. Types would name a screen the widgets do not implement.

**Hide Theia and show `BrowserPanel` on the same `IrisIdeWindow` stack for dedicated.** Rejected. That is the IDE-internal feature. Dedicated would create or show Theia and then cover it. Folder-open state and HWND sync would leak into a screen that has no IDE.

**New `QMainWindow` for the browser.** Rejected. The user stays in Iris. DragTab and chat remount already exist on MainWindow.

## Open questions and risks

- Should `_on_ide_icon` from dedicated always return home, or should a second click after return open companion? The current IDE icon from normal already enters companion. Dedicated exit first keeps that.
- `_apply_iris_ide_unified_layout` has many companion side effects. The extract has to stop before HWND and `_iris_ide_unified`. If the extract takes too much, dedicated enter should copy the remount lines instead of sharing a helper that still knows about Theia.
- MCP `ui_mode` docs say `normal|ide_companion`. Adding `dedicated_browser` changes what `control_actions.session` reports. Does any external client switch on the old pair only?

## Next implementation step

Add `PanelHost` / `MiniHost` / helpers in `iris/browser/types.py` and migrate `BrowserSession` plus the two `_check_mini_player` fixture asserts so `"panel"` is gone before any widget moves.
