# SKETCH. Types, signatures, module map

Bodies are `not implemented` or `# TODO`. This is the contract for fill-in. Usage in DESIGN.md is the spec. If a signature disagrees with that usage, change the signature.

## Types

```python
# iris/browser/types.py. Replace ViewHost = Literal["panel", "mini"]

from dataclasses import dataclass
from typing import Literal, Union

DockedSite = Literal["dedicated", "ide_internal"]

@dataclass(frozen=True)
class PanelHost:
    """QWebEngineView is in BrowserPanel on this screen."""
    site: DockedSite
    kind: Literal["panel"] = "panel"

@dataclass(frozen=True)
class MiniHost:
    """QWebEngineView is in the Qt.Tool mini. resume is the dock to restore."""
    resume: DockedSite
    kind: Literal["mini"] = "mini"

ViewHost = Union[PanelHost, MiniHost]

UiMode = Literal["normal", "ide_hero", "ide_companion", "dedicated_browser"]
# UiMode lives conceptually on MainWindow._ui_mode.
# Export the alias from iris/ui if a helper module is added.
# Do not put Qt types in iris/browser/types.py.


def is_mini(host: ViewHost) -> bool:
    return isinstance(host, MiniHost)


def is_docked(host: ViewHost) -> bool:
    return isinstance(host, PanelHost)


def docked_site(host: ViewHost) -> DockedSite:
    if isinstance(host, MiniHost):
        return host.resume
    return host.site


def as_mini(host: ViewHost) -> MiniHost:
    return MiniHost(resume=docked_site(host))


def as_docked(host: ViewHost) -> PanelHost:
    return PanelHost(site=docked_site(host))


def parse_view_host(raw: object, *, docked_default: DockedSite) -> ViewHost:
    """Boundary only. Accept ViewHost, or leftover strings mini|panel|dedicated|ide_internal."""
    raise NotImplementedError


def uses_unified_shell(mode: str) -> bool:
    return mode in ("ide_companion", "dedicated_browser")


def left_occupant(mode: str) -> Literal["none", "theia", "browser"]:
    if mode == "ide_companion":
        return "theia"
    if mode == "dedicated_browser":
        return "browser"
    return "none"
```

Invariants encoded here.

- Dedicated and IDE-internal cannot be spelled `"panel"`.
- Mini always carries the dock it will restore.
- `_ui_mode == "ide_companion"` cannot mean dedicated. `left_occupant` forbids that read.

Default session host is `PanelHost(site="dedicated")`.

## Session

```python
# iris/browser/session.py

HostApplier = Callable[[ViewHost], None]  # was Callable[[ViewHost], None] on the old literal


class BrowserSession:
    def __init__(self, ...) -> None:
        self._view_host: ViewHost = PanelHost(site="dedicated")
        # ...

    def view_host(self) -> ViewHost:
        raise NotImplementedError

    def note_view_host(self, host: ViewHost) -> None:
        raise NotImplementedError

    def _overlay_host(self, snap: BrowserSnapshot) -> BrowserSnapshot:
        # TODO mini_player = is_mini(self._view_host). No other ViewHost branch.
        raise NotImplementedError

    def _ensure_driver_locked(self) -> Any:
        # TODO re-show surface when driver exists, not visible, and is_docked(self._view_host)
        raise NotImplementedError

    def _apply_host_locked(self, host: ViewHost) -> None:
        # TODO if is_mini both or same PanelHost.site: return
        # TODO else ui_call host_applier(host); self._view_host = host
        raise NotImplementedError

    def _execute_body(self, cmd: BrowserCommand) -> BrowserResult:
        # Open:   _apply_host_locked(as_docked(self._view_host))
        # MiniPlayer on:  _apply_host_locked(as_mini(self._view_host))
        # MiniPlayer off: _apply_host_locked(as_docked(self._view_host))
        # same-host MiniPlayer still returns detail="idempotent"
        raise NotImplementedError
```

Command types are unchanged. `MiniPlayer.on: bool` stays. Restore site is in `ViewHost`, not a new command field.

## Unified shell

```python
# iris/ui/workspaces/ide_companion_page.py

class IdeUnifiedShell(QWidget):
    # existing: mount, apply_ratio, shift_iris_width, ide_host, iris_host,
    #           set_ide_insets, set_split_changed_callback, clear_hosts

    def mount_left_browser(self, panel: QWidget) -> None:
        """addWidget panel into _ide_lay. Show it. Remember as left Qt child.
        Do not create or show IrisIdeWindow. Caller owns HWND policy.
        """
        # TODO if already in _ide_lay: panel.show(); return
        # TODO addWidget(panel); panel.show()
        # TODO set_ide_insets(0, 0, 0, 0)
        raise NotImplementedError

    def left_browser(self) -> QWidget | None:
        raise NotImplementedError

    def clear_left_browser(self) -> None:
        """Drop the left-browser ref only. Caller addWidget-moves the panel."""
        raise NotImplementedError
```

`mount(ide, companion)` stays the Theia path. `ide` remains `None` because Theia is HWND, not a Qt child. Dedicated never passes an `IrisIdeWindow` as `ide`.

## MainWindow

```python
# iris/ui/window/main_window.py

class MainWindow:
    # _ui_mode: UiMode
    # delete self._browser_page and the workspace_stack addWidget for it

    def show_browser_workspace(self):
        """One public entry. Policy: companion covers Theia. Else dedicated shell."""
        if self._ui_mode == "ide_companion":
            return self._show_ide_internal_browser()
        if self._ui_mode == "ide_hero" or getattr(self, "_hero_enter_pending", False):
            self._exit_iris_ide_hero()
        return self._show_dedicated_browser()

    def _show_dedicated_browser(self):
        """Enter IdeUnifiedShell with BrowserPanel on ide_host. No IrisIdeWindow."""
        # TODO ensure_qt_webengine_ready; get shared panel
        # TODO if _ui_mode != "dedicated_browser":
        #          _mount_unified_companion_body()
        #          _unified_shell.mount(None, _companion_page, total_w=work.width())
        #          _body_stack.setCurrentWidget(_unified_shell)
        #          _ui_mode = "dedicated_browser"
        #          _drag.set_ide_companion_active(True)
        #          _iris_ide_unified stays False
        #          do not call _ensure_iris_ide_window
        # TODO _unified_shell.mount_left_browser(panel)
        # TODO panel.ensure_view(); session.note_surface_ready; note_view_host(PanelHost("dedicated"))
        # TODO wire panel.ide_requested -> _on_browser_ide_requested
        # TODO _workspace_mode = "browser"; _set_workspace_icon_active("browser")
        # TODO return panel
        raise NotImplementedError

    def _show_ide_internal_browser(self):
        """Today's _show_browser_in_ide. Cover Theia. Stay ide_companion."""
        # TODO rename body from _show_browser_in_ide; keep behavior
        # TODO session.note_view_host(PanelHost("ide_internal"))
        raise NotImplementedError

    def _exit_dedicated_browser(self) -> None:
        """Leave unified chrome. Do not hide or unembed IrisIdeWindow."""
        # TODO if _ui_mode != "dedicated_browser": return
        # TODO _maybe_detach_browser_to_mini()
        # TODO _unified_shell.clear_left_browser(); clear_hosts
        # TODO remount companion body back to assistant / body_stack index 0
        # TODO _ui_mode = "normal"; _drag.set_ide_companion_active(False)
        raise NotImplementedError

    def _mount_unified_companion_body(self) -> None:
        """Shared remount. Orb, live activity, chat onto _companion_page.
        No HWND. No _iris_ide_unified. No _ui_mode write.
        """
        # TODO lift the remount block from _apply_iris_ide_unified_layout(True)
        raise NotImplementedError

    def apply_browser_view_host(self, host: ViewHost | str) -> None:
        """Single app writer of view parenting."""
        # TODO parsed = host if isinstance(host, (PanelHost, MiniHost)) else parse_view_host(
        #          host, docked_default=_docked_default_for_mode())
        # TODO mini branch: release_view, attach_view, show_in_chat(_chat)
        #          if ide_internal visible: IrisIdeWindow._show_ide_stack_page()
        #          note_view_host(parsed)
        # TODO docked dedicated: detach mini, place_view, _show_dedicated_browser
        # TODO docked ide_internal: detach mini, place_view, _show_ide_internal_browser
        raise NotImplementedError

    def _docked_default_for_mode(self) -> DockedSite:
        return "ide_internal" if self._ui_mode == "ide_companion" else "dedicated"

    def _on_ide_icon(self) -> None:
        # TODO if dedicated_browser: _exit_dedicated_browser(); return
        # TODO existing hero / companion / enter branches unchanged
        raise NotImplementedError

    def _on_browser_ide_requested(self) -> None:
        # companion: return_from_browser, keep Theia. Unchanged.
        # dedicated: _maybe_detach_browser_to_mini then _enter_ide_companion
        raise NotImplementedError

    def _workspace_chat_page(self):
        # TODO email -> _email_page; calendar -> _calendar_page; browser -> None
        raise NotImplementedError

    def _sync_docked_iris_ide_geometry(self) -> None:
        # TODO existing early return already covers dedicated
        #      win is None or not _iris_ide_unified. Keep that. Do not add a new flag.
        raise NotImplementedError
```

Calendar, mail, home, and companion-exit paths that already leave a workspace must call `_exit_dedicated_browser` when `_ui_mode == "dedicated_browser"`. Same pattern as today's `_exit_ide_companion` checks. One helper used by those sites.

```python
def _leave_unified_if_needed(self) -> None:
    if self._ui_mode == "dedicated_browser":
        self._exit_dedicated_browser()
    elif self._ui_mode == "ide_companion":
        self._exit_ide_companion()
```

Do not invent a third exit.

## IrisIdeWindow

```python
# iris/ui/workspaces/iris_ide_window.py

class IrisIdeWindow:
    def reclaim_browser_panel(self):
        # unchanged: addWidget onto _stack if missing
        raise NotImplementedError

    def show_browser(self, *, show_window: bool = True):
        # TODO apply_browser_view_host(PanelHost(site="ide_internal"))
        # TODO show/raise only when show_window and this window is the companion left occupant
        raise NotImplementedError

    def apply_browser_view_host(self, host: ViewHost | str) -> None:
        """IDE-only HostApplier. Docked site is always ide_internal.
        Reject PanelHost(site="dedicated"). That screen does not live here.
        """
        # TODO parsed = parse_view_host(host, docked_default="ide_internal")
        # TODO if isinstance(parsed, PanelHost) and parsed.site != "ide_internal":
        #          raise ValueError("IrisIdeWindow cannot host dedicated")
        # TODO mini / uncover Theia: keep current reparent logic
        raise NotImplementedError

    def is_browser_visible(self) -> bool:
        # unchanged: current stack widget is the panel
        raise NotImplementedError
```

Dedicated enter never calls `_ensure_iris_ide_window`. A leftover hidden window from an earlier companion session stays hidden.

## Control actions

```python
# iris/ui/control_actions/browser.py. Public registration unchanged.

def _surface():
    return window.show_browser_workspace()

def _apply_host(host: ViewHost | str) -> None:
    window.apply_browser_view_host(host)
```

No new `browser.*` name. `iris/system/_check_browser_scenarios.py` catalog asserts stay.

## DragTab

```python
# iris/ui/widgets/drag_tab.py

def set_ide_companion_active(self, active: bool) -> None:
    # unchanged behavior. Dedicated reuses it.
    raise NotImplementedError
```

Do not add `set_unified_chrome`. One method. Dedicated and companion both pass `True` while the shell is up.

## Deleted

```text
iris/ui/workspaces/browser_workspace_page.py
MainWindow._browser_page
_workspace_stack entry for browser
_workspace_chat_page() -> _browser_page
ViewHost = Literal["panel", "mini"]
session._view_host == "panel" / == "mini" string compares
apply_browser_view_host("panel") as a real site
```

Migrate every caller in the same wave. Tests listed below are the remaining `"panel"` readers.

## Module map

```text
iris/browser/types.py
    ViewHost union, parse_view_host, is_mini, is_docked, docked_site, as_mini, as_docked
    UiMode helpers may live here or in iris/ui/workspaces/shell_mode.py if Qt-free split is wanted
    prefer types.py helpers to avoid a one-caller module

iris/browser/session.py
    stores ViewHost, MiniPlayer / Open use as_mini / as_docked
    does not parent widgets

iris/browser/__init__.py
    export PanelHost, MiniHost, is_mini, is_docked  next to ViewHost

iris/ui/workspaces/ide_companion_page.py
    IdeUnifiedShell.mount_left_browser
    IdeCompanionPage unchanged

iris/ui/window/main_window.py
    show_browser_workspace dispatch
    _show_dedicated_browser, _exit_dedicated_browser
    _mount_unified_companion_body
    apply_browser_view_host typed
    _on_ide_icon dedicated branch
    delete _browser_page

iris/ui/workspaces/iris_ide_window.py
    ide_internal only
    reject dedicated PanelHost

iris/ui/browser/panel.py
    unchanged chrome. Address bar already on the panel that fills ide_host.

iris/ui/browser/mini_player.py
    unchanged Qt.Tool, chat anchor

iris/ui/widgets/drag_tab.py
    reuse set_ide_companion_active

iris/ui/control_actions/browser.py
    same _surface / _apply_host, typed host

iris/ui/workspaces/browser_workspace_page.py
    delete

iris/ui/workspaces/_check_browser_workspace.py
    rewrite observables, do not weaken

iris/ui/browser/_check_mini_player.py
    is_mini / is_docked, keep driver id and view_in_slot

iris/system/_check_browser_scenarios.py
    no catalog change
```

## Tests, behavior not internals

`_check_browser_workspace` after `show_browser_workspace` from a fresh MainWindow.

```python
panel = w.show_browser_workspace()
assert w._ui_mode == "dedicated_browser"
assert w._body_stack.currentWidget() is w._unified_shell
assert w._unified_shell.left_browser() is panel
assert panel.isVisible()
assert w._companion_page.is_mounted()
assert w._iris_ide_window is None or not w._iris_ide_window.isVisible()
assert not getattr(w, "_iris_ide_unified", False)
sizes = w._unified_shell._split.sizes()
total = sum(sizes)
assert sizes[0] == int(total * 0.8) or abs(sizes[0] / total - 0.8) < 0.05
# user can still drag
w._unified_shell._split.setSizes([sizes[0] - 80, sizes[1] + 80])
assert w._unified_shell._split.sizes() != sizes
panel.ensure_view()
assert panel.tab_count() >= 1
adopted = panel._adopt_popup()
assert adopted is not None and panel.tab_count() == 2
panel._on_new_tab()
assert panel.tab_count() == 3
```

Companion path. The existing stub `w._ui_mode = "ide_companion"` still reaches `_show_ide_internal_browser` and `_ensure_iris_ide_window`. Keep that.

```python
w._ui_mode = "ide_companion"
ide_panel = w.show_browser_workspace()
assert w._ui_mode == "ide_companion"
assert ide is w._iris_ide_window and ide is not None
assert ide_panel is panel
assert ide.is_browser_visible() or ide._stack.currentWidget() is panel
ide.return_from_browser()
assert not ide.is_browser_visible()
w.show_browser_workspace()
assert ide.is_browser_visible() or ide._stack.currentWidget() is panel
```

Do not assert `_workspace_stack.currentWidget() is w._browser_page`. That page is gone. The contract is left webpage plus right chat plus no Theia for dedicated, and Theia-cover without leaving companion for IDE-internal.

`_check_mini_player` fixture.

```python
assert is_mini(session.view_host())
assert r.snapshot.mini_player is True
# second MiniPlayer(on=True) still detail == "idempotent"
assert is_docked(session.view_host()) and not r.snapshot.mini_player
```

`_check_qt_reparent` still uses `IrisIdeWindow` as `HostApplier`. After `show_browser`, `view_host()` is `PanelHost("ide_internal")`. After leave-watch auto-mini, `is_mini`. After `MiniPlayer(on=False)`, panel is visible on the IDE stack, same driver id.

Chat-pip check still calls `w.show_browser_workspace()`, then `MiniPlayer(on=True)`, then calendar. Mini stays visible, anchored to `w._chat`, clamped. Expand puts the view back in `panel.view_in_slot()`. Dedicated chrome underneath may have exited. That is fine. The observable is the view, not which stack page holds an empty panel.

## Red-flag screen

- Shallow module. Callers still call one method. Dedicated vs internal is inside MainWindow.
- Information leakage. 80:20 stays in `IdeUnifiedShell.apply_ratio`. No second sizes list.
- Temporal decomposition. Enter and exit own chrome plus left occupant together. No separate "hide sidebar" module.
- Pass-through. `show_browser_workspace` adds the mode check. That is policy.
- Split ownership. MainWindow parents the panel for the app. `IrisIdeWindow` parents only its stack. Session stores `ViewHost` only.
- Two ways. `BrowserWorkspacePage` deleted. `"panel"` deleted from the type.
- Importable internals. `mount_left_browser` is not registered on the control surface.
- Hand-synced list. `left_occupant` derives from `_ui_mode`. No parallel `_shell_kind` field.

## Principles that changed a choice

- model-the-domain. Tagged `ViewHost` and `_ui_mode == "dedicated_browser"` instead of another `"panel"` branch.
- foundational-thinking. Types and occupant before widget moves.
- redesign-from-first-principles. Dedicated is a shell occupant, not a calendar clone with a flag.
- laziness-protocol. Reuse `_unified_shell` and DragTab. No third page.
- subtract-before-you-add. Delete `BrowserWorkspacePage` before adding `mount_left_browser`.
- type-system-discipline. `"panel"` cannot name two screens.
- boundary-discipline. String parse only on the two `apply_browser_view_host` methods.
- make-operations-idempotent. Enter, exit, and mini converge.
- encode-lessons-in-structure. The mixup becomes a type, not a comment.
- minimize-reader-load. Three-step call chain. No cloned splitter.
- migrate-callers-then-delete-legacy-apis. Page and `"panel"` leave in one wave.
- experience-first. Same chrome and 80:20 the user already has after folder open.
- separate-before-serializing-shared-state. One panel writer per actor.
- test-behavior-not-implementation. Checks assert occupant, ratio, visibility, driver id.
- exhaust-the-design-space. Fork 1 committed. Fork 2 and 3 rejected in DESIGN.md.
