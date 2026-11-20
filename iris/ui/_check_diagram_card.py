"""채팅 다이어그램 카드 자검. WebEngine은 만들지 않는다."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from urllib.parse import quote

from PyQt6.QtCore import QUrl

from iris.ui.chat.diagram_card import (
    card_height_px,
    diagram_href,
    parse_diagram_href,
    present_file_url,
)
from iris.ui.window.diagram_preview import open_diagram_preview


class _FakeChat:
    def __init__(self) -> None:
        self.shown: list[tuple[str, str]] = []
        self.notes: list[tuple[str, str]] = []

    def show_diagram(self, html_path: str, title: str = "") -> bool:
        self.shown.append((html_path, title))
        return Path(html_path).is_file()

    def append_diagram_note(self, html_path: str, title: str = "") -> None:
        self.notes.append((html_path, title))


def _check_height() -> None:
    assert card_height_px(0) == 280
    assert card_height_px(200) == 180
    assert card_height_px(800) == 400
    assert card_height_px(2000) == 420


def _check_url_and_href() -> None:
    url = present_file_url(Path("C:/iris/diagrams/a.html"))
    query = url.query()
    assert "present=1" in query
    assert "embed" not in query
    href = diagram_href(r"C:\iris\a b.html")
    assert href.startswith("iris-diagram://")
    assert parse_diagram_href(href) == r"C:\iris\a b.html"
    assert parse_diagram_href("https://example.com") is None
    # Drive letter + %2F must survive QUrl (opaque host form empties).
    slashy = r"C:\iris\a/b.html"
    href2 = diagram_href(slashy)
    via = QUrl(href2).toString()
    assert via, f"QUrl emptied diagram href: {href2!r}"
    assert parse_diagram_href(via) == slashy, (href2, via)
    # Legacy host form still parses when not emptied by QUrl.
    legacy = "iris-diagram://" + quote(r"C:\iris\a b.html", safe="")
    assert parse_diagram_href(legacy) == r"C:\iris\a b.html"


def _check_preview() -> None:
    with TemporaryDirectory() as tmp:
        html = Path(tmp) / "demo.html"
        html.write_text("<html></html>", encoding="utf-8")
        chat = _FakeChat()
        window = SimpleNamespace(_chat=chat)
        assert open_diagram_preview(window, str(html), title="흐름") is True
        assert chat.shown == [(str(html), "흐름")]
        assert chat.notes == [(str(html), "흐름")]

        missing = _FakeChat()
        assert open_diagram_preview(SimpleNamespace(_chat=missing), str(Path(tmp) / "nope.html")) is False
        assert missing.notes == []
        assert open_diagram_preview(SimpleNamespace(), str(html)) is False


def main() -> int:
    _check_height()
    _check_url_and_href()
    _check_preview()
    print("diagram card ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
