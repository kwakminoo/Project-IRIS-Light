from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from iris.browser._driver import recovery_text, remaining_wait
from iris.browser.search import BROWSER_HOME_URL, search_url
from iris.browser.types import (
    BrowserCommand,
    BrowserPhase,
    BrowserResult,
    BrowserSnapshot,
    Click,
    Extract,
    HistoryStep,
    Media,
    MiniPlayer,
    NAME_CAP,
    NODE_CAP,
    Navigate,
    Open,
    PageNode,
    PanelHost,
    Reload,
    Scroll,
    Search,
    Snapshot,
    TypeText,
    ViewHost,
    as_docked,
    as_mini,
    empty_snapshot,
    is_docked,
    is_mini,
    make_page_ref,
    split_page_ref,
)
from iris.browser.youtube import is_youtube_watch_url, page_block_reason

UiCall = Callable[[Callable[[], Any]], Any]
SurfaceProvider = Callable[[], Any]
HostApplier = Callable[[ViewHost], None]
SnapshotListener = Callable[[BrowserSnapshot], None]

log = logging.getLogger("iris.browser")

PLAY_BUDGET_SEC = 90.0


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
        self._view_host: ViewHost = PanelHost(site="dedicated")
        self._snap = empty_snapshot(phase=BrowserPhase.CLOSED)
        self._listeners: list[SnapshotListener] = []
        self._visible = False
        self._last_result: BrowserResult | None = None
        self._panel_ref: Any = None
        self._gen = 0
        self._published_fault: str | None = None

    def set_ui_call(self, ui_call: UiCall) -> None:
        self._ui_call = ui_call
        driver = self._driver
        if driver is not None:
            driver._ui_call = ui_call

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
                self._snap = self._overlay_host(self._stamp(driver.read_snapshot()))

    def _ui_from_locked(self, fn: Callable[[], Any]) -> Any:
        """Drop _lock while on the UI thread. UI callbacks re-enter snapshot/note_*."""
        self._lock.release()
        try:
            return self._ui_call(fn)
        finally:
            self._lock.acquire()

    def note_surface_ready(self, view: Any) -> None:
        """HUD already showed the panel — do not show IrisIdeWindow on the next command."""
        with self._lock:
            if self._driver is None and view is not None:
                from iris.browser._driver import WebEnginePageDriver

                self._driver = WebEnginePageDriver(view, ui_call=self._ui_call)
            parent = getattr(view, "parent", None)
            widget = parent() if callable(parent) else parent
            if widget is not None and hasattr(widget, "tab_count"):
                self._panel_ref = widget
            self._visible = True

    def add_listener(self, listener: SnapshotListener) -> None:
        self._listeners.append(listener)

    def _tab_meta(self) -> tuple[int, int]:
        panel = self._panel_ref
        if panel is None:
            return 0, 1
        try:
            count_fn = getattr(panel, "tab_count", None)
            idx_fn = getattr(panel, "current_tab_index", None)
            count = int(count_fn() if callable(count_fn) else 1) or 1
            idx = int(idx_fn() if callable(idx_fn) else 0)
            return idx, max(1, count)
        except Exception:
            return 0, 1

    def _overlay_host(self, snap: BrowserSnapshot) -> BrowserSnapshot:
        tab_index, tab_count = self._tab_meta()
        return snap.evolve(
            mini_player=is_mini(self._view_host),
            tab_index=tab_index,
            tab_count=tab_count,
            target_id=f"tab:{tab_index}",
        )

    def last_result(self) -> BrowserResult | None:
        """Last execute() result, or None if this process has not run a command."""
        with self._lock:
            return self._last_result

    def snapshot(self) -> BrowserSnapshot:
        if not self._lock.acquire(blocking=False):
            return self._snap
        try:
            if self._driver is not None:
                try:
                    live = self._driver.read_snapshot()
                    self._snap = self._overlay_host(
                        live.evolve(
                            gen=self._snap.gen,
                            nodes=self._snap.nodes,
                            excerpt=self._snap.excerpt or live.excerpt,
                        )
                    )
                    if (
                        self._snap.phase == BrowserPhase.FAULTED
                        and self._published_fault != self._snap.last_error
                    ):
                        self._published_fault = self._snap.last_error
                        self._publish(self._snap)
                except Exception as exc:
                    self._snap = self._snap.evolve(
                        phase=BrowserPhase.FAULTED,
                        last_error=str(exc),
                        mini_player=is_mini(self._view_host),
                    )
            else:
                self._snap = self._overlay_host(self._snap)
            return self._snap
        finally:
            self._lock.release()

    def ensure_visible(self) -> None:
        with self._lock:
            self._ensure_driver_locked()

    def _ensure_driver_locked(self) -> Any:
        if self._driver is not None:
            if (
                not self._visible
                and self._surface_provider is not None
                and is_docked(self._view_host)
            ):
                self._ui_from_locked(self._show_surface)
                self._visible = True
            return self._driver
        if self._surface_provider is None:
            raise RuntimeError("browser surface not available")

        def create() -> Any:
            panel = self._surface_provider()
            if panel is None:
                raise RuntimeError("browser view create failed")
            view = panel.ensure_view()
            from iris.browser._driver import WebEnginePageDriver

            return WebEnginePageDriver(view, ui_call=self._ui_call), panel

        packed = self._ui_from_locked(create)
        if not isinstance(packed, tuple) or packed[0] is None:
            raise RuntimeError("browser view create failed")
        driver, panel = packed
        if self._driver is None:
            self._driver = driver
        if panel is not None:
            self._panel_ref = panel
        self._visible = True
        self._view_host = as_docked(self._view_host)
        self._snap = empty_snapshot(phase=BrowserPhase.READY)
        return self._driver

    def _show_surface(self) -> None:
        if self._surface_provider is not None:
            self._surface_provider()

    def _apply_host_locked(self, host: ViewHost) -> None:
        current = self._view_host
        if is_mini(current) and is_mini(host):
            return
        if is_docked(current) and is_docked(host) and current.site == host.site:
            return
        if self._host_applier is not None:
            self._ui_from_locked(lambda h=host: self._host_applier(h))
        self._view_host = host

    def _publish(self, snap: BrowserSnapshot) -> None:
        self._snap = self._overlay_host(snap)
        if self._snap.phase != BrowserPhase.FAULTED:
            self._published_fault = None
        for listener in list(self._listeners):
            try:
                listener(self._snap)
            except Exception:
                pass

    def _stamp(self, snap: BrowserSnapshot) -> BrowserSnapshot:
        self._gen += 1
        nodes = tuple(
            PageNode(
                ref=make_page_ref(self._gen, i),
                role=n.role,
                name=(n.name or "")[:NAME_CAP],
                interactive=n.interactive,
                frame=n.frame or "",
                in_view=bool(n.in_view),
            )
            for i, n in enumerate(snap.nodes[:NODE_CAP])
        )
        return snap.evolve(gen=self._gen, nodes=nodes)

    def _publish_fresh(self, snap: BrowserSnapshot) -> BrowserSnapshot:
        stamped = self._stamp(snap)
        self._publish(stamped)
        return self._snap

    def _resolve_ref(self, ref: str) -> PageNode:
        snap = self._snap
        try:
            gen, index = split_page_ref(ref)
        except ValueError as exc:
            raise LookupError("bad_ref") from exc
        if gen != snap.gen:
            raise LookupError("stale_ref")
        if index < 0 or index >= len(snap.nodes):
            raise LookupError("unknown_ref")
        node = snap.nodes[index]
        if node.ref != ref:
            raise LookupError("stale_ref")
        return node

    def _settle(self, driver: Any) -> None:
        settle = getattr(driver, "settle_after_act", None)
        if callable(settle):
            settle()

    def execute(self, cmd: BrowserCommand) -> BrowserResult:
        result = self._execute_body(cmd)
        with self._lock:
            self._last_result = result
        return result

    def _execute_body(self, cmd: BrowserCommand) -> BrowserResult:
        with self._lock:
            kind = getattr(cmd, "kind", "unknown")
            log.info("cmd=%s", kind)
            try:
                if isinstance(cmd, Snapshot) and self._driver is None and self._surface_provider is None:
                    snap = self._overlay_host(self._snap)
                    return BrowserResult(True, "snapshot", snap)

                if isinstance(cmd, Open):
                    self._ensure_driver_locked()
                    self._apply_host_locked(as_docked(self._view_host))
                    snap = self._driver.read_snapshot()
                    url = (snap.url or "").strip()
                    if not url or url in ("about:blank", "about:blank#blocked"):
                        self._driver.navigate(BROWSER_HOME_URL)
                        snap = self._driver.read_snapshot()
                    if snap.phase == BrowserPhase.CLOSED:
                        snap = snap.evolve(phase=BrowserPhase.READY, last_error=None, url=snap.url or "about:blank")
                    snap = self._publish_fresh(snap)
                    return BrowserResult(True, "open", snap)

                if isinstance(cmd, MiniPlayer):
                    self._ensure_driver_locked()
                    already = is_mini(self._view_host) if cmd.on else is_docked(self._view_host)
                    if already:
                        snap = self._overlay_host(self._driver.read_snapshot())
                        snap = self._publish_fresh(snap)
                        return BrowserResult(True, "mini_player", snap, detail="idempotent")
                    target = as_mini(self._view_host) if cmd.on else as_docked(self._view_host)
                    self._apply_host_locked(target)
                    snap = self._publish_fresh(self._driver.read_snapshot())
                    return BrowserResult(True, "mini_player", snap)

                driver = self._ensure_driver_locked()

                if isinstance(cmd, Snapshot):
                    snap = driver.read_snapshot()
                    snap = self._publish_fresh(snap)
                    return BrowserResult(True, "snapshot", snap)

                if isinstance(cmd, Extract):
                    read_text = ""
                    reader = getattr(driver, "read_text", None)
                    if callable(reader):
                        read_text = str(
                            reader(scope=cmd.scope, ref=cmd.ref, max_chars=cmd.max_chars) or ""
                        )
                    snap = self._overlay_host(self._snap)
                    self._publish(snap)
                    return BrowserResult(True, "extract", snap, read_text=read_text)

                if isinstance(cmd, Navigate):
                    current = driver.read_snapshot()
                    if (
                        current.url.rstrip("/") == cmd.url.rstrip("/")
                        and current.phase == BrowserPhase.READY
                    ):
                        snap = self._publish_fresh(current)
                        return BrowserResult(True, "navigate", snap, detail="idempotent")
                    driver.navigate(cmd.url)
                    snap = self._publish_fresh(driver.read_snapshot())
                    return BrowserResult(True, "navigate", snap)

                if isinstance(cmd, Search):
                    url = search_url(cmd.query, engine=cmd.engine)
                    log.info("search engine=%s play=%s url=%s", cmd.engine, cmd.play, url)
                    deadline = time.monotonic() + PLAY_BUDGET_SEC if cmd.play else None
                    driver.navigate(url, deadline=deadline)
                    snap = driver.read_snapshot()
                    block = page_block_reason(snap.url, snap.title)
                    if block:
                        snap = self._publish_fresh(snap)
                        log.warning("search blocked=%s url=%s", block, snap.url)
                        return BrowserResult(False, "search", snap, detail=block)
                    detail = ""
                    if cmd.play:
                        play_err = _play_first_result(driver, deadline=deadline)
                        snap = driver.read_snapshot()
                        playing = bool(snap.media and snap.media.playing)
                        if play_err or not playing:
                            detail = play_err or (
                                (snap.media.block if snap.media else "") or "not playing"
                            )
                            snap = self._publish_fresh(snap)
                            log.warning("youtube play failed detail=%s url=%s", detail, snap.url)
                            return BrowserResult(False, "search", snap, detail=detail)
                        if snap.media and snap.media.ad:
                            detail = "ad_playing"
                    snap = self._publish_fresh(driver.read_snapshot())
                    if "/sorry/" in (snap.url or ""):
                        log.warning("search captcha url=%s", snap.url)
                        return BrowserResult(False, "search", snap, detail="captcha")
                    log.info("search ok url=%s playing=%s", snap.url, bool(snap.media and snap.media.playing))
                    return BrowserResult(True, "search", snap, detail=detail)

                if isinstance(cmd, Media):
                    snap = driver.read_snapshot()
                    block = page_block_reason(snap.url, snap.title)
                    if block:
                        snap = snap.evolve(gen=self._snap.gen, nodes=self._snap.nodes)
                        self._publish(snap)
                        return BrowserResult(False, "media", snap, detail=block)
                    if cmd.action == "pause":
                        err = driver.try_pause() if hasattr(driver, "try_pause") else "pause unsupported"
                    else:
                        err = driver.try_play() if hasattr(driver, "try_play") else "play unsupported"
                    snap = driver.read_snapshot()
                    snap = snap.evolve(gen=self._snap.gen, nodes=self._snap.nodes)
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
                    snap = self._publish_fresh(driver.read_snapshot())
                    return BrowserResult(True, "reload", snap)

                if isinstance(cmd, HistoryStep):
                    snap_before = driver.read_snapshot()
                    if cmd.delta < 0 and not snap_before.can_go_back:
                        return BrowserResult(False, "history", self._snap, detail="cannot go back")
                    if cmd.delta > 0 and not snap_before.can_go_forward:
                        return BrowserResult(False, "history", self._snap, detail="cannot go forward")
                    try:
                        driver.history_step(cmd.delta)
                    except LookupError:
                        snap = self._publish_fresh(driver.read_snapshot())
                        return BrowserResult(False, "history", snap, detail="history edge")
                    self._settle(driver)
                    snap = self._publish_fresh(driver.read_snapshot())
                    return BrowserResult(True, "history", snap)

                if isinstance(cmd, Click):
                    try:
                        self._resolve_ref(cmd.target.ref)
                        driver.click(cmd.target)
                    except LookupError as exc:
                        return BrowserResult(False, "click", self._overlay_host(self._snap), detail=str(exc))
                    self._settle(driver)
                    snap = self._publish_fresh(driver.read_snapshot())
                    return BrowserResult(True, "click", snap)

                if isinstance(cmd, TypeText):
                    try:
                        self._resolve_ref(cmd.target.ref)
                        driver.type_text(cmd.target, cmd.text, clear=cmd.clear)
                    except LookupError as exc:
                        return BrowserResult(False, "type", self._overlay_host(self._snap), detail=str(exc))
                    self._settle(driver)
                    snap = self._publish_fresh(driver.read_snapshot())
                    return BrowserResult(True, "type", snap)

                if isinstance(cmd, Scroll):
                    try:
                        if cmd.ref:
                            self._resolve_ref(cmd.ref)
                            driver.scroll_by(cmd.delta_x, cmd.delta_y, ref=cmd.ref)
                        else:
                            driver.scroll_by(cmd.delta_x, cmd.delta_y)
                    except LookupError as exc:
                        return BrowserResult(False, "scroll", self._overlay_host(self._snap), detail=str(exc))
                    self._settle(driver)
                    snap = self._publish_fresh(driver.read_snapshot())
                    return BrowserResult(True, "scroll", snap)

                snap = driver.read_snapshot()
                return BrowserResult(False, str(kind), snap, detail="unknown command")
            except Exception as exc:
                log.exception("browser command %s failed: %s", kind, exc)
                mark = getattr(self._driver, "mark_fault", None)
                if callable(mark):
                    try:
                        mark(str(exc))
                    except Exception:
                        pass
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


def _wait_watch_or_block(driver: Any, *, deadline: float) -> BrowserSnapshot:
    last = driver.read_snapshot()
    while time.monotonic() < deadline:
        last = driver.read_snapshot()
        if is_youtube_watch_url(last.url) or "/watch" in (last.url or ""):
            return last
        if page_block_reason(last.url, last.title):
            return last
        pause = remaining_wait(deadline, 0.25)
        if pause <= 0:
            break
        time.sleep(pause)
    return last


def _play_first_result(driver: Any, *, deadline: float) -> str:
    from iris.browser.types import ByCss, ByText
    from iris.browser.youtube import first_watch_locator

    if remaining_wait(deadline, 1.0) <= 0:
        mark = getattr(driver, "mark_fault", None)
        if callable(mark):
            mark(recovery_text("play"))
        raise TimeoutError(recovery_text("play"))

    locators = (
        first_watch_locator(),
        ByCss(css="a.yt-simple-endpoint[href*='/watch']"),
        ByCss(css="a[href*='/watch?v=']"),
        ByCss(css="ytd-video-renderer a#video-title"),
    )
    getter = getattr(driver, "first_watch_url", None)
    last_err = "no video result"
    opened = False
    while time.monotonic() < deadline:
        href = ""
        if callable(getter):
            try:
                href = getter(deadline=deadline)
            except TypeError:
                href = getter()
        if href:
            driver.navigate(href, deadline=deadline)
            opened = True
            last_err = ""
            break
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
        for node in snap.nodes:
            if node.role == "link" and node.name:
                try:
                    driver.click(ByText(text=node.name, nth=0))
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
        pause = remaining_wait(deadline, 0.45)
        if pause <= 0:
            break
        time.sleep(pause)
    if last_err:
        return last_err
    pause = remaining_wait(deadline, 0.4)
    if pause > 0:
        time.sleep(pause)
    snap = _wait_watch_or_block(driver, deadline=deadline)
    block = page_block_reason(snap.url, snap.title)
    if block:
        return block
    if not (is_youtube_watch_url(snap.url) or "/watch" in (snap.url or "")):
        return f"opened {snap.url} (not a watch URL — site may have blocked playback)"
    if remaining_wait(deadline, 1.0) <= 0:
        return recovery_text("play")
    try_play = getattr(driver, "try_play", None)
    if callable(try_play):
        note = try_play(deadline=deadline)
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
