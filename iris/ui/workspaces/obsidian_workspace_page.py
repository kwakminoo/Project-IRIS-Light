"""Iris Wiki 워크스페이스 — 노트 미리보기."""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QTextBrowser, QVBoxLayout, QWidget

from iris.core.markdown_text import markdown_to_chat_html
from iris.knowledge.iris_wiki import IrisWiki, WIKI_NAME


class ObsidianWorkspacePage(QWidget):
    """중앙 Iris Wiki 미리보기."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ObsidianWorkspacePage")
        self._wiki: IrisWiki | None = None
        self._current_rel = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)

        self._title = QLabel(WIKI_NAME)
        self._title.setObjectName("SectionTitle")
        lay.addWidget(self._title)

        preview_wrap = QWidget()
        preview_wrap.setObjectName("ObsidianPreviewPanel")
        preview_lay = QVBoxLayout(preview_wrap)
        preview_lay.setContentsMargins(0, 0, 0, 0)

        self._body = QTextBrowser()
        self._body.setObjectName("ObsidianPreviewBody")
        self._body.setOpenExternalLinks(True)
        self._body.setReadOnly(True)
        preview_lay.addWidget(self._body)
        lay.addWidget(preview_wrap, 1)

    def set_wiki(self, wiki: IrisWiki) -> None:
        self._wiki = wiki

    def show_note(self, rel_path: str) -> None:
        if not self._wiki:
            return
        rel_path = (rel_path or "").strip()
        if not rel_path:
            return
        try:
            text = self._wiki.read_note(rel_path)
        except OSError:
            self._body.setHtml("<p>노트를 읽을 수 없습니다.</p>")
            return
        self._current_rel = rel_path
        title = rel_path.rsplit("/", 1)[-1].removesuffix(".md")
        self._title.setText(title)
        html = markdown_to_chat_html(text)
        self._body.setHtml(f'<div style="line-height:1.5;">{html}</div>')

    @property
    def current_note(self) -> str:
        return self._current_rel
