from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from iris.browser.search import BROWSER_HOME_URL, search_url
from iris.browser.types import (
    BrowserCommand,
    BrowserPhase,
    BrowserResult,
    BrowserSnapshot,
    Click,
    HistoryStep,
    Media,
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
from iris.browser.youtube import is_youtube_watch_url, page_block_reason

UiCall = Callable[[Callable[[], Any]], Any]
SurfaceProvider = Callable[[], Any]
HostApplier = Callable[[ViewHost], None]
SnapshotListener = Callable[[BrowserSnapshot], None]

log = logging.getLogger("iris.browser")


class BrowserSession:
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
        with self._lock:
            self._view_host = host
            self._snap = self._overlay_host(self._snap)

    def set_driver(self, driver: Any) -> None:
        with self._lock:
            self._driver = driver
            if driver is not None:
                self._snap = self._overlay_host(driver.read_snapshot())

    def note_surface_ready(self, view: Any) -> None:
        """HUD already showed the panel — do not show IrisIdeWindow on the next command."""
        with self._lock:
            if self._driver is None and view is not None:
                from iris.browser._driver import WebEnginePageDriver

                self._driver = WebEnginePageDriver(view, ui_call=self._ui_call)
            self._visible = True

    def add_listener(self, listener: SnapshotListener) -> None:
        self._listeners.append(listener)

    def _tab_meta(self) -> tuple[int, int]:
        provider = self._surface_provider
        if provider is None:
            return 0, 1
        try:
            panel = provider()
        except Exception:
            return 0, 1
        if panel is None:
            return 0, 1
        count_fn = getattr(panel, "tab_count", None)
        idx_fn = getattr(panel, "current_tab_index", None)
        count = int(count_fn() if callable(count_fn) else 1) or 1
        idx = int(idx_fn() if callable(idx_fn) else 0)
        return idx, max(1, count)

    def _overlay_host(self, snap: BrowserSnapshot) -> BrowserSnapshot:
        flag = self._view_host == "mini"
        tab_index, tab_count = self._tab_meta()
        return snap.evolve(
            mini_player=flag,
            tab_index=tab_index,
            tab_count=tab_count,
            target_id=f"tab:{tab_index}",
        )

    def snapshot(self) -> BrowserSnapshot:
        with self._lock:
            if self._driver is not None:
                try:
                    self._snap = self._overlay_host(self._driver.read_snapshot())
                except Exception as exc:
                    self._snap = self._snap.evolve(
                        phase=BrowserPhase.FAULTED,
                        last_error=str(exc),
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
            log.info("cmd=%s", kind)
            try:
                if isinstance(cmd, Snapshot) and self._driver is None and self._surface_provider is None:
                    snap = self._overlay_host(self._snap)
                    return BrowserResult(True, "snapshot", snap)

                if isinstance(cmd, Open):
                    self._ensure_driver_locked()
                    self._apply_host_locked("panel")
                    snap = self._driver.read_snapshot()
                    url = (snap.url or "").strip()
                    if not url or url in ("about:blank", "about:blank#blocked"):
                        self._driver.navigate(BROWSER_HOME_URL)
                        snap = self._driver.read_snapshot()
                    if snap.phase == BrowserPhase.CLOSED:
                        snap = snap.evolve(phase=BrowserPhase.READY, last_error=None, url=snap.url or "about:blank")
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
                    log.info("search engine=%s play=%s url=%s", cmd.engine, cmd.play, url)
                    driver.navigate(url)
                    snap = driver.read_snapshot()
                    block = page_block_reason(snap.url, snap.title)
                    if block:
                        self._publish(snap)
                        log.warning("search blocked=%s url=%s", block, snap.url)
                        return BrowserResult(False, "search", snap, detail=block)
                    detail = ""
                    if cmd.play:
                        play_err = _play_first_result(driver)
                        snap = driver.read_snapshot()
                        playing = bool(snap.media and snap.media.playing)
                        if play_err or not playing:
                            detail = play_err or (
                                (snap.media.block if snap.media else "") or "not playing"
                            )
                            self._publish(snap)
                            log.warning("youtube play failed detail=%s url=%s", detail, snap.url)
                            return BrowserResult(False, "search", snap, detail=detail)
                        if snap.media and snap.media.ad:
                            detail = "ad_playing"
                    snap = driver.read_snapshot()
                    self._publish(snap)
                    if "/sorry/" in (snap.url or ""):
                        log.warning("search captcha url=%s", snap.url)
                        return BrowserResult(False, "search", snap, detail="captcha")
                    log.info("search ok url=%s playing=%s", snap.url, bool(snap.media and snap.media.playing))
                    return BrowserResult(True, "search", snap, detail=detail)

                if isinstance(cmd, Media):
                    snap = driver.read_snapshot()
                    block = page_block_reason(snap.url, snap.title)
                    if block:
                        self._publish(snap)
                        return BrowserResult(False, "media", snap, detail=block)
                    if cmd.action == "pause":
                        err = driver.try_pause() if hasattr(driver, "try_pause") else "pause unsupported"
                    else:
                        err = driver.try_play() if hasattr(driver, "try_play") else "play unsupported"
                    snap = driver.read_snapshot()
                    playing = bool(snap.media and snap.media.playing)
                    ok = (not playing) if cmd.action == "pause" else playing
                    self._publish(snap)
                    if not ok:
                        detail = err or ("still playing" if cmd.action == "pause" else "not playing")
                        log.warning("media %s failed detail=%s url=%s", cmd.action, detail, snap.url)
                        return BrowserResult(False, "media", snap, detail=detail)
                    log.info("media %s ok url=%s", cmd.action, snap.url)
                    return BrowserResult(True, "media", snap)

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
            except Exception as exc:
                log.exception("browser command %s failed: %s", kind, exc)
                snap = empty_snapshot(phase=BrowserPhase.FAULTED)
                if self._driver is not None:
                    try:
                        snap = self._driver.read_snapshot()
                    except Exception:
                        pass
                if snap.phase != BrowserPhase.FAULTED:
                    snap = snap.evolve(phase=BrowserPhase.FAULTED, last_error=str(exc))
                self._publish(snap)
                return BrowserResult(False, str(kind), snap, detail=str(exc))


def _wait_watch_or_block(driver: Any, timeout: float = 12.0) -> BrowserSnapshot:
    deadline = time.monotonic() + timeout
    last = driver.read_snapshot()
    while time.monotonic() < deadline:
        last = driver.read_snapshot()
        if is_youtube_watch_url(last.url) or "/watch" in (last.url or ""):
            return last
        block = page_block_reason(last.url, last.title)
        if block:
            return last
        time.sleep(0.25)
    return last


def _play_first_result(driver: Any) -> str:
    """Open first watch result, then verify media playing. No restriction bypass."""
    from iris.browser.types import ByCss, ByText
    from iris.browser.youtube import first_watch_locator

    locators = (
        first_watch_locator(),
        ByCss(css="a.yt-simple-endpoint[href*='/watch']"),
        ByCss(css="a[href*='/watch?v=']"),
        ByCss(css="ytd-video-renderer a#video-title"),
    )
    getter = getattr(driver, "first_watch_url", None)
    last_err = "no video result"
    opened = False
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        href = getter() if callable(getter) else ""
        if href:
            try:
                driver.navigate(href)
                opened = True
                last_err = ""
                break
            except Exception as exc:
                last_err = str(exc)
        for loc in locators:
            try:
                driver.click(loc)
                opened = True
                last_err = ""
                break
            except LookupError as exc:
                last_err = str(exc)
        if opened:
            break
        snap = driver.read_snapshot()
        for lm in snap.landmarks:
            if lm.role == "link" and lm.name:
                try:
                    driver.click(ByText(text=lm.name, nth=0))
                    opened = True
                    last_err = ""
                    break
                except LookupError as exc:
                    last_err = str(exc)
        if opened:
            break
        block = page_block_reason(snap.url, snap.title)
        if block:
            return block
        if "youtube.com" not in (snap.url or "").lower():
            break
        time.sleep(0.45)
    if last_err:
        return last_err
    time.sleep(0.4)
    snap = _wait_watch_or_block(driver)
    block = page_block_reason(snap.url, snap.title)
    if block:
        return block
    if not (is_youtube_watch_url(snap.url) or "/watch" in (snap.url or "")):
        return f"opened {snap.url} (not a watch URL — site may have blocked playback)"
    try_play = getattr(driver, "try_play", None)
    if callable(try_play):
        note = try_play()
        if note:
            return note
    return ""


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
