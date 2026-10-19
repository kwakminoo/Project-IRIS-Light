"""BrowserSession — sole mutator for the Iris IDE browser surface."""

from __future__ import annotations

import threading
from typing import Any, Callable

from iris.browser.search import search_url
from iris.browser.types import (
    BrowserCommand,
    BrowserPhase,
    BrowserResult,
    BrowserSnapshot,
    Click,
    HistoryStep,
    MiniPlayer,
    Navigate,
    Open,
    Reload,
    Scroll,
    Search,
    Snapshot,
    TypeText,
    ViewHost,
    empty_snapshot,
)

UiCall = Callable[[Callable[[], Any]], Any]
SurfaceProvider = Callable[[], Any]
HostApplier = Callable[[ViewHost], None]
SnapshotListener = Callable[[BrowserSnapshot], None]


class BrowserSession:
    """Deep module: execute + snapshot + ensure_visible."""

    def __init__(
        self,
        *,
        driver: Any | None = None,
        ui_call: UiCall | None = None,
        surface_provider: SurfaceProvider | None = None,
        host_applier: HostApplier | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._driver = driver
        self._ui_call: UiCall = ui_call or (lambda fn: fn())
        self._surface_provider = surface_provider
        self._host_applier = host_applier
        self._view_host: ViewHost = "panel"
        self._snap = empty_snapshot(phase=BrowserPhase.CLOSED)
        self._listeners: list[SnapshotListener] = []
        self._visible = False

    def set_ui_call(self, ui_call: UiCall) -> None:
        self._ui_call = ui_call

    def set_surface_provider(self, provider: SurfaceProvider | None) -> None:
        self._surface_provider = provider

    def set_host_applier(self, applier: HostApplier | None) -> None:
        self._host_applier = applier

    def view_host(self) -> ViewHost:
        with self._lock:
            return self._view_host

    def note_view_host(self, host: ViewHost) -> None:
        """UI reports host after reparent (auto-mini / chrome)."""
        with self._lock:
            self._view_host = host
            self._snap = self._overlay_host(self._snap)

    def set_driver(self, driver: Any) -> None:
        with self._lock:
            self._driver = driver
            if driver is not None:
                self._snap = self._overlay_host(driver.read_snapshot())

    def add_listener(self, listener: SnapshotListener) -> None:
        self._listeners.append(listener)

    def _overlay_host(self, snap: BrowserSnapshot) -> BrowserSnapshot:
        flag = self._view_host == "mini"
        if snap.mini_player == flag:
            return snap
        return BrowserSnapshot(
            url=snap.url,
            title=snap.title,
            phase=snap.phase,
            can_go_back=snap.can_go_back,
            can_go_forward=snap.can_go_forward,
            scroll_x=snap.scroll_x,
            scroll_y=snap.scroll_y,
            last_error=snap.last_error,
            landmarks=snap.landmarks,
            mini_player=flag,
        )

    def snapshot(self) -> BrowserSnapshot:
        with self._lock:
            if self._driver is not None:
                try:
                    self._snap = self._overlay_host(self._driver.read_snapshot())
                except Exception as exc:  # noqa: BLE001
                    self._snap = BrowserSnapshot(
                        url=self._snap.url,
                        title=self._snap.title,
                        phase=BrowserPhase.FAULTED,
                        can_go_back=self._snap.can_go_back,
                        can_go_forward=self._snap.can_go_forward,
                        scroll_x=self._snap.scroll_x,
                        scroll_y=self._snap.scroll_y,
                        last_error=str(exc),
                        landmarks=self._snap.landmarks,
                        mini_player=self._view_host == "mini",
                    )
            else:
                self._snap = self._overlay_host(self._snap)
            return self._snap

    def ensure_visible(self) -> None:
        with self._lock:
            self._ensure_driver_locked()

    def _ensure_driver_locked(self) -> Any:
        if self._driver is not None:
            if (
                not self._visible
                and self._surface_provider is not None
                and self._view_host == "panel"
            ):
                self._ui_call(self._show_surface)
                self._visible = True
            return self._driver
        if self._surface_provider is None:
            raise RuntimeError("browser surface not available")

        def create() -> Any:
            panel = self._surface_provider()
            view = panel.ensure_view()
            from iris.browser._driver import WebEnginePageDriver

            return WebEnginePageDriver(view, ui_call=self._ui_call), panel

        driver, _panel = self._ui_call(create)
        self._driver = driver
        self._visible = True
        self._view_host = "panel"
        self._snap = empty_snapshot(phase=BrowserPhase.READY)
        return self._driver

    def _show_surface(self) -> None:
        if self._surface_provider is not None:
            self._surface_provider()

    def _apply_host_locked(self, host: ViewHost) -> None:
        if self._view_host == host:
            return
        if self._host_applier is not None:
            self._ui_call(lambda h=host: self._host_applier(h))
        self._view_host = host

    def _publish(self, snap: BrowserSnapshot) -> None:
        self._snap = self._overlay_host(snap)
        for listener in list(self._listeners):
            try:
                listener(self._snap)
            except Exception:
                pass

    def execute(self, cmd: BrowserCommand) -> BrowserResult:
        with self._lock:
            kind = getattr(cmd, "kind", "unknown")
            try:
                if isinstance(cmd, Snapshot) and self._driver is None and self._surface_provider is None:
                    snap = self._overlay_host(self._snap)
                    return BrowserResult(True, "snapshot", snap)

                if isinstance(cmd, Open):
                    self._ensure_driver_locked()
                    self._apply_host_locked("panel")
                    snap = self._driver.read_snapshot()
                    if snap.phase == BrowserPhase.CLOSED:
                        snap = BrowserSnapshot(
                            url=snap.url or "about:blank",
                            title=snap.title,
                            phase=BrowserPhase.READY,
                            can_go_back=snap.can_go_back,
                            can_go_forward=snap.can_go_forward,
                            scroll_x=snap.scroll_x,
                            scroll_y=snap.scroll_y,
                            last_error=None,
                            landmarks=snap.landmarks,
                        )
                    self._publish(snap)
                    return BrowserResult(True, "open", snap)

                if isinstance(cmd, MiniPlayer):
                    target: ViewHost = "mini" if cmd.on else "panel"
                    self._ensure_driver_locked()
                    if self._view_host == target:
                        snap = self._overlay_host(self._driver.read_snapshot())
                        self._publish(snap)
                        return BrowserResult(True, "mini_player", snap, detail="idempotent")
                    self._apply_host_locked(target)
                    snap = self._overlay_host(self._driver.read_snapshot())
                    self._publish(snap)
                    return BrowserResult(True, "mini_player", snap)

                driver = self._ensure_driver_locked()

                if isinstance(cmd, Snapshot):
                    snap = driver.read_snapshot()
                    self._publish(snap)
                    return BrowserResult(True, "snapshot", snap)

                if isinstance(cmd, Navigate):
                    current = driver.read_snapshot()
                    if (
                        current.url.rstrip("/") == cmd.url.rstrip("/")
                        and current.phase == BrowserPhase.READY
                    ):
                        self._publish(current)
                        return BrowserResult(True, "navigate", current, detail="idempotent")
                    driver.navigate(cmd.url)
                    snap = driver.read_snapshot()
                    self._publish(snap)
                    return BrowserResult(True, "navigate", snap)

                if isinstance(cmd, Search):
                    url = search_url(cmd.query, engine=cmd.engine)
                    driver.navigate(url)
                    snap = driver.read_snapshot()
                    self._publish(snap)
                    return BrowserResult(True, "search", snap)

                if isinstance(cmd, Reload):
                    driver.reload()
                    snap = driver.read_snapshot()
                    self._publish(snap)
                    return BrowserResult(True, "reload", snap)

                if isinstance(cmd, HistoryStep):
                    snap_before = driver.read_snapshot()
                    if cmd.delta < 0 and not snap_before.can_go_back:
                        return BrowserResult(False, "history", snap_before, detail="cannot go back")
                    if cmd.delta > 0 and not snap_before.can_go_forward:
                        return BrowserResult(False, "history", snap_before, detail="cannot go forward")
                    try:
                        driver.history_step(cmd.delta)
                    except LookupError:
                        snap = driver.read_snapshot()
                        self._publish(snap)
                        return BrowserResult(False, "history", snap, detail="history edge")
                    snap = driver.read_snapshot()
                    self._publish(snap)
                    return BrowserResult(True, "history", snap)

                if isinstance(cmd, Click):
                    driver.click(cmd.target)
                    snap = driver.read_snapshot()
                    self._publish(snap)
                    return BrowserResult(True, "click", snap)

                if isinstance(cmd, TypeText):
                    driver.type_text(cmd.target, cmd.text, clear=cmd.clear)
                    snap = driver.read_snapshot()
                    self._publish(snap)
                    return BrowserResult(True, "type", snap)

                if isinstance(cmd, Scroll):
                    driver.scroll_by(cmd.delta_x, cmd.delta_y)
                    snap = driver.read_snapshot()
                    self._publish(snap)
                    return BrowserResult(True, "scroll", snap)

                snap = driver.read_snapshot()
                return BrowserResult(False, str(kind), snap, detail="unknown command")
            except Exception as exc:  # noqa: BLE001
                snap = empty_snapshot(phase=BrowserPhase.FAULTED)
                if self._driver is not None:
                    try:
                        snap = self._driver.read_snapshot()
                    except Exception:
                        pass
                if snap.phase != BrowserPhase.FAULTED:
                    snap = BrowserSnapshot(
                        url=snap.url,
                        title=snap.title,
                        phase=BrowserPhase.FAULTED,
                        can_go_back=snap.can_go_back,
                        can_go_forward=snap.can_go_forward,
                        scroll_x=snap.scroll_x,
                        scroll_y=snap.scroll_y,
                        last_error=str(exc),
                        landmarks=snap.landmarks,
                    )
                self._publish(snap)
                return BrowserResult(False, str(kind), snap, detail=str(exc))


_SESSION: BrowserSession | None = None
_SESSION_LOCK = threading.Lock()


def get_browser_session() -> BrowserSession:
    global _SESSION
    with _SESSION_LOCK:
        if _SESSION is None:
            _SESSION = BrowserSession()
        return _SESSION


def reset_browser_session_for_tests() -> None:
    global _SESSION
    with _SESSION_LOCK:
        _SESSION = None
