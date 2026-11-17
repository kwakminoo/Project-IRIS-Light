"""P2: ChatAppOffer present + 다시 보기 reopen link.

Run: .venv\\Scripts\\python.exe -m iris.ui.chat._check_app_offer_reopen
"""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from PyQt6.QtWidgets import QApplication

from iris.apps.offer import path_offer
from iris.core.message_parts import AppPart
from iris.ui.chat.app_offer_link import app_href, parse_app_href
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.chat_renderer import _chat_url_ok
from iris.ui.qt_bootstrap import ensure_qt_webengine_ready


def main() -> int:
    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)
    _ = app

    href = app_href("abc def")
    assert href.startswith("iris-app://"), href
    assert parse_app_href(href) == "abc def"
    assert parse_app_href("https://example.com") is None
    assert _chat_url_ok("iris-app://abc") is True

    with TemporaryDirectory() as tmp:
        html = Path(tmp) / "offer.html"
        html.write_text(
            "<!DOCTYPE html><html><body>ok</body></html>", encoding="utf-8"
        )
        offer = path_offer("Mini App", str(html), offer_id="reopen01")

        panel = ChatPanel()
        panel.resize(480, 640)
        shown_paths: list[str] = []

        def _fake_show(
            html_path: str, title: str = "앱", *, offer_id: str = ""
        ) -> bool:
            shown_paths.append(html_path)
            _ = offer_id
            return Path(html_path).is_file()

        panel.show_app_host = _fake_show  # type: ignore[method-assign]
        assert panel.present_chat_app_offer(offer) is True
        assert offer.offer_id in panel._chat_app_offers
        assert panel._chat_app_offers[offer.offer_id] is offer
        # Default present path: AppPart on H1 transcript, not App Host slot.
        assert shown_paths == []
        turns = panel.transcript()._turns
        assert turns, "expected transcript turn after present"
        apps = [p for p in turns[-1].parts if isinstance(p, AppPart)]
        assert len(apps) == 1
        assert apps[0].title == "Mini App"
        assert "body>ok</body>" in apps[0].html.replace(" ", "")

        note_html = panel._log.toHtml()
        assert "iris-app://" in note_html, note_html
        assert offer.offer_id in note_html, note_html
        assert "다시 보기" in note_html

        # Explicit reopen still uses the slot card path.
        assert panel.reopen_chat_app_offer(offer.offer_id) is True
        assert shown_paths == [str(html)]
        assert panel.reopen_chat_app_offer("missing") is False

        bad = path_offer("Gone", str(Path(tmp) / "nope.html"), offer_id="gone")
        assert panel.present_chat_app_offer(bad) is False
        assert "gone" not in panel._chat_app_offers

    print("app offer reopen ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
