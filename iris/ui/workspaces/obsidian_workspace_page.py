"""Iris Wiki 워크스페이스 — 점·선 그래프(중앙) + 노트 정보(우측).

수동 확인 (코드 블록 카드):
  1. IRIS 실행 → Wiki 워크스페이스
  2. ``` fenced code 가 포함된 노트를 그래프에서 선택
  3. 우측 미리보기에 chat_block_radius·mono 폰트 코드 카드가 보이는지 확인
  4. 이미지 클릭 → 라이트박스, http 링크 → 브라우저
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import (
    QLabel,
    QSizePolicy,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from iris.knowledge.iris_wiki import WIKI_NAME, IrisWiki
from iris.ui.chat.chat_image_view import (
    attach_image_loader,
    handle_chat_anchor_click,
    prefetch_chat_html_images,
)
from iris.ui.chat.chat_renderer import render_wiki_document
from iris.ui.knowledge.wiki_graph_view import WikiGraphView

_INFO_PANEL_WIDTH = 360


class ObsidianWorkspacePage(QWidget):
    """중앙 Iris Wiki 그래프 + 우측 노트 정보 패널."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ObsidianWorkspacePage")
        self._wiki: IrisWiki | None = None
        self._current_rel = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(0)

        # 중앙 — 그래프
        graph_wrap = QWidget()
        graph_wrap.setObjectName("WorkspacePanel")
        graph_lay = QVBoxLayout(graph_wrap)
        graph_lay.setContentsMargins(12, 8, 12, 8)
        graph_lay.setSpacing(8)
        graph_title = QLabel(f"{WIKI_NAME} — 지식 그래프")
        graph_title.setObjectName("SectionTitle")
        graph_lay.addWidget(graph_title)
        self._graph = WikiGraphView()
        self._graph.node_selected.connect(self.show_note)
        graph_lay.addWidget(self._graph, 1)
        splitter.addWidget(graph_wrap)

        # 우측 — 선택 노트 정보
        info_wrap = QWidget()
        info_wrap.setObjectName("ObsidianPreviewPanel")
        info_wrap.setMinimumWidth(260)
        info_wrap.setMaximumWidth(_INFO_PANEL_WIDTH)
        info_wrap.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        info_lay = QVBoxLayout(info_wrap)
        info_lay.setContentsMargins(12, 8, 12, 8)
        info_lay.setSpacing(8)
        self._title = QLabel("노트를 선택하세요")
        self._title.setObjectName("SectionTitle")
        self._title.setWordWrap(True)
        info_lay.addWidget(self._title)
        self._body = QTextBrowser()
        self._body.setObjectName("ObsidianPreviewBody")
        self._body.setOpenExternalLinks(False)
        self._body.setReadOnly(True)
        attach_image_loader(self._body)
        self._body.anchorClicked.connect(self._on_preview_anchor)
        info_lay.addWidget(self._body, 1)
        splitter.addWidget(info_wrap)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([820, 340])
        outer.addWidget(splitter)

    def _on_preview_anchor(self, url: QUrl) -> None:
        handle_chat_anchor_click(self, url.toString())

    def set_wiki(self, wiki: IrisWiki) -> None:
        self._wiki = wiki
        self._graph.build(wiki)

    def reload_graph(self) -> None:
        self._graph.build(self._wiki)

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
        html = render_wiki_document(text)
        if not html:
            self._body.setHtml('<p style="color:#94a3b8;">(빈 노트)</p>')
        else:
            self._body.setHtml(html)
            prefetch_chat_html_images(self._body, html)
        self._graph.select(rel_path)

    @property
    def current_note(self) -> str:
        return self._current_rel
