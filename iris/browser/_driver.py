"""Private page drivers — not part of the public iris.browser API."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import parse_qs, urlparse

from iris.browser.types import (
    BrowserPhase,
    BrowserSnapshot,
    ByCss,
    ByRef,
    ByRole,
    ByText,
    EXTRACT_MAX,
    EXCERPT_CAP,
    FrameInfo,
    Locator,
    NAME_CAP,
    PageNode,
    MediaState,
    media_from_dict,
    split_page_ref,
)

_REF_MISS = frozenset({"stale_ref", "bad_ref", "unknown_ref", "element not found"})

log = logging.getLogger("iris.browser")

NAV_WAIT_SEC = 45.0
RELOAD_WAIT_SEC = 30.0

_RECOVERY = {
    "navigate": "navigate timeout. Reload or try again.",
    "reload": "reload timeout. Try again.",
    "blank": "page failed to load. Reload or try a different URL.",
    "crash": "renderer crashed. Reload the page.",
    "play": "play timed out. Try search again.",
}

_BRIDGE_JS = (Path(__file__).resolve().parent / "_bridge.js").read_text(encoding="utf-8")


def recovery_text(kind: str) -> str:
    return _RECOVERY[kind]


def remaining_wait(deadline: float | None, default: float) -> float:
    if deadline is None:
        return max(0.0, float(default))
    return max(0.0, min(float(default), deadline - time.monotonic()))


def _is_normal_termination(status: Any) -> bool:
    name = getattr(status, "name", None)
    text = str(name if name is not None else status).split(".")[-1].lower().replace(" ", "")
    if text in {"normal", "normaltermination", "normalterminationstatus"}:
        return True
    try:
        return int(status) == 0
    except (TypeError, ValueError):
        return False


def _bbox4(raw: object) -> tuple[int, int, int, int] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        return (int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3]))
    except (TypeError, ValueError):
        return None


class PageDriver(Protocol):
    def read_snapshot(self) -> BrowserSnapshot: ...
    def navigate(self, url: str, *, deadline: float | None = None) -> None: ...
    def reload(self, *, deadline: float | None = None) -> None: ...
    def history_step(self, delta: int) -> None: ...
    def click(self, target: Locator) -> None: ...
    def type_text(self, target: Locator, text: str, *, clear: bool) -> None: ...
    def scroll_by(self, dx: int, dy: int, *, ref: str | None = None) -> None: ...


def _locator_payload(target: Locator) -> dict[str, Any]:
    if isinstance(target, ByRef):
        try:
            _gen, index = split_page_ref(target.ref)
        except ValueError:
            index = -1
        return {"kind": "ref", "index": index, "ref": target.ref}
    if isinstance(target, ByCss):
        return {"kind": "css", "css": target.css, "nth": 0}
    if isinstance(target, ByText):
        return {
            "kind": "text",
            "text": target.text,
            "nth": target.nth,
            "exact": target.exact,
        }
    if isinstance(target, ByRole):
        return {
            "kind": "role",
            "role": target.role,
            "name": target.name,
            "nth": target.nth,
            "exact": target.exact,
        }
    raise TypeError(f"unknown locator: {type(target)!r}")


@dataclass
class _FakePage:
    url: str
    title: str
    nodes: list[PageNode] = field(default_factory=list)
    excerpt: str = ""
    article: str = ""
    scroll_y: int = 0
    links: dict[str, str] = field(default_factory=dict)
    frames: tuple[FrameInfo, ...] = ()


class FakePageDriver:
    """In-memory driver for unit/fixture scenarios (no network, no Qt)."""

    def __init__(self, pages: dict[str, _FakePage] | None = None) -> None:
        self._pages = dict(pages or {})
        self._history: list[str] = ["about:blank"]
        self._index = 0
        self._scroll_x = 0
        self._scroll_y = 0
        self._phase = BrowserPhase.READY
        self._last_error: str | None = None
        self._playing = False
        self._wait_queue: list[str] = []
        self.phases_seen: list[BrowserPhase] = []
        self.try_play_calls = 0
        self._gone: set[int] = set()
        self._ensure_blank()

    def mark_disconnected(self, index: int) -> None:
        self._gone.add(int(index))

    def queue_wait(self, result: str) -> None:
        self._wait_queue.append(result)

    def crash(self, status: str = "abnormal") -> None:
        if _is_normal_termination(status):
            return
        self._set_phase(BrowserPhase.FAULTED)
        self._last_error = recovery_text("crash")

    def mark_fault(self, message: str) -> None:
        self._set_phase(BrowserPhase.FAULTED)
        self._last_error = message

    def _set_phase(self, phase: BrowserPhase) -> None:
        self._phase = phase
        self.phases_seen.append(phase)

    def _apply_wait(self, fail_name: str, *, deadline: float | None) -> None:
        default = NAV_WAIT_SEC if fail_name == "navigate" else RELOAD_WAIT_SEC
        if remaining_wait(deadline, default) <= 0:
            self.mark_fault(recovery_text(fail_name))
            raise TimeoutError(self._last_error)
        outcome = self._wait_queue.pop(0) if self._wait_queue else "ok"
        self._set_phase(BrowserPhase.BUSY)
        self._last_error = None
        if outcome == "timeout":
            self.mark_fault(recovery_text(fail_name))
            raise TimeoutError(self._last_error)
        if outcome in ("blank", "fail"):
            self.mark_fault(recovery_text("blank"))
            raise RuntimeError(self._last_error)
        if outcome == "crash":
            self.crash("abnormal")
            raise RuntimeError(self._last_error)

    def _ensure_blank(self) -> None:
        if "about:blank" not in self._pages:
            self._pages["about:blank"] = _FakePage(url="about:blank", title="")

    def _current(self) -> _FakePage:
        url = self._history[self._index]
        page = self._pages.get(url)
        if page is None:
            page = _FakePage(url=url, title=url)
            self._pages[url] = page
        return page

    def register_page(self, page: _FakePage) -> None:
        self._pages[page.url] = page

    def read_snapshot(self) -> BrowserSnapshot:
        page = self._current()
        return BrowserSnapshot(
            url=self._history[self._index],
            title=page.title,
            phase=self._phase,
            can_go_back=self._index > 0,
            can_go_forward=self._index < len(self._history) - 1,
            scroll_x=self._scroll_x,
            scroll_y=self._scroll_y,
            last_error=self._last_error,
            nodes=tuple(page.nodes),
            excerpt=page.excerpt,
            media=self.read_media(),
            frames=tuple(getattr(page, "frames", ()) or ()),
        )

    def settle_after_act(self) -> None:
        return

    def read_text(self, *, scope: str, ref: str | None, max_chars: int) -> str:
        page = self._current()
        cap = max(1, min(int(max_chars), EXTRACT_MAX))
        if scope == "document":
            body = page.article or page.excerpt or page.title
            return body[:cap]
        if ref:
            try:
                _gen, index = split_page_ref(ref)
            except ValueError:
                return ""
            if 0 <= index < len(page.nodes):
                return (page.nodes[index].name or "")[:cap]
        body = page.article or page.excerpt or page.title
        return body[:cap]

    def read_media(self) -> MediaState:
        watch = "/watch" in self._history[self._index]
        return MediaState(
            playing=bool(self._playing and watch),
            paused=not (self._playing and watch),
            current_time=1.0 if self._playing and watch else 0.0,
            ready_state=4 if watch else 0,
            kind="video" if watch else "",
        )

    def navigate(self, url: str, *, deadline: float | None = None) -> None:
        self._apply_wait("navigate", deadline=deadline)
        url = self._resolve_search(url)
        if url != self._history[self._index]:
            self._history = self._history[: self._index + 1]
            self._history.append(url)
            self._index = len(self._history) - 1
        self._scroll_x = 0
        self._scroll_y = 0
        self._gone.clear()
        if "/watch" not in url:
            self._playing = False
        page = self._current()
        page.scroll_y = 0
        self._set_phase(BrowserPhase.READY)

    def first_watch_url(self, *, deadline: float | None = None) -> str:
        if remaining_wait(deadline, 1.0) <= 0:
            return ""
        page = self._current()
        for dest in page.links.values():
            if "/watch" in dest:
                return dest
        return ""

    def try_play(self, *, deadline: float | None = None) -> str:
        self.try_play_calls += 1
        if remaining_wait(deadline, 1.0) <= 0:
            return recovery_text("play")
        url = self._history[self._index]
        if "/watch" in url:
            self._playing = True
            return ""
        return "not a watch page"

    def try_pause(self) -> str:
        if "/watch" not in self._history[self._index]:
            return "not a watch page"
        self._playing = False
        return ""

    def _resolve_search(self, url: str) -> str:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        path = parsed.path or ""
        q = ""
        if "youtube.com" in host and path.startswith("/results"):
            q = (parse_qs(parsed.query).get("search_query") or [""])[0]
        elif (
            "duckduckgo.com" in host
            or ("google." in host and "/search" in path)
            or path.endswith("/search")
        ):
            q = (parse_qs(parsed.query).get("q") or [""])[0]
        else:
            return url
        results = self._pages.get("__search__")
        if results is not None:
            results.title = f"Search: {q}"
            return results.url
        return url

    def reload(self, *, deadline: float | None = None) -> None:
        self._apply_wait("reload", deadline=deadline)
        self._gone.clear()
        self._set_phase(BrowserPhase.READY)

    def history_step(self, delta: int) -> None:
        nxt = self._index + int(delta)
        if nxt < 0 or nxt >= len(self._history):
            raise LookupError("history edge")
        self._index = nxt
        self._scroll_y = self._current().scroll_y
        self._phase = BrowserPhase.READY

    def _raise_if_gone(self, target: Locator) -> None:
        if not isinstance(target, ByRef):
            return
        try:
            _gen, index = split_page_ref(target.ref)
        except ValueError as exc:
            raise LookupError("bad_ref") from exc
        if index in self._gone:
            raise LookupError("stale_ref")

    def click(self, target: Locator) -> None:
        self._raise_if_gone(target)
        page = self._current()
        key = _fake_locator_key(target)
        dest = page.links.get(key)
        if dest is None and isinstance(target, ByRef):
            try:
                _gen, index = split_page_ref(target.ref)
            except ValueError as exc:
                raise LookupError("element not found") from exc
            if 0 <= index < len(page.nodes):
                name = page.nodes[index].name
                dest = page.links.get(f"text:{name}") or page.links.get(name)
        if dest is None:
            for node in page.nodes:
                if _node_matches(node, target):
                    dest = page.links.get(node.name) or page.links.get(f"text:{node.name}")
                    if dest:
                        break
        if not dest:
            raise LookupError("element not found")
        self._last_error = None
        self.navigate(dest)

    def type_text(self, target: Locator, text: str, *, clear: bool) -> None:
        self._raise_if_gone(target)
        page = self._current()
        key = _fake_locator_key(target)
        named = any(_node_matches(node, target) for node in page.nodes)
        if isinstance(target, ByRef):
            try:
                _gen, index = split_page_ref(target.ref)
                named = named or (0 <= index < len(page.nodes))
            except ValueError:
                named = False
        if key not in page.links and not named:
            raise LookupError("element not found")
        page.links[f"typed:{key}"] = text if not clear else text
        self._last_error = None
        self._phase = BrowserPhase.READY

    def scroll_by(self, dx: int, dy: int, *, ref: str | None = None) -> None:
        if ref:
            try:
                _gen, index = split_page_ref(ref)
            except ValueError as exc:
                raise LookupError("bad_ref") from exc
            page = self._current()
            if index in self._gone:
                raise LookupError("stale_ref")
            if index < 0 or index >= len(page.nodes):
                raise LookupError("unknown_ref")
            node = page.nodes[index]
            page.nodes[index] = replace(node, in_view=True)
            self._scroll_y = max(self._scroll_y, 1)
            page.scroll_y = self._scroll_y
            self._phase = BrowserPhase.READY
            self._last_error = None
            return
        self._scroll_x = max(0, self._scroll_x + int(dx))
        self._scroll_y = max(0, self._scroll_y + int(dy))
        self._current().scroll_y = self._scroll_y
        self._phase = BrowserPhase.READY
        self._last_error = None


def _fake_locator_key(target: Locator) -> str:
    if isinstance(target, ByCss):
        return f"css:{target.css}"
    if isinstance(target, ByText):
        return f"text:{target.text}"
    if isinstance(target, ByRole):
        return f"role:{target.role}:{target.name or ''}"
    if isinstance(target, ByRef):
        return f"ref:{target.ref}"
    return repr(target)


def _node_matches(node: PageNode, target: Locator) -> bool:
    if isinstance(target, ByText):
        if target.exact:
            return node.name == target.text
        return target.text.lower() in node.name.lower()
    if isinstance(target, ByRole):
        if node.role != target.role:
            return False
        if not target.name:
            return True
        if target.exact:
            return node.name == target.name
        return target.name.lower() in node.name.lower()
    return False


def youtube_like_fixture_driver() -> FakePageDriver:
    search = _FakePage(
        url="https://fixture.local/search",
        title="Search: IU night letter",
        nodes=[
            PageNode(ref="", role="link", name="IU - 밤편지 (Night Letter)", interactive=True),
            PageNode(ref="", role="link", name="Other result", interactive=True),
        ],
        links={
            "text:IU": "https://fixture.local/watch?v=fixture-iu",
            "text:IU - 밤편지 (Night Letter)": "https://fixture.local/watch?v=fixture-iu",
            "role:link:IU - 밤편지 (Night Letter)": "https://fixture.local/watch?v=fixture-iu",
            "css:a#video-title": "https://fixture.local/watch?v=fixture-iu",
            "css:a.yt-simple-endpoint[href*='/watch']": "https://fixture.local/watch?v=fixture-iu",
            "css:a[href*='/watch?v=']": "https://fixture.local/watch?v=fixture-iu",
        },
    )
    watch = _FakePage(
        url="https://fixture.local/watch?v=fixture-iu",
        title="IU - 밤편지 (Night Letter) - YouTube",
        nodes=[PageNode(ref="", role="heading", name="IU - 밤편지", interactive=False)],
    )
    react = _FakePage(
        url="https://fixture.local/react-docs",
        title="React",
        nodes=[PageNode(ref="", role="heading", name="React", interactive=False)],
    )
    tall = _FakePage(
        url="https://fixture.local/tall",
        title="Tall page",
        nodes=[PageNode(ref="", role="button", name="Below fold", interactive=True, in_view=False)],
    )
    driver = FakePageDriver(
        {
            search.url: search,
            watch.url: watch,
            react.url: react,
            tall.url: tall,
            "__search__": search,
            "https://react.dev": react,
            "https://react.dev/": react,
            "https://react.dev/learn": tall,
        }
    )
    return driver


def _map_node(item: dict) -> PageNode:
    return PageNode(
        ref="",
        role=str(item.get("role") or ""),
        name=str(item.get("name") or "")[:NAME_CAP],
        interactive=bool(item.get("interactive", True)),
        frame=str(item.get("frame") or ""),
        in_view=bool(item.get("in_view", item.get("inView", True))),
        disabled=bool(item.get("disabled", False)),
        checked=bool(item.get("checked", False)),
        selected=bool(item.get("selected", False)),
        focused=bool(item.get("focused", False)),
        context=str(item.get("context") or ""),
    )


class WebEnginePageDriver:
    """QWebEngineView driver. Construct only on the UI thread."""

    def __init__(
        self,
        view: Any,
        *,
        ui_call: Callable[[Callable[[], Any]], Any] | None = None,
    ) -> None:
        self._view = view
        self._ui_call = ui_call or (lambda fn: fn())
        self._last_error: str | None = None
        self._phase = BrowserPhase.OPENING
        self._bridge_ready = False
        self._nav_pending = False
        self._wait_gate: threading.Event | None = None
        self._renderer_dead = False
        try:
            view.loadStarted.connect(self._on_load_started)
            view.loadFinished.connect(self._on_load_finished)
        except Exception:
            pass
        page_attr = getattr(view, "page", None)
        page = page_attr() if callable(page_attr) else page_attr
        if page is not None:
            try:
                page.renderProcessTerminated.connect(self._on_render_terminated)
            except Exception:
                pass

    def _on_render_terminated(self, status: Any, _code: int = 0) -> None:
        if _is_normal_termination(status):
            return
        self._renderer_dead = True
        self.mark_fault(recovery_text("crash"))
        gate = self._wait_gate
        if gate is not None:
            gate.set()

    def mark_fault(self, message: str) -> None:
        self._last_error = message
        self._phase = BrowserPhase.FAULTED

    def _on_load_started(self, *_a: Any) -> None:
        self._nav_pending = True
        self._bridge_ready = False

    def _on_load_finished(self, *_a: Any) -> None:
        self._nav_pending = False

    def _run_ui(self, fn: Callable[[], Any]) -> Any:
        return self._ui_call(fn)

    def _wait_event(self, done: threading.Event, timeout: float) -> bool:
        """Wait without deadlocking when already on the Qt UI thread."""
        self._wait_gate = done
        try:
            try:
                from PyQt6.QtCore import QThread
                from PyQt6.QtWidgets import QApplication
            except Exception:
                return done.wait(timeout)
            app = QApplication.instance()
            if app is None or QThread.currentThread() is not app.thread():
                return done.wait(timeout)
            deadline = time.monotonic() + timeout
            while not done.is_set():
                if time.monotonic() >= deadline:
                    return False
                app.processEvents()
                time.sleep(0.01)
            return True
        finally:
            if self._wait_gate is done:
                self._wait_gate = None

    def _eval_js(self, code: str, *, timeout: float = 8.0, deadline: float | None = None) -> Any:
        wait = remaining_wait(deadline, timeout)
        if wait <= 0:
            raise TimeoutError("javascript timeout")
        box: dict[str, Any] = {}
        done = threading.Event()

        def start() -> None:
            page = self._view.page()

            def cb(result: Any) -> None:
                box["v"] = result
                done.set()

            page.runJavaScript(code, cb)

        self._run_ui(start)
        fired = self._wait_event(done, wait)
        if self._renderer_dead:
            raise RuntimeError(self._last_error or recovery_text("crash"))
        if not fired:
            raise TimeoutError("javascript timeout")
        return box.get("v")

    def _ensure_bridge(self) -> None:
        if self._bridge_ready:
            return
        self._eval_js(_BRIDGE_JS)
        self._bridge_ready = True

    def read_snapshot(self) -> BrowserSnapshot:
        try:
            self._ensure_bridge()
            raw = self._eval_js("window.__irisBrowser.snapshot()")
        except Exception as exc:
            return BrowserSnapshot(
                url="",
                title="",
                phase=BrowserPhase.FAULTED,
                can_go_back=False,
                can_go_forward=False,
                scroll_x=0,
                scroll_y=0,
                last_error=str(exc),
            )

        def hist_flags() -> tuple[bool, bool, str, str]:
            hist = self._view.history()
            url = ""
            title = ""
            try:
                url = str(self._view.url().toString() or "")
                title = str(self._view.title() or "")
            except Exception:
                pass
            return bool(hist.canGoBack()), bool(hist.canGoForward()), url, title

        can_back, can_fwd, url, title = self._run_ui(hist_flags)
        data = raw if isinstance(raw, dict) else {}
        raw_nodes = data.get("nodes") or data.get("landmarks") or []
        nodes = tuple(_map_node(item) for item in raw_nodes if isinstance(item, dict))
        raw_frames = data.get("frames") or ()
        frames = tuple(
            FrameInfo(
                id=str(item.get("id") or ""),
                origin=str(item.get("origin") or ""),
                reachable=bool(item.get("reachable")),
                reason=str(item.get("reason") or ""),
            )
            for item in raw_frames
            if isinstance(item, dict)
        )
        excerpt = str(data.get("excerpt") or "")[:EXCERPT_CAP]
        phase = self._phase
        if self._last_error or phase == BrowserPhase.FAULTED:
            phase = BrowserPhase.FAULTED
        return BrowserSnapshot(
            url=str(data.get("url") or url or ""),
            title=str(data.get("title") or title or ""),
            phase=phase,
            can_go_back=can_back,
            can_go_forward=can_fwd,
            scroll_x=int(data.get("scrollX") or 0),
            scroll_y=int(data.get("scrollY") or 0),
            last_error=self._last_error,
            nodes=nodes,
            excerpt=excerpt,
            media=media_from_dict(data.get("media")),
            frames=frames,
        )

    def settle_after_act(self) -> None:
        if not self._nav_pending:
            time.sleep(0.3)
            return
        done = threading.Event()

        def arm() -> None:
            if not self._nav_pending:
                done.set()
                return

            def finished(_ok: bool) -> None:
                try:
                    self._view.loadFinished.disconnect(finished)
                except Exception:
                    pass
                done.set()

            self._view.loadFinished.connect(finished)
            if not self._nav_pending:
                try:
                    self._view.loadFinished.disconnect(finished)
                except Exception:
                    pass
                done.set()

        self._run_ui(arm)
        self._wait_event(done, 45.0)
        self._nav_pending = False
        self._bridge_ready = False
        self._ensure_bridge()

    def read_text(self, *, scope: str, ref: str | None, max_chars: int) -> str:
        self._ensure_bridge()
        index = None
        if ref:
            try:
                _gen, index = split_page_ref(ref)
            except ValueError:
                index = None
        payload = json.dumps(
            {
                "scope": scope,
                "index": index,
                "maxChars": max(1, min(int(max_chars), EXTRACT_MAX)),
            }
        )
        try:
            raw = self._eval_js(f"window.__irisBrowser.extract({payload})")
        except Exception as exc:
            log.warning("extract js failed: %s", exc)
            return ""
        if not isinstance(raw, dict):
            return ""
        return str(raw.get("text") or "")[:EXTRACT_MAX]

    def _current_url(self) -> str:
        try:
            return str(self._view.url().toString() or "")
        except Exception:
            return ""

    def _wait_load(self, start: Callable[[], None], *, timeout: float, fail_name: str) -> None:
        if timeout <= 0:
            self.mark_fault(recovery_text(fail_name))
            raise TimeoutError(self._last_error)
        self._phase = BrowserPhase.BUSY
        self._last_error = None
        self._renderer_dead = False
        self._bridge_ready = False
        done = threading.Event()
        ok_box: dict[str, bool] = {}

        def finished(ok: bool) -> None:
            ok_box["ok"] = bool(ok)
            try:
                self._view.loadFinished.disconnect(finished)
            except Exception:
                pass
            done.set()

        def arm() -> None:
            self._view.loadFinished.connect(finished)
            start()

        self._run_ui(arm)
        fired = self._wait_event(done, timeout)
        if self._renderer_dead:
            raise RuntimeError(self._last_error or recovery_text("crash"))
        if not fired:
            self.mark_fault(recovery_text(fail_name))
            log.error("%s timeout", fail_name)
            raise TimeoutError(self._last_error)
        if not ok_box.get("ok", True):
            # Redirects and aborted intermediates often fire loadFinished(False)
            # while the final document is fine. Accept if we left about:blank.
            landed = self._run_ui(self._current_url)
            if not landed or landed in ("about:blank", "about:blank#blocked"):
                self.mark_fault(recovery_text("blank"))
                log.error("%s failed blank url=%s", fail_name, landed)
                raise RuntimeError(self._last_error)
            log.warning("loadFinished(False) but landed url=%s", landed)
        self._phase = BrowserPhase.READY

    def navigate(self, url: str, *, deadline: float | None = None) -> None:
        from PyQt6.QtCore import QUrl

        timeout = remaining_wait(deadline, NAV_WAIT_SEC)

        def start() -> None:
            self._view.load(QUrl(url))

        self._wait_load(start, timeout=timeout, fail_name="navigate")
        time.sleep(0.15)
        self._ensure_bridge()
        log.info("navigated url=%s", url)

    def first_watch_url(self, *, deadline: float | None = None) -> str:
        self._ensure_bridge()
        try:
            raw = self._eval_js("window.__irisBrowser.firstWatchUrl()", deadline=deadline)
        except Exception as exc:
            log.warning("firstWatchUrl js failed: %s", exc)
            return ""
        href = str(raw or "").strip()
        if href.startswith("https://") and "/watch" in href:
            return href
        return ""

    def try_play(self, *, deadline: float | None = None) -> str:
        if remaining_wait(deadline, 16.0) <= 0:
            return recovery_text("play")
        self._ensure_bridge()
        try:
            raw = self._eval_js("window.__irisBrowser.tryPlay()", timeout=16.0, deadline=deadline)
        except Exception as exc:
            log.warning("tryPlay js failed: %s", exc)
            return f"play script failed: {exc}"
        if not isinstance(raw, dict):
            return "play script returned nothing"
        if raw.get("ok") and raw.get("playing"):
            return ""
        if self._click_player():
            pause = remaining_wait(deadline, 0.7)
            if pause > 0:
                time.sleep(pause)
            try:
                again = self._eval_js("window.__irisBrowser.mediaState()", timeout=4.0, deadline=deadline)
            except Exception:
                again = None
            st = media_from_dict(again)
            if st is not None and st.playing:
                return ""
        err = str(raw.get("error") or raw.get("block") or "autoplay")
        log.warning("tryPlay blocked: %s", err)
        return err

    def _click_player(self) -> bool:
        """Qt mouse click — YouTube treats JS play() as non-gesture."""
        try:
            box = self._eval_js("window.__irisBrowser.playerBox()")
        except Exception:
            box = None
        x, y = 0, 0
        if isinstance(box, (list, tuple)) and len(box) >= 4:
            x = int(box[0] + max(8, int(box[2]) / 2))
            y = int(box[1] + max(8, int(box[3]) / 2))

        def go() -> bool:
            from PyQt6.QtCore import QPoint, Qt
            from PyQt6.QtTest import QTest

            view = self._view
            if view is None:
                return False
            view.setFocus()
            w = max(1, int(view.width()))
            h = max(1, int(view.height()))
            px = x if x > 0 else w // 2
            py = y if y > 0 else h // 3
            QTest.mouseClick(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(px, py))
            return True

        try:
            return bool(self._run_ui(go))
        except Exception as exc:
            log.warning("player click failed: %s", exc)
            return False

    def try_pause(self) -> str:
        self._ensure_bridge()
        try:
            raw = self._eval_js("window.__irisBrowser.tryPause()")
        except Exception as exc:
            log.warning("tryPause js failed: %s", exc)
            return f"pause script failed: {exc}"
        if not isinstance(raw, dict):
            return "pause script returned nothing"
        if raw.get("ok"):
            return ""
        return str(raw.get("error") or raw.get("block") or "pause failed")

    def reload(self, *, deadline: float | None = None) -> None:
        timeout = remaining_wait(deadline, RELOAD_WAIT_SEC)

        def start() -> None:
            self._view.reload()

        self._wait_load(start, timeout=timeout, fail_name="reload")
        self._ensure_bridge()

    def history_step(self, delta: int) -> None:
        self._phase = BrowserPhase.BUSY
        self._bridge_ready = False

        def step() -> bool:
            hist = self._view.history()
            if delta < 0:
                if not hist.canGoBack():
                    return False
                hist.back()
                return True
            if not hist.canGoForward():
                return False
            hist.forward()
            return True

        ok = bool(self._run_ui(step))
        if not ok:
            self._phase = BrowserPhase.READY
            raise LookupError("history edge")
        time.sleep(0.15)
        self._phase = BrowserPhase.READY
        self._ensure_bridge()

    def _raise_js_act(self, raw: Any, fallback: str) -> None:
        if isinstance(raw, dict) and raw.get("ok"):
            return
        err = str((raw or {}).get("error") if isinstance(raw, dict) else fallback)
        if err in _REF_MISS:
            raise LookupError(err)
        self._last_error = err
        self._phase = BrowserPhase.FAULTED
        raise LookupError(err)

    def click(self, target: Locator) -> None:
        self._ensure_bridge()
        payload = json.dumps(_locator_payload(target))
        raw = self._eval_js(f"window.__irisBrowser.click({payload})")
        self._raise_js_act(raw, "click failed")
        self._last_error = None
        self._phase = BrowserPhase.READY

    def type_text(self, target: Locator, text: str, *, clear: bool) -> None:
        self._ensure_bridge()
        payload = json.dumps(_locator_payload(target))
        text_js = json.dumps(text)
        raw = self._eval_js(
            f"window.__irisBrowser.type({payload}, {text_js}, {json.dumps(bool(clear))})"
        )
        self._raise_js_act(raw, "type failed")
        self._last_error = None
        self._phase = BrowserPhase.READY

    def scroll_by(self, dx: int, dy: int, *, ref: str | None = None) -> None:
        self._ensure_bridge()
        if ref:
            payload = json.dumps(_locator_payload(ByRef(ref=ref)))
            raw = self._eval_js(f"window.__irisBrowser.scrollTo({payload})")
            self._raise_js_act(raw, "scroll failed")
            self._last_error = None
            self._phase = BrowserPhase.READY
            return
        raw = self._eval_js(f"window.__irisBrowser.scrollBy({int(dx)}, {int(dy)})")
        if not isinstance(raw, dict) or not raw.get("ok"):
            self._last_error = "scroll failed"
            self._phase = BrowserPhase.FAULTED
            raise RuntimeError("scroll failed")
        self._last_error = None
        self._phase = BrowserPhase.READY
