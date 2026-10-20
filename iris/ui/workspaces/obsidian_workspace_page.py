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

from PyQt6.QtCore import QEvent, QPoint, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap, QWheelEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QSplitterHandle,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from iris.ui.shared.theme_tokens import TOKENS

from iris.knowledge.iris_wiki import IrisWiki, markdown_heading, match_wiki_notes
from iris.knowledge.wiki_original import first_page_png, split_note_view, viewer_local_path
from iris.ui.chat.chat_image_view import (
    attach_image_loader,
    handle_chat_anchor_click,
    prefetch_chat_html_images,
)
from iris.ui.chat.chat_renderer import render_wiki_document
from iris.ui.knowledge.wiki_graph_view import WikiGraphView
from iris.ui.workspaces.workspace_iris_chat import (
    install_companion_shell,
    mount_chat_host,
    shift_chat_column,
)

_CONTENT_MIN = 240
_GRAPH_COLLAPSE = 0
_GRAPH_FADE_START = 200
_GRAPH_FADE_END = 28
_SEARCH_W = 280
# 스크롤 시퀀스: 요약 아래 원본 위젯들. PDF 뷰 높이는 뷰포트에 맞춰 내부 휠 스크롤.
_ORIGINAL_PREVIEW_MIN = 280
_PDF_VIEW_MIN = 420
_SPLIT_PATH = Path.home() / ".iris-light" / "wiki-split.json"
_RESULT_LIMIT = 8


class _WikiPdfEngine:
    """QWebEngineView 지연 생성용. 휠이 QScrollArea로 새지 않게 감싼다."""

    @staticmethod
    def create(parent: QWidget):
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        class _View(QWebEngineView):
            def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
                # 부모 WikiNoteScroll이 휠을 가로채 PDF 내부 스크롤이 죽지 않게 한다.
                super().wheelEvent(event)
                event.accept()

        view = _View(parent)
        view.setObjectName("WikiOriginalView")
        view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        return view


def _load_split_ratio() -> float | None:
    try:
        data = json.loads(_SPLIT_PATH.read_text(encoding="utf-8"))
        ratio = float(data.get("content_ratio", 0))
    except (OSError, ValueError, TypeError):
        return None
    # 정보 패널을 좌측까지 당기면 비율이 높아진다 (구체 접힘).
    if 0.12 <= ratio <= 0.98:
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
    """위키 구체·노트(좌) + 아이리스 채팅(우). 메일/캘린더와 같은 채팅 호스트."""

    note_focused = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ObsidianWorkspacePage")
        self._wiki: IrisWiki | None = None
        self._current_rel = ""
        self._split_ready = False
        self._chat_list_extra = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        center = QWidget()
        center.setObjectName("WikiCenterPanel")
        center_lay = QVBoxLayout(center)
        center_lay.setContentsMargins(12, 8, 8, 8)
        center_lay.setSpacing(8)

        self._search = _SearchEdit(self)
        self._search.setObjectName("WikiSearchEdit")
        self._search.setPlaceholderText("Wiki 검색...")
        self._search.setClearButtonEnabled(True)
        # FixedWidth면 구체 칸이 280 아래로 안 접힌다 — max만 두고 접을 때 숨긴다.
        self._search.setMinimumWidth(0)
        self._search.setMaximumWidth(_SEARCH_W)
        self._search.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
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
        splitter.setChildrenCollapsible(True)
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
        graph_wrap.setMinimumWidth(_GRAPH_COLLAPSE)
        self._graph_wrap = graph_wrap
        self._graph_opacity = QGraphicsOpacityEffect(graph_wrap)
        self._graph_opacity.setOpacity(1.0)
        graph_wrap.setGraphicsEffect(self._graph_opacity)
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
        info_wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._info_wrap = info_wrap
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
        # 내부 스크롤 끔 — 바깥 WikiNoteScroll이 요약→원본 시퀀스를 담당.
        self._body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._body.setMinimumHeight(0)
        attach_image_loader(self._body)
        self._body.anchorClicked.connect(self._on_preview_anchor)
        self._body.document().contentsChanged.connect(self._fit_body_height)
        self._original = None
        self._pending_original = ""
        self._loaded_original = ""
        self._previewed_original = ""
        self._original_full_mode = False
        self._fitting_body = False
        # 한 스크롤: 요약 → 캡션·상태·미리보기·버튼·PDF (WikiOriginalPane 래퍼 없음).
        self._note_scroll = QScrollArea(info_wrap)
        self._note_scroll.setObjectName("WikiNoteScroll")
        self._note_scroll.setWidgetResizable(True)
        self._note_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._note_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._note_scroll.viewport().installEventFilter(self)
        note_col = QWidget()
        note_col.setObjectName("WikiNoteColumn")
        note_lay = QVBoxLayout(note_col)
        note_lay.setContentsMargins(0, 0, 0, 0)
        note_lay.setSpacing(12)
        note_lay.addWidget(self._body, 0)
        self._original_cap = QLabel("원본 문서")
        self._original_cap.setObjectName("WikiOriginalCaption")
        self._original_cap.hide()
        note_lay.addWidget(self._original_cap, 0)
        self._original_status = QLabel("불러오는 중…")
        self._original_status.setObjectName("WikiOriginalStatus")
        self._original_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._original_status.hide()
        note_lay.addWidget(self._original_status, 0)
        self._original_preview = QLabel()
        self._original_preview.setObjectName("WikiOriginalPreview")
        self._original_preview.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._original_preview.setScaledContents(False)
        self._original_preview.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        self._original_preview.hide()
        note_lay.addWidget(self._original_preview, 0)
        self._original_full_btn = QPushButton("전체 보기")
        self._original_full_btn.setObjectName("WikiOriginalFullBtn")
        self._original_full_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._original_full_btn.hide()
        self._original_full_btn.clicked.connect(self._open_original_full)
        note_lay.addWidget(self._original_full_btn, 0)
        # WebEngine은 늦게 붙는다 (_ensure_original_view).
        note_lay.addStretch(1)
        self._note_col = note_col
        self._note_lay = note_lay
        self._note_scroll.setWidget(note_col)
        info_lay.addWidget(self._note_scroll, 1)
        splitter.addWidget(info_wrap)
        splitter.setCollapsible(0, True)
        splitter.setCollapsible(1, False)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        center_lay.addWidget(splitter, 1)
        # IDE와 동일: IdeUnifiedShell 8:2 (좌 위키 · 우 Companion)
        install_companion_shell(self, center, root=root)

    def place_chat_host(self, host: QWidget) -> None:
        mount_chat_host(self, host)

    def shift_chat_column(self, delta: int) -> None:
        shift_chat_column(self, delta)

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
        self._fit_body_height()
        self._note_scroll.verticalScrollBar().setValue(0)
        self._pending_original = self._original_file(rel_path, asset)
        if self._pending_original:
            self._reveal_original_pane()
            self._show_original_loading()
            QTimer.singleShot(0, self._load_original)
        else:
            self._hide_original_pane()
        self._graph.select(rel_path)

    def _fit_body_height(self) -> None:
        """요약이 문서 전체 높이를 쓰게 해서, 스크롤 시 원본이 그 아래에 오게 한다."""
        if self._fitting_body or self._body.isHidden():
            return
        self._fitting_body = True
        try:
            width = max(120, int(self._note_scroll.viewport().width()) - 8)
            doc = self._body.document()
            doc.setTextWidth(float(width))
            height = int(doc.size().height()) + int(self._body.frameWidth() * 2) + 12
            height = max(48, height)
            if abs(self._body.height() - height) < 2:
                return
            self._body.setFixedHeight(height)
            self._body.updateGeometry()
            lay = self._note_col.layout()
            if lay is not None:
                lay.invalidate()
                lay.activate()
            self._note_col.adjustSize()
        finally:
            self._fitting_body = False

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        # PDF 위 휠은 바깥 WikiNoteScroll이 먹지 않는다 (내부 페이지 스크롤용).
        if (
            event.type() == QEvent.Type.Wheel
            and watched is self._note_scroll.viewport()
            and self._original is not None
            and self._original.isVisible()
        ):
            pos = event.globalPosition().toPoint()
            local = self._original.mapFromGlobal(pos)
            if self._original.rect().contains(local):
                target = self._original.focusProxy() or self._original
                QApplication.sendEvent(target, event)
                return True
        return super().eventFilter(watched, event)

    def _hide_original_pane(self) -> None:
        self._pending_original = ""
        self._loaded_original = ""
        self._previewed_original = ""
        self._original_full_mode = False
        self._original_cap.hide()
        self._original_status.hide()
        self._original_preview.hide()
        self._original_full_btn.hide()
        self._original_full_btn.setText("전체 보기")
        self._original_preview.clear()
        self._original_preview.setMinimumHeight(0)
        self._body.show()
        self._fit_body_height()
        if self._original is not None:
            self._original.hide()
            self._original.setMinimumHeight(0)
            self._original.setUrl(QUrl("about:blank"))

    def _reveal_original_pane(self) -> None:
        """요약 아래 원본 위젯들(캡션·미리보기·버튼)을 연다."""
        self._original_cap.show()
        self._original_full_btn.show()
        self._fit_body_height()

    def _show_original_loading(self, text: str = "불러오는 중…") -> None:
        self._original_status.setText(text)
        self._original_status.show()

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
        view = _WikiPdfEngine.create(self._note_col)
        view.loadFinished.connect(self._on_original_load_finished)
        view.hide()
        # stretch 앞에 삽입 (마지막 stretch = count-1)
        idx = max(0, self._note_lay.count() - 1)
        self._note_lay.insertWidget(idx, view, 0)
        self._original = view
        return view

    def _on_original_load_finished(self, _ok: bool) -> None:
        if self._original is not None and self._original.isVisible():
            self._original_status.hide()

    def _pdf_view_height(self) -> int:
        return max(_PDF_VIEW_MIN, int(self._note_scroll.viewport().height()) - 24)

    def _set_preview_pixmap(self, image: QImage) -> None:
        if image.isNull():
            self._original_preview.clear()
            return
        width = max(200, int(self._note_scroll.viewport().width()) - 24)
        if width <= 0:
            width = 400
        scaled = image
        if image.width() > width:
            scaled = image.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
        self._original_preview.setPixmap(QPixmap.fromImage(scaled))
        self._original_preview.setMinimumHeight(max(_ORIGINAL_PREVIEW_MIN, scaled.height()))

    def _show_pdf_preview(self, path: Path) -> None:
        """pymupdf 1페이지를 요약 아래에 그린다. Chromium은 「전체 보기」."""
        self._exit_original_full(restore_preview=False)
        key = str(path.resolve())
        pending = self._pending_original
        if (
            key == self._previewed_original
            and self._original_preview.pixmap() is not None
            and not self._original_preview.pixmap().isNull()
        ):
            self._original_status.hide()
            if self._original is not None:
                self._original.hide()
            self._body.show()
            self._fit_body_height()
            self._original_preview.show()
            self._original_full_btn.setText("전체 보기")
            self._original_full_btn.show()
            return
        self._show_original_loading()
        self._original_full_btn.hide()
        if self._original is not None:
            self._original.hide()
        png = first_page_png(path)
        if self._pending_original != pending:
            return
        if png:
            image = QImage.fromData(png)
            self._set_preview_pixmap(image)
            self._previewed_original = key
            self._original_status.hide()
            self._body.show()
            self._fit_body_height()
            self._original_preview.show()
            self._original_full_btn.setText("전체 보기")
            self._original_full_btn.show()
            return
        self._original_preview.clear()
        self._previewed_original = ""
        self._show_original_loading("미리보기를 만들 수 없습니다.")
        self._original_preview.hide()
        self._body.show()
        self._fit_body_height()
        self._original_full_btn.setText("전체 보기")
        self._original_full_btn.show()

    def _exit_original_full(self, *, restore_preview: bool = True) -> None:
        """WebEngine을 끄고 1페이지 미리보기로 돌린다. 요약은 항상 유지."""
        was_full = self._original_full_mode
        self._original_full_mode = False
        if self._original is not None:
            self._original.hide()
            self._original.setMinimumHeight(0)
            if was_full:
                self._original.setUrl(QUrl("about:blank"))
                self._loaded_original = ""
        self._body.show()
        self._fit_body_height()
        self._original_full_btn.setText("전체 보기")
        if not restore_preview or not self._pending_original:
            return
        path = Path(self._pending_original)
        if path.is_file() and path.suffix.lower() == ".pdf":
            self._show_pdf_preview(path)

    def _open_original_full(self) -> None:
        """「전체 보기」↔「미리보기로」. 요약은 숨기지 않고 같은 스크롤에 둔다."""
        if self._original_full_mode:
            self._exit_original_full(restore_preview=True)
            return
        path_text = self._pending_original
        if not path_text:
            return
        path = Path(path_text)
        if not path.is_file():
            return
        self._load_original_webengine(path, show_loading=True)

    def _load_original_webengine(self, path: Path, *, show_loading: bool) -> None:
        from PyQt6.QtWebEngineCore import QWebEngineSettings

        path_text = str(path)
        is_pdf = path.suffix.lower() == ".pdf"
        view = self._ensure_original_view()
        settings = view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, is_pdf)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, is_pdf
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False
        )
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        # Windows Chromium은 한글 경로 PDF를 빈 화면으로 여는 경우가 있다.
        view_path = viewer_local_path(path)
        url = QUrl.fromLocalFile(str(view_path))
        if is_pdf:
            url.setFragment("view=FitH")
        self._reveal_original_pane()
        if path_text != self._pending_original:
            return
        # 요약은 그대로 두고, PDF는 뷰포트 높이로 고정해 내부 휠 스크롤이 되게 한다.
        self._original_full_mode = True
        self._body.show()
        self._fit_body_height()
        self._original_preview.hide()
        view_h = self._pdf_view_height()
        view.setFixedHeight(view_h)
        view.setMinimumHeight(view_h)
        self._original_full_btn.setText("미리보기로")
        self._original_full_btn.show()
        view.show()
        view.setFocus(Qt.FocusReason.OtherFocusReason)
        # 원본 PDF가 보이도록 캡션 근처로 스크롤
        QTimer.singleShot(0, lambda: self._note_scroll.ensureWidgetVisible(self._original_cap))
        key = url.toString()
        if key == self._loaded_original and view.url().toString() == key:
            self._original_status.hide()
            return
        if show_loading:
            self._show_original_loading()
        self._loaded_original = key
        view.load(url)

    def _load_original(self) -> None:
        path_text = self._pending_original
        if not path_text:
            self._hide_original_pane()
            return
        path = Path(path_text)
        if not path.is_file():
            self._hide_original_pane()
            return
        self._reveal_original_pane()
        if path.suffix.lower() == ".pdf":
            self._show_pdf_preview(path)
            return
        # HTML·이미지 등은 여전히 WebEngine (플레이스홀더 → loadFinished).
        self._load_original_webengine(path, show_loading=True)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._split_ready:
            self._split_ready = True
            self._apply_saved_split()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._split_ready:
            self._clamp_note_split()
            self._apply_graph_fade()
            self._fit_body_height()
            if (
                self._original_full_mode
                and self._original is not None
                and self._original.isVisible()
            ):
                h = self._pdf_view_height()
                self._original.setFixedHeight(h)
                self._original.setMinimumHeight(h)
        if self._results.isVisible():
            self._place_results()

    def _clamp_note_split(self) -> None:
        """정보 패널 최소폭만 보장. 구체는 0까지 접을 수 있다."""
        sizes = self._split.sizes()
        total = sum(sizes)
        if total <= 0 or len(sizes) < 2:
            return
        content = max(_CONTENT_MIN, min(sizes[1], total))
        graph = total - content
        if graph != sizes[0] or content != sizes[1]:
            self._split.blockSignals(True)
            self._split.setSizes([graph, content])
            self._split.blockSignals(False)

    def _apply_graph_fade(self) -> None:
        """정보 패널을 좌측으로 당길수록 위키 구체를 페이드아웃."""
        sizes = self._split.sizes()
        graph_w = sizes[0] if sizes else 0
        if graph_w >= _GRAPH_FADE_START:
            opacity = 1.0
        elif graph_w <= _GRAPH_FADE_END:
            opacity = 0.0
        else:
            opacity = (graph_w - _GRAPH_FADE_END) / (_GRAPH_FADE_START - _GRAPH_FADE_END)
        self._graph_opacity.setOpacity(opacity)
        # 거의 안 보이면 클릭을 가로채지 않는다.
        transparent = opacity < 0.08
        self._graph_wrap.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, transparent
        )
        # 검색창이 구체 칸 최소폭을 다시 키우지 않게, 좁아지면 먼저 숨긴다.
        if graph_w < _SEARCH_W or transparent:
            self._search.hide()
            self._results.hide()
        else:
            self._search.show()

    def _apply_saved_split(self) -> None:
        total = max(self._split.width(), _CONTENT_MIN + 1)
        self._info_wrap.setMaximumWidth(16777215)
        ratio = _load_split_ratio()
        # 기본: 구체가 넓고 정보는 읽기 폭. 저장된 비율이 있으면 따른다.
        content = int(total * ratio) if ratio is not None else min(360, max(_CONTENT_MIN, total // 3))
        content = max(_CONTENT_MIN, min(content, total))
        self._split.blockSignals(True)
        self._split.setSizes([total - content, content])
        self._split.blockSignals(False)
        self._apply_graph_fade()

    def _on_split_moved(self, _pos: int, _index: int) -> None:
        sizes = self._split.sizes()
        total = sum(sizes)
        if total <= 0 or len(sizes) < 2:
            return
        content = max(_CONTENT_MIN, min(sizes[1], total))
        if content != sizes[1]:
            self._split.blockSignals(True)
            self._split.setSizes([total - content, content])
            self._split.blockSignals(False)
        _save_split_ratio(content / total)
        self._apply_graph_fade()

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
