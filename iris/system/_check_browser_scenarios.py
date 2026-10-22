"""Browser automation scenarios — fixture mode (default) or IRIS_BROWSER_LIVE=1.

Fixture mode uses FakePageDriver (no network). Live mode is optional.
"""

from __future__ import annotations

import ast
import os
import sys
import tempfile
from pathlib import Path

from iris.browser._driver import youtube_like_fixture_driver
from iris.browser.registry import control_action_names
from iris.browser.session import BrowserSession
from iris.browser.types import ByText, Click, Navigate, Scroll, Search
from iris.system.control_surface import runs_off_ui_thread


ROOT = Path(__file__).resolve().parents[2]


def _check_no_playwright_in_control_actions() -> None:
    path = ROOT / "iris" / "ui" / "control_actions" / "browser.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "playwright" not in alias.name.lower(), alias.name
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "playwright" not in node.module.lower(), node.module


def _check_off_ui_and_catalog() -> None:
    names = control_action_names()
    assert "browser.search" in names
    assert "browser.open" in names
    assert "browser.mini_player" in names
    assert "browser.media" in names
    for name in names:
        assert runs_off_ui_thread(name), name
    assert runs_off_ui_thread("browser.click")
    assert runs_off_ui_thread("browser.mini_player")


def _run_fixture_scenarios() -> None:
    driver = youtube_like_fixture_driver()
    session = BrowserSession(driver=driver)

    r = session.execute(Search(query="IU night letter"))
    assert r.ok, r.detail
    r = session.execute(Click(target=ByText(text="IU")))
    assert r.ok, r.detail
    assert "fixture-iu" in r.snapshot.url
    assert "IU" in r.snapshot.title or any("IU" in lm.name for lm in r.snapshot.landmarks)
    print("scenario A search→click ok")

    r = session.execute(Search(query="IU night letter", engine="youtube", play=True))
    assert r.ok, r.detail
    assert "fixture-iu" in r.snapshot.url
    assert r.snapshot.media and r.snapshot.media.playing
    print("scenario A2 youtube play ok")

    from iris.browser.types import Media

    paused = session.execute(Media(action="pause"))
    assert paused.ok and paused.snapshot.media and not paused.snapshot.media.playing
    resumed = session.execute(Media(action="resume"))
    assert resumed.ok and resumed.snapshot.media and resumed.snapshot.media.playing
    print("scenario A2b pause/resume ok")

    r = session.execute(Search(query="React docs", engine="google"))
    assert r.ok, r.detail
    print("scenario A3 google search fixture ok")

    r = session.execute(Navigate(url="https://react.dev"))
    assert r.ok, r.detail
    assert "react" in r.snapshot.url.lower()
    assert r.snapshot.title == "React"
    print("scenario B navigate react.dev fixture ok")

    session.execute(Navigate(url="https://react.dev/learn"))
    before = session.snapshot().scroll_y
    r = session.execute(Scroll(delta_y=800))
    assert r.ok, r.detail
    assert r.snapshot.scroll_y > before, (before, r.snapshot.scroll_y)
    print("scenario C scroll increases scroll_y ok")


def _run_webengine_smoke() -> None:
    """Real QWebEngine: local HTML navigate + scroll (no third-party net)."""
    import sys
    import tempfile
    from pathlib import Path

    from PyQt6.QtWidgets import QApplication

    from iris.browser.session import BrowserSession
    from iris.browser.types import Navigate, Scroll
    from iris.ui.browser.panel import BrowserPanel
    from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)
    html = (
        "<!doctype html><html><head><title>IRIS Browser Smoke</title></head>"
        "<body style='height:4000px'><h1>smoke</h1></body></html>"
    )
    path = Path(tempfile.gettempdir()) / "iris_browser_smoke.html"
    path.write_text(html, encoding="utf-8")
    url = path.resolve().as_uri()

    session = BrowserSession()
    panel = BrowserPanel(session)
    panel.show()
    view = panel.ensure_view()
    from iris.browser._driver import WebEnginePageDriver

    session.set_driver(WebEnginePageDriver(view))
    r = session.execute(Navigate(url=url))
    assert r.ok, r.detail
    assert "iris_browser_smoke" in r.snapshot.url or r.snapshot.title == "IRIS Browser Smoke"
    before = r.snapshot.scroll_y
    r = session.execute(Scroll(delta_y=600))
    assert r.ok, r.detail
    assert r.snapshot.scroll_y > before, (before, r.snapshot.scroll_y)
    panel.close()
    print("webengine smoke navigate+scroll ok")


def _run_live_optional() -> None:
    if os.environ.get("IRIS_BROWSER_LIVE", "").strip() not in ("1", "true", "yes"):
        print("live net skipped (set IRIS_BROWSER_LIVE=1 for react.dev)")
        return
    os.environ.setdefault(
        "IRIS_BROWSER_PROFILE",
        str(Path(tempfile.gettempdir()) / "iris-browser-live-profile"),
    )
    import sys

    from PyQt6.QtWidgets import QApplication

    from iris.browser.session import BrowserSession
    from iris.browser.types import Navigate, Scroll, Search
    from iris.ui.browser.panel import BrowserPanel
    from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)
    session = BrowserSession()
    panel = BrowserPanel(session)
    panel.show()
    view = panel.ensure_view()
    from iris.browser._driver import WebEnginePageDriver

    session.set_driver(WebEnginePageDriver(view))
    r = session.execute(Navigate(url="https://react.dev"))
    assert r.ok, r.detail
    assert "react.dev" in r.snapshot.url.lower(), r.snapshot.url
    before = r.snapshot.scroll_y
    r = session.execute(Scroll(delta_y=800))
    assert r.ok and r.snapshot.scroll_y >= before
    print("live react.dev navigate+scroll ok")

    r = session.execute(Search(query="React 공식 문서", engine="google"))
    print(
        "live google search",
        "ok" if r.ok else "FAIL",
        r.snapshot.url,
        r.snapshot.title,
        r.detail or r.snapshot.last_error or "",
    )
    r = session.execute(Search(query="음악", engine="youtube", play=True))
    title = (r.snapshot.title or "").encode("ascii", "replace").decode("ascii")
    print(
        "live youtube play",
        "ok" if r.ok else "FAIL",
        r.snapshot.url,
        title,
        r.detail or r.snapshot.last_error or "",
    )
    panel.close()


def _isolate_check_profile() -> None:
    os.environ.setdefault("IRIS_BROWSER_PROFILE_NAME", f"iris-browser-check-{os.getpid()}")
    os.environ.setdefault(
        "IRIS_BROWSER_PROFILE",
        str(Path(tempfile.gettempdir()) / f"iris-browser-check-{os.getpid()}"),
    )


def main() -> int:
    _isolate_check_profile()
    _check_no_playwright_in_control_actions()
    _check_off_ui_and_catalog()
    _run_fixture_scenarios()
    if os.environ.get("IRIS_BROWSER_LIVE", "").strip() in ("1", "true", "yes"):
        _run_live_optional()
    else:
        _run_webengine_smoke()
    print("browser scenarios ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
