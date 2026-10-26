"""Private page drivers — not part of the public iris.browser API."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
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
    Locator,
    PageNode,
    MediaState,
    media_from_dict,
    split_page_ref,
)

log = logging.getLogger("iris.browser")

_BRIDGE_JS = (Path(__file__).resolve().parent / "_bridge.js").read_text(encoding="utf-8")


def _bbox4(raw: object) -> tuple[int, int, int, int] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        return (int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3]))
    except (TypeError, ValueError):
        return None


class PageDriver(Protocol):
    def read_snapshot(self) -> BrowserSnapshot: ...
    def navigate(self, url: str) -> None: ...
    def reload(self) -> None: ...
    def history_step(self, delta: int) -> None: ...
    def click(self, target: Locator) -> None: ...
    def type_text(self, target: Locator, text: str, *, clear: bool) -> None: ...
    def scroll_by(self, dx: int, dy: int) -> None: ...


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
        self._ensure_blank()

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

    def navigate(self, url: str) -> None:
        self._phase = BrowserPhase.BUSY
        self._last_error = None
        url = self._resolve_search(url)
        if url != self._history[self._index]:
            self._history = self._history[: self._index + 1]
            self._history.append(url)
            self._index = len(self._history) - 1
        self._scroll_x = 0
        self._scroll_y = 0
        if "/watch" not in url:
            self._playing = False
        page = self._current()
        page.scroll_y = 0
        self._phase = BrowserPhase.READY

    def first_watch_url(self) -> str:
        page = self._current()
        for dest in page.links.values():
            if "/watch" in dest:
                return dest
        return ""

    def try_play(self) -> str:
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

    def reload(self) -> None:
        self._phase = BrowserPhase.BUSY
        self._phase = BrowserPhase.READY

    def history_step(self, delta: int) -> None:
        nxt = self._index + int(delta)
        if nxt < 0 or nxt >= len(self._history):
            raise LookupError("history edge")
        self._index = nxt
        self._scroll_y = self._current().scroll_y
        self._phase = BrowserPhase.READY

    def click(self, target: Locator) -> None:
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
            self._last_error = "element not found"
            self._phase = BrowserPhase.FAULTED
            raise LookupError("element not found")
        self._last_error = None
        self.navigate(dest)

    def type_text(self, target: Locator, text: str, *, clear: bool) -> None:
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
            self._last_error = "element not found"
            self._phase = BrowserPhase.FAULTED
            raise LookupError("element not found")
        page.links[f"typed:{key}"] = text if not clear else text
        self._last_error = None
        self._phase = BrowserPhase.READY

    def scroll_by(self, dx: int, dy: int) -> None:
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
        nodes=[],
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
        try:
            view.loadStarted.connect(self._on_load_started)
            view.loadFinished.connect(self._on_load_finished)
        except Exception:
            pass

    def _on_load_started(self, *_a: Any) -> None:
        self._nav_pending = True
        self._bridge_ready = False

    def _on_load_finished(self, *_a: Any) -> None:
        self._nav_pending = False

    def _run_ui(self, fn: Callable[[], Any]) -> Any:
        return self._ui_call(fn)

    def _wait_event(self, done: threading.Event, timeout: float) -> bool:
        """Wait without deadlocking when already on the Qt UI thread."""
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

    def _eval_js(self, code: str, *, timeout: float = 8.0) -> Any:
        box: dict[str, Any] = {}
        done = threading.Event()

        def start() -> None:
            page = self._view.page()

            def cb(result: Any) -> None:
                box["v"] = result
                done.set()

            page.runJavaScript(code, cb)

        self._run_ui(start)
        if not self._wait_event(done, timeout):
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
        nodes = tuple(
            PageNode(
                ref="",
                role=str(item.get("role") or ""),
                name=str(item.get("name") or "")[:80],
                interactive=bool(item.get("interactive", True)),
            )
            for item in raw_nodes
            if isinstance(item, dict)
        )
        excerpt = str(data.get("excerpt") or "")[:EXCERPT_CAP]
        phase = self._phase
        if self._last_error:
            phase = BrowserPhase.FAULTED
        elif phase == BrowserPhase.BUSY:
            phase = BrowserPhase.BUSY
        elif data.get("readyState") == "complete" or url:
            phase = BrowserPhase.READY
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

    def navigate(self, url: str) -> None:
        from PyQt6.QtCore import QUrl

        self._phase = BrowserPhase.BUSY
        self._last_error = None
        self._bridge_ready = False
        done = threading.Event()
        ok_box: dict[str, bool] = {}

        def start() -> None:
            def finished(ok: bool) -> None:
                ok_box["ok"] = bool(ok)
                try:
                    self._view.loadFinished.disconnect(finished)
                except Exception:
                    pass
                done.set()

            self._view.loadFinished.connect(finished)
            self._view.load(QUrl(url))

        self._run_ui(start)
        if not self._wait_event(done, 45.0):
            self._last_error = "navigate timeout"
            self._phase = BrowserPhase.FAULTED
            log.error("navigate timeout url=%s", url)
            raise TimeoutError("navigate timeout")
        if not ok_box.get("ok", True):
            # Redirects / aborted intermediates often fire loadFinished(False)
            # while the final document is fine — accept if we left about:blank.
            def current_url() -> str:
                try:
                    return str(self._view.url().toString() or "")
                except Exception:
                    return ""

            landed = self._run_ui(current_url)
            if not landed or landed in ("about:blank", "about:blank#blocked"):
                self._last_error = "navigate failed"
                self._phase = BrowserPhase.FAULTED
                log.error("navigate failed url=%s", url)
                raise RuntimeError("navigate failed")
            log.warning("loadFinished(False) but landed url=%s", landed)
        self._phase = BrowserPhase.READY
        time.sleep(0.15)
        self._ensure_bridge()
        log.info("navigated url=%s", url)

    def first_watch_url(self) -> str:
        self._ensure_bridge()
        try:
            raw = self._eval_js("window.__irisBrowser.firstWatchUrl()")
        except Exception as exc:
            log.warning("firstWatchUrl js failed: %s", exc)
            return ""
        href = str(raw or "").strip()
        if href.startswith("https://") and "/watch" in href:
            return href
        return ""

    def try_play(self) -> str:
        """Ask the page video to play. Does not bypass site/autoplay policy."""
        self._ensure_bridge()
        try:
            raw = self._eval_js("window.__irisBrowser.tryPlay()", timeout=16.0)
        except Exception as exc:
            log.warning("tryPlay js failed: %s", exc)
            return f"play script failed: {exc}"
        if not isinstance(raw, dict):
            return "play script returned nothing"
        if raw.get("ok") and raw.get("playing"):
            return ""
        if self._click_player():
            time.sleep(0.7)
            try:
                again = self._eval_js("window.__irisBrowser.mediaState()", timeout=4.0)
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

    def reload(self) -> None:
        self._phase = BrowserPhase.BUSY
        self._bridge_ready = False
        done = threading.Event()

        def start() -> None:
            def finished(_ok: bool) -> None:
                try:
                    self._view.loadFinished.disconnect(finished)
                except Exception:
                    pass
                done.set()

            self._view.loadFinished.connect(finished)
            self._view.reload()

        self._run_ui(start)
        self._wait_event(done, 30.0)
        self._phase = BrowserPhase.READY
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

    def click(self, target: Locator) -> None:
        self._ensure_bridge()
        payload = json.dumps(_locator_payload(target))
        raw = self._eval_js(f"window.__irisBrowser.click({payload})")
        if not isinstance(raw, dict) or not raw.get("ok"):
            err = str((raw or {}).get("error") if isinstance(raw, dict) else "click failed")
            self._last_error = err
            self._phase = BrowserPhase.FAULTED
            raise LookupError(err)
        self._last_error = None
        self._phase = BrowserPhase.READY

    def type_text(self, target: Locator, text: str, *, clear: bool) -> None:
        self._ensure_bridge()
        payload = json.dumps(_locator_payload(target))
        text_js = json.dumps(text)
        raw = self._eval_js(
            f"window.__irisBrowser.type({payload}, {text_js}, {json.dumps(bool(clear))})"
        )
        if not isinstance(raw, dict) or not raw.get("ok"):
            err = str((raw or {}).get("error") if isinstance(raw, dict) else "type failed")
            self._last_error = err
            self._phase = BrowserPhase.FAULTED
            raise LookupError(err)
        self._last_error = None
        self._phase = BrowserPhase.READY

    def scroll_by(self, dx: int, dy: int) -> None:
        self._ensure_bridge()
        raw = self._eval_js(f"window.__irisBrowser.scrollBy({int(dx)}, {int(dy)})")
        if not isinstance(raw, dict) or not raw.get("ok"):
            self._last_error = "scroll failed"
            self._phase = BrowserPhase.FAULTED
            raise RuntimeError("scroll failed")
        self._last_error = None
        self._phase = BrowserPhase.READY
