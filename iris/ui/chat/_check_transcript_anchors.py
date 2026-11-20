"""H1 link clicks intercept navigation and reach ChatPanel dispatch (ChatLog parity)."""

from __future__ import annotations

import sys

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()

from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.ui.chat import chat_panel as chat_panel_mod
from iris.ui.chat.chat_blocks import copy_anchor_for, file_anchor_for, parse_copy_anchor
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.diagram_card import diagram_href, parse_diagram_href

_NAV = QWebEnginePage.NavigationType.NavigationTypeLinkClicked


def _accept(page: QWebEnginePage, href: str) -> bool:
    return bool(page.acceptNavigationRequest(QUrl(href), _NAV, True))


def main() -> int:
    _ = QApplication.instance() or _APP

    panel = ChatPanel()
    host = panel.transcript()
    assert hasattr(host, "anchor_activated"), "H1TranscriptHost.anchor_activated missing"
    view = host._ensure_view()
    page = view.page()

    activated: list[str] = []
    host.anchor_activated.connect(activated.append)

    updates: list[str] = []
    panel.update_action_clicked.connect(updates.append)
    ollama: list[bool] = []
    panel.ollama_login_clicked.connect(lambda: ollama.append(True))
    speakers: list[str] = []
    panel.speaker_clicked.connect(speakers.append)

    handled: list[str] = []
    real_handle = chat_panel_mod.handle_chat_anchor_click

    def _spy_handle(parent, href: str) -> bool:
        handled.append(href)
        return True

    chat_panel_mod.handle_chat_anchor_click = _spy_handle  # type: ignore[assignment]
    try:
        file_href = file_anchor_for("iris/ui/chat/chat_blocks.py")
        copy_code = "AbC_mixed"
        copy_href = copy_anchor_for(copy_code)
        diagram_path = r"C:\iris\a/b.html"
        diag_href = diagram_href(diagram_path)
        cases = (
            copy_href,
            file_href,
            "http://example.com/docs",
            "iris-update://apply",
            "iris-ollama-login://open",
            "iris-tts://msg-1",
            diag_href,
        )
        for href in cases:
            assert QUrl(href).toString(), f"QUrl must round-trip for check input: {href}"
            assert _accept(page, href) is False, f"must intercept (no navigate): {href}"

        assert len(activated) == len(cases), activated
        # Path-form copy/diagram: exact case and %2F survive H1 emit.
        assert parse_copy_anchor(activated[0]) == copy_code, activated[0]
        assert activated[0] == QUrl(copy_href).toString()
        assert activated[1] == file_href
        assert activated[2] == "http://example.com/docs"
        assert activated[3] == "iris-update://apply"
        assert activated[4] == "iris-ollama-login://open"
        assert activated[5] == "iris-tts://msg-1"
        assert parse_diagram_href(activated[6]) == diagram_path, activated[6]

        assert any(parse_copy_anchor(h) == copy_code for h in handled), handled
        assert file_href in handled, handled
        assert "http://example.com/docs" in handled, handled
        assert updates == ["apply"], updates
        assert ollama == [True], ollama
        assert speakers == ["msg-1"], speakers

        # about:blank / page chrome must still navigate
        assert _accept(page, "about:blank") is True
    finally:
        chat_panel_mod.handle_chat_anchor_click = real_handle  # type: ignore[assignment]

    print("transcript_anchors ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
