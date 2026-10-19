"""Mini-player self-check — ViewHost reparent, stack stays off browser."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from iris.browser.registry import control_action_names, parse_command
from iris.browser.session import BrowserSession, get_browser_session, reset_browser_session_for_tests
from iris.browser.types import MiniPlayer, Navigate
from iris.browser.youtube import is_youtube_watch_url


def _check_youtube_helper() -> None:
    assert is_youtube_watch_url("https://www.youtube.com/watch?v=abc")
    assert is_youtube_watch_url("https://youtu.be/abc123")
    assert is_youtube_watch_url("https://m.youtube.com/watch?v=abc")
    assert not is_youtube_watch_url("https://www.youtube.com/results?search_query=x")
    assert not is_youtube_watch_url("https://react.dev")
    print("youtube helper ok")


def _check_registry() -> None:
    assert "browser.mini_player" in control_action_names()
    cmd = parse_command({"command": "mini_player", "on": True})
    assert isinstance(cmd, MiniPlayer) and cmd.on is True
    cmd = parse_command({"action": "browser.mini_player", "on": False})
    assert isinstance(cmd, MiniPlayer) and cmd.on is False
    print("mini_player registry ok")


def _check_fixture_host_toggle() -> None:
    from iris.browser._driver import youtube_like_fixture_driver

    driver = youtube_like_fixture_driver()
    session = BrowserSession(driver=driver)
    r = session.execute(MiniPlayer(on=True))
    assert r.ok, r.detail
    assert r.snapshot.mini_player is True
    assert session.view_host() == "mini"
    r = session.execute(MiniPlayer(on=True))
    assert r.detail == "idempotent"
    r = session.execute(MiniPlayer(on=False))
    assert r.ok and r.snapshot.mini_player is False
    assert session.view_host() == "panel"
    print("fixture mini_player toggle ok")


def _check_qt_reparent() -> None:
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWidgets import QApplication

    from iris.browser._driver import WebEnginePageDriver
    from iris.ui.qt_bootstrap import ensure_qt_webengine_ready
    from iris.ui.workspaces.iris_ide_window import IrisIdeWindow

    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)

    html = (
        "<!doctype html><html><head><title>watch fixture</title></head>"
        "<body><h1>mini</h1></body></html>"
    )
    path = Path(tempfile.gettempdir()) / "iris_browser_mini_watch.html"
    path.write_text(html, encoding="utf-8")
    file_url = path.resolve().as_uri()

    reset_browser_session_for_tests()
    session = get_browser_session()
    win = IrisIdeWindow()
    win.show_welcome(show_window=False)
    panel = win.ensure_browser_panel()
    view = panel.ensure_view()
    session.set_driver(WebEnginePageDriver(view))
    session.set_host_applier(win.apply_browser_view_host)
    session.set_ui_call(lambda fn: fn())

    watch_url = "https://www.youtube.com/watch?v=iris-mini-check"
    r = session.execute(Navigate(url=file_url))
    assert r.ok, r.detail
    view.setUrl(QUrl(watch_url))
    app.processEvents()

    win.show_browser(show_window=False)
    assert win.is_browser_visible()
    driver_id = id(session._driver)

    win.show_welcome(show_window=False)
    app.processEvents()
    assert not win.is_browser_visible()
    assert win.is_welcome_visible()
    assert win.is_browser_mini_visible(), "mini should show after leaving watch URL"
    assert session.view_host() == "mini"
    assert session.snapshot().mini_player is True
    assert id(session._driver) == driver_id, "driver must not be recreated on reparent"

    r = session.execute(MiniPlayer(on=False))
    assert r.ok, r.detail
    app.processEvents()
    assert win.is_browser_visible()
    assert not win.is_browser_mini_visible()
    assert session.view_host() == "panel"
    assert id(session._driver) == driver_id

    win.close()
    reset_browser_session_for_tests()
    print("qt mini reparent + welcome stack ok")


def main() -> int:
    _check_youtube_helper()
    _check_registry()
    _check_fixture_host_toggle()
    _check_qt_reparent()
    print("browser mini player ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
