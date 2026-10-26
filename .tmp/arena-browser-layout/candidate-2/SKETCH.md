# Sketch. Dedicated browser shell (fork 3)

Bodies are `not implemented` or `# TODO`. Types and signatures are the contract.

## Types

```python
# iris/browser/types.py  (replace ViewHost = Literal["panel", "mini"])

from enum import Enum
from typing import Literal


class ViewHost(str, Enum):
    DEDICATED = "dedicated"
    IDE_INTERNAL = "ide_internal"
    MINI = "mini"

    def is_full(self) -> bool:
        return self is not ViewHost.MINI


FullViewHost = Literal[ViewHost.DEDICATED, ViewHost.IDE_INTERNAL]


def parse_view_host(raw: object) -> ViewHost:
    """Boundary. Wire/Qt-signal strings become ViewHost. No 'panel' alias."""
    if isinstance(raw, ViewHost):
        return raw
    if raw == ViewHost.DEDICATED.value:
        return ViewHost.DEDICATED
    if raw == ViewHost.IDE_INTERNAL.value:
        return ViewHost.IDE_INTERNAL
    if raw == ViewHost.MINI.value:
        return ViewHost.MINI
    raise ValueError(f"unknown view host: {raw!r}")


def full_host_for_screen(*, companion_active: bool) -> ViewHost:
    """Pure. Companion up → cover Theia. Else dedicated screen."""
    if companion_active:
        return ViewHost.IDE_INTERNAL
    return ViewHost.DEDICATED
```

`BrowserSnapshot.mini_player` stays a derived bool (`view_host is MINI`). Do not add a second host field on the snapshot. Session is the source of truth.

Delete `Literal["panel", "mini"]`. Grep must find zero `"panel"` view-host writes after the change.

## Session

```python
# iris/browser/session.py

HostApplier = Callable[[ViewHost], None]


class BrowserSession:
    def __init__(self, ...):
        self._view_host: ViewHost = ViewHost.DEDICATED
        self._resume_host: ViewHost = ViewHost.DEDICATED  # never MINI
        # ... existing fields

    def view_host(self) -> ViewHost:
        ...

    def resume_host(self) -> ViewHost:
        """Last full host. Mini expand applies this."""
        raise NotImplementedError

    def note_view_host(self, host: ViewHost) -> None:
        """Only mutator for _view_host. Non-mini also writes _resume_host."""
        raise NotImplementedError

    def note_resume_host(self, host: ViewHost) -> None:
        """Leave-companion-while-mini. host must be full."""
        raise NotImplementedError

    def _overlay_host(self, snap: BrowserSnapshot) -> BrowserSnapshot:
        # TODO: mini_player = self._view_host is ViewHost.MINI  (same as today)
        raise NotImplementedError

    def _ensure_driver_locked(self) -> Any:
        # TODO: on first create, do NOT force view_host to a fake "panel".
        # surface_provider shows the screen and notes the real host.
        # if already have driver, view_host is full, and not visible: show surface.
        raise NotImplementedError

    def _apply_host_locked(self, host: ViewHost) -> None:
        if self._view_host == host:
            return
        if self._host_applier is not None:
            self._ui_call(lambda h=host: self._host_applier(h))
        self.note_view_host(host)

    def _execute_body(self, cmd: BrowserCommand) -> BrowserResult:
        if isinstance(cmd, Open):
            # TODO: _ensure_driver_locked(); if view_host is MINI, apply resume_host
            raise NotImplementedError
        if isinstance(cmd, MiniPlayer):
            # TODO: target = MINI if cmd.on else self._resume_host
            # existing idempotent detail when already there
            raise NotImplementedError
        raise NotImplementedError
```

## Window signatures

```python
# iris/ui/window/main_window.py  (methods only; no production edit in this sketch)


class MainWindow:
    def __init__(...):
        self._unified_shell = IdeUnifiedShell()
        self._unified_shell.set_split_changed_callback(self._sync_docked_iris_ide_geometry)
        self._browser_shell = IdeUnifiedShell()
        self._browser_shell.setObjectName("DedicatedBrowserShell")
        # no HWND callback on _browser_shell
        self._body_stack.addWidget(self._main_splitter)
        self._body_stack.addWidget(self._companion_page)
        self._body_stack.addWidget(self._unified_shell)
        self._body_stack.addWidget(self._browser_shell)
        # DELETE: self._browser_page = BrowserWorkspacePage()
        # DELETE: self._workspace_stack.addWidget(self._browser_page)

    def dedicated_browser_active(self) -> bool:
        return self._body_stack.currentWidget() is self._browser_shell

    def reveal_browser_page(self):
        """Policy boundary. The only companion-vs-dedicated branch."""
        if self._ui_mode == "ide_companion":
            return self.show_ide_internal_browser()
        return self.show_browser_workspace()

    def show_browser_workspace(self):
        """Dedicated 80:20 shell. Does not read _ui_mode to pick a screen."""
        raise NotImplementedError

    def show_ide_internal_browser(self):
        """Cover Theia on IrisIdeWindow._stack. Requires _ui_mode == ide_companion."""
        raise NotImplementedError

    def apply_browser_view_host(self, host: object) -> None:
        raise NotImplementedError

    def _enter_unified_body(self, shell: IdeUnifiedShell, left: QWidget | None) -> None:
        """Shared mount. Chat onto _companion_page, shell.mount, body_stack current=shell."""
        raise NotImplementedError

    def _leave_dedicated_browser(self) -> None:
        raise NotImplementedError

    def _ensure_normal_body(self) -> None:
        """Idempotent. If dedicated shell is current, leave it. Companion is a different _ui_mode."""
        raise NotImplementedError
```

### `show_browser_workspace` body

```python
def show_browser_workspace(self):
    if self._ui_mode == "ide_hero" or getattr(self, "_hero_enter_pending", False):
        self._exit_iris_ide_hero()
    # TODO: if already dedicated_browser_active and panel in left host:
    #   panel.ensure_view(); note DEDICATED; return panel  (idempotent)

    from iris.browser.session import get_browser_session
    from iris.ui.browser.panel import get_shared_browser_panel
    from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

    ensure_qt_webengine_ready()
    session = get_browser_session()
    panel = get_shared_browser_panel(session)
    panel.ensure_view()
    # TODO: bind panel.ide_requested → _on_browser_ide_requested (disconnect first)
    # TODO: _enter_unified_body(self._browser_shell, panel)
    # TODO: _workspace_mode = "browser"
    # TODO: _drag.set_ide_companion_active(True)
    # TODO: _set_workspace_icon_active("browser")
    # TODO: do NOT set _ui_mode or _iris_ide_unified
    # TODO: do NOT create or show IrisIdeWindow
    session.note_surface_ready(panel.view())
    session.note_view_host(ViewHost.DEDICATED)
    return panel
```

### `show_ide_internal_browser` body

```python
def show_ide_internal_browser(self):
    if self._ui_mode != "ide_companion":
        raise RuntimeError("ide-internal browser requires ide_companion")
    # existing _show_browser_in_ide:
    ide = self._ensure_iris_ide_window()
    panel = ide.reclaim_browser_panel()
    panel.ensure_view()
    # TODO: bind ide_requested
    ide.show_browser(show_window=True)
    self._workspace_mode = "browser"
    self._set_workspace_icon_active("browser")
    get_browser_session().note_view_host(ViewHost.IDE_INTERNAL)
    return panel
```

### `apply_browser_view_host` body

```python
def apply_browser_view_host(self, host: object) -> None:
    target = parse_view_host(host)
    session = get_browser_session()
    panel = get_shared_browser_panel(session)
    view = panel.ensure_view()
    if target is ViewHost.MINI:
        # TODO: existing mini attach (release_view, attach_view, show_in_chat)
        # TODO: if ide.is_browser_visible(): ide._show_ide_stack_page()
        session.note_view_host(ViewHost.MINI)
        return
    # restore view into panel slot (existing detach from mini)
    if target is ViewHost.DEDICATED:
        self.show_browser_workspace()
        return
    if target is ViewHost.IDE_INTERNAL:
        self.show_ide_internal_browser()
        return
```

### Shared enter / leave

```python
def _enter_unified_body(self, shell: IdeUnifiedShell, left: QWidget | None) -> None:
    # TODO: save geometry / main_splitter sizes on first leave of main splitter
    #       (same snapshot fields companion already uses, if not already saved)
    # TODO: work = work_area_for(self); setMinimumSize(960, 640); root margins 0
    # TODO: _release_workspace_chat_to_assistant(restore_viz=False)
    # TODO: _companion_page.mount(orb_spacer, live_activity, chat, ...)
    # TODO: shell.mount(left, self._companion_page, total_w=work.width())
    # TODO: self._body_stack.setCurrentWidget(shell)
    # TODO: _embed_viz_in_companion_slot()
    # TODO: _drag.set_ide_companion_active(True)
    raise NotImplementedError


def _leave_dedicated_browser(self) -> None:
    if not self.dedicated_browser_active():
        return
    self._maybe_detach_browser_to_mini()
    # TODO: _browser_shell.clear_hosts(); park _companion_page on _body_stack if needed
    # TODO: _unmount_companion_body()  (viz back, chat toward assistant)
    # TODO: _body_stack.setCurrentWidget(self._main_splitter)
    # TODO: restore margins / geometry like unified deactivate, without touching
    #       _iris_ide_window or _ui_mode (already normal)
    self._drag.set_ide_companion_active(False)
    self._workspace_mode = "assistant"
    raise NotImplementedError


def _ensure_normal_body(self) -> None:
    if self.dedicated_browser_active():
        self._leave_dedicated_browser()


def _on_ide_icon(self) -> None:
    if self.dedicated_browser_active():
        self._leave_dedicated_browser()
        return
    # existing hero / companion / enter branches
    raise NotImplementedError
```

Home, mail, calendar, wiki, obsidian handlers start with `_maybe_detach_browser_to_mini()` then `_ensure_normal_body()`, then the existing `_workspace_stack` switch.

Companion exit, while mini, calls `session.note_resume_host(ViewHost.DEDICATED)` so expand does not cover Theia after the user left IDE.

### Mini expand wiring

```python
# MainWindow.ensure_browser_mini
mini.expand_requested.connect(
    lambda: self.apply_browser_view_host(get_browser_session().resume_host())
)

# IrisIdeWindow.ensure_browser_mini
mini.expand_requested.connect(
    lambda: self.apply_browser_view_host(ViewHost.IDE_INTERNAL)
)
```

## IrisIdeWindow

```python
# iris/ui/workspaces/iris_ide_window.py

def apply_browser_view_host(self, host: object) -> None:
    target = parse_view_host(host)
    if target is ViewHost.DEDICATED:
        raise ValueError("IrisIdeWindow cannot host dedicated placement")
    if target is ViewHost.MINI:
        # existing mini path; note MINI
        raise NotImplementedError
    # IDE_INTERNAL: restore view into panel, setCurrentWidget(panel), note IDE_INTERNAL
    raise NotImplementedError
```

`show_browser` / `reclaim_browser_panel` stay. They only cover `_stack`. They never look at MainWindow.

## Control surface

```python
# iris/ui/control_actions/browser.py

def _surface():
    return window.reveal_browser_page()

def _apply_host(host) -> None:
    window.apply_browser_view_host(parse_view_host(host))
```

`BrowserHost` protocol adds `show_ide_internal_browser` and `reveal_browser_page`. Keeps `show_browser_workspace` and `apply_browser_view_host`.

## Module map

| Module | Owns | Does not own |
|---|---|---|
| `iris/browser/types.py` | `ViewHost`, `parse_view_host`, `full_host_for_screen` | Qt widgets, `_ui_mode` |
| `iris/browser/session.py` | `_view_host`, `_resume_host`, command apply | which `_body_stack` page is current |
| `iris/ui/window/main_window.py` | `_browser_shell`, reveal/show/leave, chat remount | driver, URL, mini geometry |
| `iris/ui/workspaces/ide_companion_page.py` | `IdeUnifiedShell`, `IdeCompanionPage` | browser placement |
| `iris/ui/workspaces/iris_ide_window.py` | Theia `_stack` cover | dedicated screen |
| `iris/ui/browser/panel.py` | address bar, tabs, `QWebEngineView` slot | which shell parents it |
| `iris/ui/browser/mini_player.py` | tool window + view attach | resume host |
| `iris/ui/control_actions/browser.py` | wire `browser.*` to session | layout |
| `iris/ui/workspaces/browser_workspace_page.py` | **delete** | — |
| `iris/ui/workspaces/workspace_iris_chat.py` | mail/calendar chat host | dedicated |

Call chain ceiling. `browser.open` → `session.execute` → `reveal_browser_page` → `show_*`. `MiniPlayer` → `apply_browser_view_host` → `show_*`. No extra coordinator module.

## Invariants (encoded, not commented)

1. `resume_host.is_full()` always. `note_resume_host(MINI)` raises.
2. `dedicated_browser_active()` xor `_ui_mode == "ide_companion"` xor neither. Never both shells current.
3. `_iris_ide_unified` is true only when `_body_stack` current is `_unified_shell`.
4. `_browser_shell` has no HWND split callback.
5. `BrowserPanel` has one Qt parent at a time. `addWidget` moves it. `setParent(None)` forbidden.
6. `show_browser_workspace` does not call `_ensure_iris_ide_window`.
7. `IrisIdeWindow.apply_browser_view_host(DEDICATED)` raises.

## Tests (behavior, same contracts, new observables)

`iris/ui/workspaces/_check_browser_workspace.py`

```python
panel = w.show_browser_workspace()
assert w._workspace_mode == "browser"
assert w.dedicated_browser_active()
assert w._ui_mode == "normal"
assert w._body_stack.currentWidget() is w._browser_shell
assert w._companion_page.is_mounted()
assert w._iris_ide_window is None or not w._iris_ide_window.isVisible()
sizes = w._browser_shell._split.sizes()
total = sum(sizes)
assert sizes[0] >= int(total * 0.5) and sizes[1] >= 160
# user can drag the handle
w._browser_shell._split.setSizes([sizes[0] - 80, sizes[1] + 80])
assert w._browser_shell._split.sizes() != sizes
# tabs / popup (existing)
panel.ensure_view()
assert panel.tab_count() >= 1
# ... _adopt_popup / _on_new_tab unchanged

w._ui_mode = "ide_companion"
ide_panel = w.show_ide_internal_browser()  # not show_browser_workspace
assert w._ui_mode == "ide_companion"
assert not w.dedicated_browser_active()
ide = w._iris_ide_window
assert ide is not None
assert ide_panel is panel
assert ide.is_browser_visible() or ide._stack.currentWidget() is panel
ide.return_from_browser()
assert not ide.is_browser_visible()
w.show_ide_internal_browser()
assert ide.is_browser_visible() or ide._stack.currentWidget() is panel
```

`iris/ui/browser/_check_mini_player.py`

- Fixture toggle. After `MiniPlayer(on=False)`, `view_host() is ViewHost.DEDICATED` (default resume). `mini_player is False`. Idempotent `on=True` still `detail == "idempotent"`.
- Qt reparent on `IrisIdeWindow`. After leave-watch-url, `view_host() is MINI`. After `MiniPlayer(on=False)`, `view_host() is IDE_INTERNAL` and `win.is_browser_visible()`. Same driver id.
- Chat pip. `show_browser_workspace` then mini then calendar. Mini still anchored to `w._chat`. Expand puts the view back in the panel slot. After calendar, `resume_host() is DEDICATED` so expand does not create `IrisIdeWindow`.

Do not drop tab, popup, driver-id, or chat-anchor assertions.

## Catalog copy

Replace "Iris IDE browser stack page" with two sentences. Dedicated screen is MainWindow `_browser_shell`. IDE-internal cover is `IrisIdeWindow._stack`.
