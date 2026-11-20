"""채팅 칸 안의 archify 뷰어 카드.

로그(QTextEdit) 안에 웹뷰를 넣지 않는다. present=1 은 SVG를 칸에 맞추고
테마·경로 버튼을 남긴다. embed=1 은 그 버튼을 숨기므로 쓰지 않는다.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, unquote

from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from iris.ui.shared.theme_tokens import TOKENS

_CARD_MIN = 180
_CARD_MAX = 420
_CARD_DEFAULT = 280
_SCHEME = "iris-diagram://"
# QUrl empties opaque hosts that contain %2F; keep path after a fixed authority mark.
_PATH_MARK = "_/"

# present 모드 헤더의 23rem 오른쪽 패딩만 좁은 칸에서 없앤다. archify 소스는 그대로 둔다.
_FIT_JS = """
(() => {
  document.documentElement.setAttribute('data-present', 'true');
  if (!document.getElementById('iris-diagram-fit')) {
    const style = document.createElement('style');
    style.id = 'iris-diagram-fit';
    style.textContent = 'html[data-present="true"] .header{padding-right:0 !important;}';
    document.head.appendChild(style);
  }
  return true;
})()
"""


def card_height_px(panel_height: int) -> int:
    """채팅 패널 높이의 절반. 180~420. 높이를 모르면 280."""
    height = int(panel_height or 0)
    if height <= 0:
        return _CARD_DEFAULT
    return max(_CARD_MIN, min(_CARD_MAX, height // 2))


def present_file_url(path: Path | str) -> QUrl:
    """로컬 HTML + present=1. embed 는 붙이지 않는다."""
    url = QUrl.fromLocalFile(str(Path(path).resolve()))
    url.setQuery("present=1")
    return url


def diagram_href(path: str) -> str:
    return _SCHEME + _PATH_MARK + quote(str(path or ""), safe="")


def parse_diagram_href(anchor: str) -> str | None:
    raw = anchor or ""
    if not raw.startswith(_SCHEME):
        return None
    body = raw[len(_SCHEME) :]
    if body.startswith(_PATH_MARK):
        body = body[len(_PATH_MARK) :]
    elif body.startswith("/"):
        body = body[1:]
    # else: legacy iris-diagram://{quoted} (ChatLog / old HTML)
    text = unquote(body).strip()
    return text or None


class DiagramCard(QFrame):
    """로그와 입력창 사이의 다이어그램 카드. 웹뷰는 첫 표시 때 하나."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("DiagramCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            "QFrame#DiagramCard {"
            f"background:{TOKENS.space_navy};"
            f"border:1px solid {TOKENS.text_muted};"
            "border-radius:8px;"
            "}"
            "QPushButton#DiagramCardClose {"
            f"color:{TOKENS.text_secondary};"
            "background:transparent;"
            f"border:1px solid {TOKENS.text_muted};"
            "border-radius:4px;"
            "padding:0 8px;"
            "}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(8)
        self._title = QLabel("구조도", self)
        self._title.setStyleSheet(f"color:{TOKENS.text_secondary}; background:transparent; border:0;")
        close = QPushButton("닫기", self)
        close.setObjectName("DiagramCardClose")
        close.setFixedHeight(22)
        close.clicked.connect(self.hide)
        head.addWidget(self._title, 1)
        head.addWidget(close, 0)
        layout.addLayout(head)
        self._view_slot = QWidget(self)
        self._view_slot.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._view_slot, 1)
        self._view = None
        self.hide()

    def show_file(self, path: Path | str, title: str = "") -> None:
        file_path = Path(path)
        label = (title or file_path.stem or "구조도").strip() or "구조도"
        self._title.setText(label)
        view = self._ensure_view()
        view.load(present_file_url(file_path))

    def _ensure_view(self):
        if self._view is not None:
            return self._view
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        view = QWebEngineView(self)
        view.loadFinished.connect(self._on_load_finished)
        layout = self.layout()
        layout.replaceWidget(self._view_slot, view)
        self._view_slot.hide()
        self._view_slot.deleteLater()
        self._view_slot = None
        self._view = view
        return view

    def _on_load_finished(self, ok: bool) -> None:
        if not ok or self._view is None:
            return
        self._view.page().runJavaScript(_FIT_JS)
