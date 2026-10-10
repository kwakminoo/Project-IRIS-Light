"""Iris Wiki 워크스페이스 — 지식 그래프(왼쪽) + 노트(오른쪽).

수동 확인 (코드 블록 카드):
  1. IRIS 실행 → Wiki 워크스페이스
  2. ``` fenced code 가 포함된 노트를 그래프에서 선택
  3. 오른쪽 미리보기에 chat_block_radius·mono 폰트 코드 카드가 보이는지 확인
  4. 이미지 클릭 → 라이트박스, http 링크 → 브라우저
"""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QPoint, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QSplitter,
    QSplitterHandle,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from iris.ui.shared.theme_tokens import TOKENS

from iris.knowledge.iris_wiki import IrisWiki, markdown_heading, match_wiki_notes
from iris.knowledge.wiki_original import split_note_view
from iris.ui.chat.chat_image_view import (
    attach_image_loader,
    handle_chat_anchor_click,
    prefetch_chat_html_images,
)
from iris.ui.chat.chat_renderer import render_wiki_document
from iris.ui.knowledge.wiki_graph_view import WikiGraphView

_CONTENT_MIN = 240
_GRAPH_MIN = 280


def _content_cap(total: int) -> int:
    room = max(_CONTENT_MIN, total - _GRAPH_MIN)
    return min(500, room)
_SEARCH_W = 280
_SPLIT_PATH = Path.home() / ".iris-light" / "wiki-split.json"
_RESULT_LIMIT = 8


def _load_split_ratio() -> float | None:
    try:
        data = json.loads(_SPLIT_PATH.read_text(encoding="utf-8"))
        ratio = float(data.get("content_ratio", 0))
    except (OSError, ValueError, TypeError):
        return None
    if 0.12 <= ratio <= 0.88:
        return ratio
    return None


def _save_split_ratio(ratio: float) -> None:
    try:
        _SPLIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SPLIT_PATH.write_text(
            json.dumps({"content_ratio": round(ratio, 4)}),
            encoding="utf-8",
        )
    except OSError:
        pass


class _WikiSplitHandle(QSplitterHandle):
    """채팅 높이 핸들과 같이, 가운데에만 짧은 막대."""

    def __init__(self, orientation: Qt.Orientation, parent: QSplitter) -> None:
        super().__init__(orientation, parent)
        self._hover = False
        self.setCursor(Qt.CursorShape.SizeHorCursor)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        hot = self._hover or self.underMouse()
        color = QColor(TOKENS.neon_cyan if hot else TOKENS.text_muted)
        color.setAlpha(170 if hot else 80)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        bar_h, bar_w = 28, 2
        x = max(0, (self.width() - bar_w) // 2)
        y = max(0, (self.height() - bar_h) // 2)
        painter.drawRoundedRect(x, y, bar_w, bar_h, 1, 1)
        painter.end()


class _WikiSplit(QSplitter):
    def createHandle(self) -> QSplitterHandle:  # noqa: N802
        return _WikiSplitHandle(self.orientation(), self)


class _SearchEdit(QLineEdit):
    def __init__(self, page: ObsidianWorkspacePage) -> None:
        super().__init__(page)
        self._page = page

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_Escape and self._page.results_open():
            self._page.hide_results()
            return
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self._page.results_open():
            self._page.move_result(1 if key == Qt.Key.Key_Down else -1)
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._page.results_open():
            self._page.activate_result()
            return
        super().keyPressEvent(event)


class ObsidianWorkspacePage(QWidget):
    """왼쪽 Iris Wiki 그래프 + 오른쪽 노트. 그래프 위 검색은 짧게."""

    note_focused = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ObsidianWorkspacePage")
        self._wiki: IrisWiki | None = None
        self._current_rel = ""
        self._split_ready = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 8)
        outer.setSpacing(8)

        self._search = _SearchEdit(self)
        self._search.setObjectName("WikiSearchEdit")
        self._search.setPlaceholderText("Wiki 검색...")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedWidth(_SEARCH_W)
        self._search.textChanged.connect(self._on_query)
        self._search.setStyleSheet(
            """
            QLineEdit#WikiSearchEdit {
                background: rgba(15, 23, 42, 0.72);
                color: #e2e8f0;
                border: 1px solid rgba(148, 163, 184, 0.35);
                border-radius: 8px;
                padding: 6px 10px;
            }
            """
        )
        self._results = QFrame(self)
        self._results.setObjectName("WikiSearchResults")
        self._results.setStyleSheet(
            """
            QFrame#WikiSearchResults {
                background: #0f172a;
                border: 1px solid rgba(148, 163, 184, 0.35);
                border-radius: 8px;
            }
            QListWidget { background: transparent; border: none; color: #e2e8f0; }
            QListWidget::item { padding: 4px 8px; }
            QListWidget::item:selected { background: rgba(56, 189, 248, 0.18); }
            """
        )
        result_lay = QVBoxLayout(self._results)
        result_lay.setContentsMargins(4, 4, 4, 4)
        self._list = QListWidget(self._results)
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.itemClicked.connect(self._on_result_clicked)
        result_lay.addWidget(self._list)
        self._results.hide()

        splitter = _WikiSplit(Qt.Orientation.Horizontal)
        splitter.setObjectName("WikiHSplit")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)
        # 앱 전역 핸들은 폭 0·투명. 잡은 영역만 열고, 표시는 핸들이 가운데 막대로 그린다.
        splitter.setStyleSheet(
            """
            QSplitter#WikiHSplit::handle {
                background: transparent;
                border: none;
                width: 10px;
                min-width: 10px;
                max-width: 10px;
                margin: 0;
            }
            """
        )
        splitter.splitterMoved.connect(self._on_split_moved)
        self._split = splitter

        graph_wrap = QWidget()
        graph_wrap.setObjectName("WorkspacePanel")
        graph_wrap.setMinimumWidth(_GRAPH_MIN)
        graph_lay = QVBoxLayout(graph_wrap)
        graph_lay.setContentsMargins(0, 0, 4, 0)
        graph_lay.setSpacing(8)
        graph_lay.addWidget(self._search, 0, Qt.AlignmentFlag.AlignLeft)
        self._graph = WikiGraphView()
        self._graph.node_selected.connect(self.show_note)
        graph_lay.addWidget(self._graph, 1)
        splitter.addWidget(graph_wrap)

        info_wrap = QWidget()
        info_wrap.setObjectName("ObsidianPreviewPanel")
        info_wrap.setMinimumWidth(_CONTENT_MIN)
        info_wrap.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        info_lay = QVBoxLayout(info_wrap)
        info_lay.setContentsMargins(8, 0, 0, 0)
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
        self._original = None
        self._pending_original = ""
        self._original_slot = QWidget(info_wrap)
        self._original_slot.hide()
        self._original_lay = QVBoxLayout(self._original_slot)
        self._original_lay.setContentsMargins(0, 0, 0, 0)
        note_split = QSplitter(Qt.Orientation.Vertical, info_wrap)
        note_split.setChildrenCollapsible(False)
        note_split.setHandleWidth(6)
        note_split.addWidget(self._body)
        note_split.addWidget(self._original_slot)
        note_split.setStretchFactor(0, 1)
        note_split.setStretchFactor(1, 2)
        self._note_split = note_split
        info_lay.addWidget(note_split, 1)
        splitter.addWidget(info_wrap)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        outer.addWidget(splitter, 1)

    def results_open(self) -> bool:
        return self._results.isVisible()

    def hide_results(self) -> None:
        self._results.hide()

    def move_result(self, delta: int) -> None:
        count = self._list.count()
        if count <= 0:
            return
        row = self._list.currentRow()
        if row < 0:
            row = 0 if delta > 0 else count - 1
        else:
            row = (row + delta) % count
        self._list.setCurrentRow(row)

    def activate_result(self) -> None:
        item = self._list.currentItem()
        if item is None and self._list.count():
            item = self._list.item(0)
        self._open_result_item(item)

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
        title = markdown_heading(text) or rel_path.rsplit("/", 1)[-1].removesuffix(".md")
        self._title.setText(title)
        top, asset = split_note_view(text)
        html = render_wiki_document(top or text)
        if not html:
            self._body.setHtml('<p style="color:#94a3b8;">(빈 노트)</p>')
        else:
            self._body.setHtml(html)
            prefetch_chat_html_images(self._body, html)
        self._pending_original = self._original_file(rel_path, asset)
        if self._pending_original:
            self._original_slot.show()
            QTimer.singleShot(0, self._load_original)
        else:
            self._original_slot.hide()
        self._graph.select(rel_path)

    def _original_file(self, rel_path: str, asset: str) -> str:
        if not asset or self._wiki is None:
            return ""
        rel = (rel_path or "").replace("\\", "/").strip()
        if rel.startswith("user/"):
            rel = rel[len("user/") :]
        note = (self._wiki.user_root / rel).resolve()
        path = (note.parent / asset).resolve()
        root = self._wiki.user_root.resolve()
        if root not in path.parents or not path.is_file():
            return ""
        return str(path)

    def _ensure_original_view(self):
        if self._original is not None:
            return self._original
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        view = QWebEngineView(self._original_slot)
        view.setObjectName("WikiOriginalView")
        self._original_lay.addWidget(view)
        self._original = view
        return view

    def _load_original(self) -> None:
        path_text = self._pending_original
        if not path_text:
            self._original_slot.hide()
            return
        path = Path(path_text)
        if not path.is_file():
            self._original_slot.hide()
            return
        from PyQt6.QtWebEngineCore import QWebEngineSettings

        view = self._ensure_original_view()
        is_pdf = path.suffix.lower() == ".pdf"
        settings = view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, is_pdf)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, is_pdf
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False
        )
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        url = QUrl.fromLocalFile(str(path))
        if is_pdf:
            url.setFragment("view=FitH")
        self._original_slot.show()
        view.load(url)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._split_ready:
            self._split_ready = True
            self._apply_saved_split()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._split_ready:
            self._limit_content_panel()
        if self._results.isVisible():
            self._place_results()

    def _limit_content_panel(self) -> None:
        total = max(self._split.width(), _CONTENT_MIN + _GRAPH_MIN)
        cap = _content_cap(total)
        info = self._split.widget(1)
        info.setMaximumWidth(cap)
        sizes = self._split.sizes()
        if len(sizes) < 2 or sum(sizes) <= 0:
            return
        content = min(sizes[1], cap)
        if content != sizes[1]:
            self._split.blockSignals(True)
            self._split.setSizes([sum(sizes) - content, content])
            self._split.blockSignals(False)

    def _apply_saved_split(self) -> None:
        total = max(self._split.width(), _CONTENT_MIN + _GRAPH_MIN)
        cap = _content_cap(total)
        self._split.widget(1).setMaximumWidth(cap)
        ratio = _load_split_ratio()
        content = int(total * ratio) if ratio is not None else min(360, total - _GRAPH_MIN)
        content = max(_CONTENT_MIN, min(content, cap))
        self._split.blockSignals(True)
        self._split.setSizes([total - content, content])
        self._split.blockSignals(False)

    def _on_split_moved(self, _pos: int, _index: int) -> None:
        sizes = self._split.sizes()
        total = sum(sizes)
        if total <= 0 or len(sizes) < 2:
            return
        cap = _content_cap(total)
        content = min(sizes[1], cap)
        if content != sizes[1]:
            self._split.blockSignals(True)
            self._split.setSizes([total - content, content])
            self._split.blockSignals(False)
        _save_split_ratio(content / total)

    def _on_query(self, text: str) -> None:
        query = (text or "").strip()
        self._list.clear()
        if not query or self._wiki is None:
            self._results.hide()
            return
        hits = match_wiki_notes(self._wiki.list_notes(), query, limit=_RESULT_LIMIT)
        if not hits:
            item = QListWidgetItem("검색 결과가 없습니다.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(item)
        else:
            for note in hits:
                suffix = Path(note.rel_path).suffix.lower() or "note"
                item = QListWidgetItem(f"{note.title}   {suffix}")
                item.setData(Qt.ItemDataRole.UserRole, note.rel_path)
                self._list.addItem(item)
            self._list.setCurrentRow(0)
        self._place_results()
        self._results.show()
        self._results.raise_()

    def _place_results(self) -> None:
        top = self._search.mapTo(self, QPoint(0, self._search.height() + 4))
        rows = max(1, min(_RESULT_LIMIT, self._list.count()))
        self._results.setGeometry(top.x(), top.y(), self._search.width(), rows * 28 + 8)

    def _on_result_clicked(self, item: QListWidgetItem) -> None:
        self._open_result_item(item)

    def _open_result_item(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        rel = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not rel:
            return
        self._search.blockSignals(True)
        self._search.setText(item.text().split("   ", 1)[0])
        self._search.blockSignals(False)
        self._results.hide()
        self.show_note(rel)
        self._graph.focus(rel)
        self.note_focused.emit(rel)

    @property
    def current_note(self) -> str:
        return self._current_rel
