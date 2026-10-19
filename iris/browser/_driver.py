"""Private page drivers — not part of the public iris.browser API."""

from __future__ import annotations

import json
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
    ByRole,
    ByText,
    Landmark,
    Locator,
)

_BRIDGE_JS = (Path(__file__).resolve().parent / "_bridge.js").read_text(encoding="utf-8")


class PageDriver(Protocol):
    def read_snapshot(self) -> BrowserSnapshot: ...
    def navigate(self, url: str) -> None: ...
    def reload(self) -> None: ...
    def history_step(self, delta: int) -> None: ...
    def click(self, target: Locator) -> None: ...
    def type_text(self, target: Locator, text: str, *, clear: bool) -> None: ...
    def scroll_by(self, dx: int, dy: int) -> None: ...


def _locator_payload(target: Locator) -> dict[str, Any]:
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
    landmarks: list[Landmark] = field(default_factory=list)
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
            landmarks=tuple(page.landmarks),
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
        page = self._current()
        page.scroll_y = 0
        self._phase = BrowserPhase.READY

    def _resolve_search(self, url: str) -> str:
        parsed = urlparse(url)
        if "duckduckgo.com" in (parsed.netloc or "") or parsed.path.endswith("/search"):
            q = (parse_qs(parsed.query).get("q") or [""])[0]
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
        if dest is None:
            for lm in page.landmarks:
                if _landmark_matches(lm, target):
                    dest = page.links.get(lm.name) or page.links.get(f"text:{lm.name}")
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
        if key not in page.links and not any(_landmark_matches(lm, target) for lm in page.landmarks):
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
    return repr(target)


def _landmark_matches(lm: Landmark, target: Locator) -> bool:
    if isinstance(target, ByText):
        if target.exact:
            return lm.name == target.text
        return target.text.lower() in lm.name.lower()
    if isinstance(target, ByRole):
        if lm.role != target.role:
            return False
        if not target.name:
            return True
        if target.exact:
            return lm.name == target.name
        return target.name.lower() in lm.name.lower()
    return False


def youtube_like_fixture_driver() -> FakePageDriver:
    search = _FakePage(
        url="https://fixture.local/search",
        title="Search: IU night letter",
        landmarks=[
            Landmark(role="link", name="IU - 밤편지 (Night Letter)"),
            Landmark(role="link", name="Other result"),
        ],
        links={
            "text:IU": "https://fixture.local/watch?v=fixture-iu",
            "text:IU - 밤편지 (Night Letter)": "https://fixture.local/watch?v=fixture-iu",
            "role:link:IU - 밤편지 (Night Letter)": "https://fixture.local/watch?v=fixture-iu",
        },
    )
    watch = _FakePage(
        url="https://fixture.local/watch?v=fixture-iu",
        title="IU - 밤편지 (Night Letter) - YouTube",
        landmarks=[Landmark(role="heading", name="IU - 밤편지")],
    )
    react = _FakePage(
        url="https://fixture.local/react-docs",
        title="React",
        landmarks=[Landmark(role="heading", name="React")],
    )
    tall = _FakePage(
        url="https://fixture.local/tall",
        title="Tall page",
        landmarks=[],
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
        except Exception as exc:  # noqa: BLE001
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
        landmarks = tuple(
            Landmark(
                role=str(item.get("role") or ""),
                name=str(item.get("name") or ""),
                bbox=tuple(item["bbox"]) if isinstance(item.get("bbox"), list) and len(item["bbox"]) == 4 else None,  # type: ignore[misc]
            )
            for item in (data.get("landmarks") or [])
            if isinstance(item, dict)
        )
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
            landmarks=landmarks,
        )

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
            raise TimeoutError("navigate timeout")
        if not ok_box.get("ok", True):
            self._last_error = "navigate failed"
            self._phase = BrowserPhase.FAULTED
            raise RuntimeError("navigate failed")
        self._phase = BrowserPhase.READY
        time.sleep(0.05)
        self._ensure_bridge()

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
        time.sleep(0.1)

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
