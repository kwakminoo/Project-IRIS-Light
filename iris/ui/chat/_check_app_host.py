"""App Host Phase 1: fixture load + ping/pong handshake."""

from __future__ import annotations

import sys

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication, QWidget

from iris.ui.chat.app_host_bridge import (
    METHOD_PING,
    METHOD_PONG,
    AppHostMessage,
    AppHostOffer,
    AppHostPhase,
    parse_message,
    pong_for,
    serialize_message,
)
from iris.ui.chat.app_host_card import AppHostCard, fixture_ping_html
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.qt_bootstrap import ensure_qt_webengine_ready


def _check_bridge_roundtrip() -> None:
    ping = AppHostMessage(method=METHOD_PING, params={"from": "check"}, id=7)
    raw = serialize_message(ping)
    parsed = parse_message(raw)
    assert parsed is not None
    assert parsed.method == METHOD_PING
    assert parsed.params == {"from": "check"}
    assert parsed.id == 7
    pong = pong_for(parsed)
    assert pong.method == METHOD_PONG
    assert pong.id == 7
    assert parse_message("") is None
    assert parse_message("{not-json") is None


def _wait_handshake(card, timeout_ms: int = 15000) -> bool:
    if card.handshake_complete:
        return True
    loop = QEventLoop()
    timed_out = {"v": False}

    def _on_ok() -> None:
        loop.quit()

    def _on_timeout() -> None:
        timed_out["v"] = True
        loop.quit()

    card.handshake_ok.connect(_on_ok)
    QTimer.singleShot(timeout_ms, _on_timeout)
    loop.exec()
    return card.handshake_complete and not timed_out["v"]


def _check_card_handshake(app: QApplication) -> None:
    fixture = fixture_ping_html()
    assert fixture.is_file(), f"missing fixture: {fixture}"

    host = QWidget()
    host.resize(480, 640)
    card = AppHostCard(host)
    card.setFixedHeight(240)
    offer = AppHostOffer(title="앱", html_path=str(fixture))
    assert card.show_offer(offer) is True
    assert card.phase is AppHostPhase.LOADING
    assert _wait_handshake(card), (
        f"handshake timeout phase={card.phase.value} pong={card._pong_delivered}"
    )
    assert card.phase is AppHostPhase.READY
    assert card.handshake_complete
    from PyQt6.QtWebEngineCore import QWebEngineSettings

    for attr in (
        QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
        QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
        QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard,
        QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
        QWebEngineSettings.WebAttribute.PluginsEnabled,
    ):
        assert not card._view.settings().testAttribute(attr)

    panel = ChatPanel()
    panel.resize(480, 640)
    assert hasattr(panel, "show_app_host")
    assert panel.show_app_host(str(fixture), title="앱") is True
    app_card = getattr(panel, "_app_host_card", None)
    assert app_card is not None
    # Parent panel may be hidden in headless check; card itself must not stay hidden.
    assert not app_card.isHidden()
    assert _wait_handshake(app_card), "ChatPanel show_app_host handshake timeout"
    assert app_card.phase is AppHostPhase.READY

    # Chat log must not be the injection surface.
    log_html = panel._log.toHtml()
    assert "app_host_ping" not in log_html
    assert "<iframe" not in log_html.lower()


def main() -> int:
    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)
    _check_bridge_roundtrip()
    _check_card_handshake(app)
    print("app_host handshake ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
