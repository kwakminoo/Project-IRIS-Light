# Dedicated browser as a third body-stack shell

## Problem

Dedicated browser is a mail/calendar clone on `_workspace_stack` with a `[820, 420]` split and the left sidebar still showing. IRIS IDE after a folder is open is a different tree. `_body_stack` shows `IdeUnifiedShell` (80:20), Theia is an HWND over `ide_host`, chat is `IdeCompanionPage`, DragTab is companion chrome. The user wants the dedicated screen to use that same structure, not a copy painted onto the mail stack.

`show_browser_workspace` is one function for two screens. If `_ui_mode == "ide_companion"` it covers Theia on `IrisIdeWindow._stack`. Otherwise it shows `BrowserWorkspacePage`. `ViewHost` is only `"panel" | "mini"`, so dedicated and IDE-internal are the same token. Mini restore always asks for `"panel"` and then guesses from `_ui_mode`. That is the mixup.

Constraints from HEAD that this sketch must keep. One shared `BrowserPanel` / `QWebEngineView`. Mini-player stays a chat-anchored `Qt.Tool`. Chat remounts with `addWidget` only. `setParent(None)` stays forbidden. IDE-internal cover of Theia stays a separate feature. No new `QMainWindow`. `_check_browser_workspace` and `_check_mini_player` stay expressible, tests update, contracts do not weaken.

## Usage (caller's view)

Callers never pass `"panel"`. They name the host. MainWindow never asks session to infer the screen.

**Dedicated screen (home / mail / calendar / wiki, companion not up).**

```python
panel = window.show_browser_workspace()
assert window._ui_mode == "normal"
assert window.dedicated_browser_active()
assert window._body_stack.currentWidget() is window._browser_shell
assert window._browser_shell.ide_host().findChild(BrowserPanel) is panel
assert window._companion_page.is_mounted()
assert window._iris_ide_window is None or not window._iris_ide_window.isVisible()
assert window._drag  # same MainWindow chrome, companion-style </> to leave
```

**IDE-internal cover (folder already open).**

```python
panel = window.show_ide_internal_browser()
assert window._ui_mode == "ide_companion"
assert not window.dedicated_browser_active()
assert window._body_stack.currentWidget() is window._unified_shell
assert ide.is_browser_visible()
assert window._iris_ide_unified
```

**Open / icon / `browser.*` (the one policy branch).**

```python
session.set_surface_provider(window.reveal_browser_page)
# reveal_browser_page:
#   companion → show_ide_internal_browser
#   else      → show_browser_workspace
session.execute(Open())
```

**Mini restore remembers which full host it left.**

```python
session.execute(MiniPlayer(on=True))
assert session.view_host() is ViewHost.MINI
assert session.resume_host() in (ViewHost.DEDICATED, ViewHost.IDE_INTERNAL)
session.execute(MiniPlayer(on=False))  # applies resume_host, never "panel"
```

Leaving companion while mini is up rewrites resume to `DEDICATED`, so expand does not reopen Theia cover after the user already went home.

## Shape

**ViewHost is a three-way enum, not `"panel"|"mini"`.** `DEDICATED`, `IDE_INTERNAL`, `MINI`. Session stores `_view_host` and `_resume_host`. `_resume_host` is always a full host. `note_view_host` is the only mutator. A non-mini note also writes resume. Mini does not. That is the domain model (principle-model-the-domain, principle-type-system-discipline). `"panel"` is deleted in the same wave (principle-migrate-callers-then-delete-legacy-apis).

**Screen and placement are different facts.** `_ui_mode` stays `"normal" | "ide_hero" | "ide_companion"`. Dedicated is not a fourth `_ui_mode`. It is `_body_stack.currentWidget() is self._browser_shell`, exposed as `dedicated_browser_active()`. No boolean to keep in sync (principle-encode-lessons-in-structure). Mini can sit on calendar while resume is `DEDICATED`. That already exists. Encoding it stops expand from guessing.

**Fork 3, committed.** `_body_stack` gains a third live page, `_browser_shell = IdeUnifiedShell()`, objectName `DedicatedBrowserShell`. It is not `_unified_shell`. Left child is `BrowserPanel` via `shell.mount(panel, companion, total_w=...)`. Right child is the same `_companion_page` the IDE uses. DragTab uses `set_ide_companion_active(True)` so `</>` means leave this 80:20 body. Address bar stays on `BrowserPanel` in the left pane. No new window.

`_unified_shell` stays IDE-only. Its split callback stays HWND sync. Dedicated never registers that callback, so splitter drags cannot move Theia (principle-separate-before-serializing-shared-state). Theia is not in this tree. Dedicated cannot hide it.

**Two show functions, one reveal.** `show_browser_workspace` is dedicated only. It does not read `_ui_mode` to pick a screen. `show_ide_internal_browser` is Theia cover only. It requires `_ui_mode == "ide_companion"` (the existing check fakes that flag). `reveal_browser_page` is the policy at the window boundary. Session, icons, and `browser.open` call reveal. That is the only companion-vs-dedicated branch (principle-boundary-discipline).

**Enter path reuses IDE chrome, not IDE flags.** Dedicated enter copies the window work-area / zero-margin / companion-mount sequence that `_apply_iris_ide_unified_layout(True)` already does, targeting `_browser_shell` and `left=panel`. It does not set `_ui_mode = "ide_companion"` or `_iris_ide_unified`. `_on_ide_icon` checks `dedicated_browser_active()` before the companion branch and leaves dedicated to the main splitter. Home, mail, calendar, wiki all call `_ensure_normal_body()` so they are safe if the last screen was dedicated (principle-make-operations-idempotent).

**Chat.** One `ChatPanel`. Dedicated and IDE share `_companion_page`. Mail/calendar keep `_workspace_chat`. Going dedicated while `_workspace_chat` is mounted transfers through the existing assistant restore, then mounts `_companion_page` on `_browser_shell`. `addWidget` only.

**Mini and the view.** Unchanged mechanics. `apply_browser_view_host` becomes a match on `ViewHost`. `MINI` detaches the view into the tool window. `DEDICATED` calls `show_browser_workspace`. `IDE_INTERNAL` calls `show_ide_internal_browser`. Expand buttons pass `session.resume_host()`, not `"panel"`. `IrisIdeWindow.apply_browser_view_host` accepts `MINI` and `IDE_INTERNAL` only. It never takes `DEDICATED`.

**Delete `BrowserWorkspacePage`.** It is the mail-clone. Dedicated is no longer a `_workspace_stack` page. `_workspace_chat_page()` drops the browser branch. One 80:20 policy lives in `IdeUnifiedShell` (principle-subtract-before-you-add, no hand-synced splitter sizes).

**Interface depth.** Public window API is three names (`reveal_browser_page`, `show_browser_workspace`, `show_ide_internal_browser`) plus `apply_browser_view_host(ViewHost)` and `dedicated_browser_active()`. Callers do not place the panel, remount chat, or know `_body_stack` indexes. Session still does not import Qt. `parse_view_host` sits at the str/Qt-signal boundary.

**Idempotent transitions.** Show dedicated twice. Same shell current, same panel parent, same chat mount, no second `IrisIdeWindow`. Show ide-internal twice. Panel on `_stack`, companion flags unchanged. Mini on/off with the same target stays `detail="idempotent"` as today.

**Call chain.** `browser.open` → `BrowserSession.execute` → `reveal_browser_page` → one show method. Three files. No fourth coordinator.

What this sketch refuses. Reusing `_unified_shell` for dedicated (fork 1). Cloning 80:20 onto `_workspace_stack` (fork 2). A ViewHost rename with the same `show_browser_workspace` body. Putting `BrowserPanel` above Theia on the dedicated screen. A second `QMainWindow`.

## Synthesis decision

Candidate only. Arena fills this after comparing packages.

## Tradeoffs accepted

- We accept a second `IdeUnifiedShell` instance in exchange for HWND sync and `_iris_ide_unified` never touching the dedicated screen.
- We accept companion DragTab chrome on dedicated (`</>` leave, status column hidden) in exchange for matching IDE-after-folder-open, including how home is reached. Workspace icons stay in the left sidebar, which is not visible until leave. That is already true of IDE.
- We accept sharing `_companion_page` between dedicated and IDE in exchange for one chat-column widget. Mail/calendar keep the extra `_workspace_chat` host they already have.
- We accept deleting `BrowserWorkspacePage` in the same change, with planned test edits, rather than leaving a dead mail-clone page (principle-outcome-oriented-execution).
- We accept that `show_ide_internal_browser` still works when tests only set `_ui_mode = "ide_companion"` without a full tile. Production always has the unified shell current. The function still must not run from `_ui_mode == "normal"`.

## Alternatives considered

- **Dedicated as a mode of the existing `IdeUnifiedShell` (fork 1).** Smaller widget count. It exposes occupancy (`left is HWND vs BrowserPanel`) and `_ui_mode` to every IDE enter/exit path. An agent copying `_apply_iris_ide_unified_layout` would set `_ui_mode = "ide_companion"` and the next `reveal` would cover Theia, or leave BrowserPanel sitting on `ide_host` under the HWND. Public interface looks smaller. The hidden rule is larger. Rejected.
- **Rebuild `BrowserWorkspacePage` on `_workspace_stack` as an 80:20 clone and hide the sidebar (fork 2).** Keeps browser next to mail in the stack. It is a second splitter (`_UNIFIED_IDE_RATIO` copied by hand) still parented by `_main_splitter`, which is not the IDE tree. Callers keep learning two 80:20 widgets. Rejected.
- **Keep `ViewHost = "panel"|"mini"` and branch only in MainWindow.** Session still cannot say which full host mini should restore. The mixup stays in the type. Rejected.
- **Right column as `_workspace_chat` (mail-like) instead of `_companion_page`.** Two chat hosts for two 80:20 screens. Extra remount. No extra capability. Rejected.

## Open questions and risks

- Should dedicated hide the DragTab status column the way IDE companion does, or keep status visible and still use `</>` to leave? This sketch matches IDE. Reversing it is a chrome flag on `_enter_unified_body`, not a new tree.
- `_body_stack` already parks `_companion_page` as page 1 for the legacy non-unified companion path. Dedicated mount steals that widget via `addWidget`. Is that legacy path still reachable in production, or only a parking slot? If it still shows, dedicated enter must not race it.
- Fake `_ui_mode = "ide_companion"` in `_check_browser_workspace` never tiles. If `show_ide_internal_browser` later requires `_iris_ide_unified`, that check needs a real companion enter. Should the check stay cheap?

## Next implementation step

Add `ViewHost` enum plus `resume_host` on `BrowserSession`, then construct `_browser_shell` on `_body_stack` and point `show_browser_workspace` at it with tests updated to the new observables.
