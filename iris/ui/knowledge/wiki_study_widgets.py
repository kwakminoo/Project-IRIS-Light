"""위키 공부 UX — 페이지 메모장 · 선택 책 FAB · 용어설명 팝오버 · 인용 칩."""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QMimeData, QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from iris.knowledge.wiki_quote import (
    WIKI_QUOTE_MIME,
    WikiQuote,
    chip_preview,
    encode_wiki_quote_bytes,
)
from iris.knowledge.wiki_term_explain import (
    MAX_SELECTION_CHARS,
    selection_eligible_for_fab,
)
from iris.storage.wiki_page_memos import PageMemoStore


class WikiPreviewBody(QTextBrowser):
    """선택 복사 시 Iris 위키 인용 MIME을 함께 넣는다."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._note_rel = ""
        self._note_title = ""

    def set_note_meta(self, note_rel: str, title: str) -> None:
        self._note_rel = (note_rel or "").strip()
        self._note_title = (title or "").strip()

    def current_quote(self) -> WikiQuote | None:
        text = self.textCursor().selectedText().replace("\u2029", "\n").strip()
        if not text or not self._note_rel:
            return None
        return WikiQuote(
            note_rel=self._note_rel,
            title=self._note_title or self._note_rel,
            quote=text,
        ).normalized()

    def createMimeDataFromSelection(self):  # noqa: N802
        # QTextBrowser 가 돌려주는 mime 은 커스텀 setData 가 무시되므로 복사본을 만든다.
        src = super().createMimeDataFromSelection()
        mime = QMimeData()
        if src is not None:
            for fmt in src.formats():
                mime.setData(fmt, src.data(fmt))
        quote = self.current_quote()
        if quote is None:
            return mime
        raw = encode_wiki_quote_bytes(quote)
        if raw:
            mime.setData(WIKI_QUOTE_MIME, QByteArray(raw))
        return mime


class WikiSelectionBookFab(QToolButton):
    """선택 영역 우측 상단 — 펼친 책 아이콘."""

    explain_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("WikiSelectionBookFab")
        self.setText("📖")
        self.setToolTip("선택 용어 짧게 설명")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(28, 28)
        self.setStyleSheet(
            """
            QToolButton#WikiSelectionBookFab {
                background: rgba(14, 165, 233, 0.92);
                color: #0f172a;
                border: none;
                border-radius: 8px;
                font-size: 14px;
            }
            QToolButton#WikiSelectionBookFab:hover {
                background: rgba(56, 189, 248, 1.0);
            }
            """
        )
        self.hide()
        self.clicked.connect(self._emit_selection)

    def _emit_selection(self) -> None:
        body = self.parentWidget()
        if not isinstance(body, QTextBrowser):
            return
        text = body.textCursor().selectedText().replace("\u2029", "\n").strip()
        if text:
            self.explain_requested.emit(text)

    def sync_to_body(self, body: QTextBrowser) -> None:
        text = body.textCursor().selectedText().replace("\u2029", "\n")
        if not selection_eligible_for_fab(text, max_chars=MAX_SELECTION_CHARS):
            self.hide()
            return
        cursor = body.textCursor()
        end = QTextCursor(cursor)
        end.setPosition(cursor.selectionEnd())
        rect = body.cursorRect(end)
        # 선택 끝의 우측 상단
        x = rect.right() + 4
        y = rect.top() - 2
        max_x = max(0, body.viewport().width() - self.width() - 2)
        max_y = max(0, body.viewport().height() - self.height() - 2)
        x = min(max(0, x), max_x)
        y = min(max(0, y), max_y)
        # viewport 좌표 → body 좌표
        vp = body.viewport()
        top_left = body.mapFromGlobal(vp.mapToGlobal(QPoint(0, 0)))
        self.move(top_left.x() + x, top_left.y() + y)
        self.raise_()
        self.show()


class WikiTermExplainPopover(QFrame):
    """채팅에 메시지를 남기지 않는 짧은 설명 카드."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("WikiTermExplainPopover")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            """
            QFrame#WikiTermExplainPopover {
                background: #0f172a;
                border: 1px solid rgba(56, 189, 248, 0.55);
                border-radius: 10px;
            }
            QLabel#WikiTermExplainTitle { color: #e0f2fe; font-weight: 600; }
            QLabel#WikiTermExplainBody { color: #cbd5e1; }
            """
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)
        head = QHBoxLayout()
        self._title = QLabel()
        self._title.setObjectName("WikiTermExplainTitle")
        self._title.setWordWrap(True)
        head.addWidget(self._title, 1)
        close_btn = QToolButton()
        close_btn.setText("×")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)
        head.addWidget(close_btn, 0)
        lay.addLayout(head)
        self._body = QLabel()
        self._body.setObjectName("WikiTermExplainBody")
        self._body.setWordWrap(True)
        self._body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._body)
        self.setFixedWidth(280)
        self.hide()

    def show_explanation(self, term: str, explanation: str, anchor: QPoint) -> None:
        self._title.setText(term)
        self._body.setText(explanation)
        self.adjustSize()
        parent = self.parentWidget()
        if parent is not None:
            x = min(max(4, anchor.x()), max(4, parent.width() - self.width() - 4))
            y = min(max(4, anchor.y()), max(4, parent.height() - self.height() - 4))
            self.move(x, y)
        self.raise_()
        self.show()


class WikiPageMemoButton(QToolButton):
    """내용 영역 우측 상단 메모장 아이콘."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WikiPageMemoButton")
        self.setText("📝")
        self.setToolTip("이 페이지 메모장")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(32, 32)
        self.setStyleSheet(
            """
            QToolButton#WikiPageMemoButton {
                background: rgba(30, 41, 59, 0.9);
                border: 1px solid rgba(148, 163, 184, 0.35);
                border-radius: 8px;
                font-size: 14px;
            }
            QToolButton#WikiPageMemoButton:hover {
                border-color: rgba(56, 189, 248, 0.7);
            }
            """
        )
        self._count = 0

    def set_count(self, n: int) -> None:
        self._count = max(0, int(n))
        if self._count:
            self.setText(f"📝{self._count}")
            self.setFixedWidth(40)
        else:
            self.setText("📝")
            self.setFixedWidth(32)


class WikiPageMemoPanel(QFrame):
    """페이지 묶임 메모 CRUD. vault에 md를 쓰지 않는다."""

    changed = pyqtSignal()

    def __init__(self, store: PageMemoStore, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("WikiPageMemoPanel")
        self._store = store
        self._note_rel = ""
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            """
            QFrame#WikiPageMemoPanel {
                background: #0b1220;
                border: 1px solid rgba(56, 189, 248, 0.4);
                border-radius: 12px;
            }
            QLabel#WikiPageMemoHeading { color: #e0f2fe; font-weight: 600; }
            QListWidget#WikiPageMemoList {
                background: transparent;
                border: none;
                color: #cbd5e1;
            }
            """
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)
        head = QHBoxLayout()
        heading = QLabel("페이지 메모장")
        heading.setObjectName("WikiPageMemoHeading")
        head.addWidget(heading, 1)
        close_btn = QToolButton()
        close_btn.setText("×")
        close_btn.clicked.connect(self.hide)
        head.addWidget(close_btn)
        lay.addLayout(head)
        self._list = QListWidget()
        self._list.setObjectName("WikiPageMemoList")
        self._list.itemSelectionChanged.connect(self._on_select)
        lay.addWidget(self._list, 1)
        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText("이 페이지에 남길 메모…")
        self._editor.setFixedHeight(72)
        lay.addWidget(self._editor)
        row = QHBoxLayout()
        add_btn = QPushButton("추가")
        add_btn.clicked.connect(self._add)
        save_btn = QPushButton("수정")
        save_btn.clicked.connect(self._save)
        del_btn = QPushButton("삭제")
        del_btn.clicked.connect(self._delete)
        row.addWidget(add_btn)
        row.addWidget(save_btn)
        row.addWidget(del_btn)
        lay.addLayout(row)
        self.setFixedWidth(300)
        self.setMinimumHeight(280)
        self.hide()

    def set_note(self, note_rel: str) -> None:
        self._note_rel = (note_rel or "").strip()
        self._editor.clear()
        self.reload()

    def reload(self) -> None:
        self._list.clear()
        for memo in self._store.list(self._note_rel):
            item = QListWidgetItem(memo.body.replace("\n", " ")[:80])
            item.setData(Qt.ItemDataRole.UserRole, memo.memo_id)
            item.setData(Qt.ItemDataRole.UserRole + 1, memo.body)
            self._list.addItem(item)

    def count(self) -> int:
        return self._store.count(self._note_rel)

    def _on_select(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        self._editor.setPlainText(str(item.data(Qt.ItemDataRole.UserRole + 1) or ""))

    def _add(self) -> None:
        if not self._note_rel:
            return
        body = self._editor.toPlainText().strip()
        if not body:
            return
        try:
            self._store.add(self._note_rel, body)
        except ValueError:
            return
        self._editor.clear()
        self.reload()
        self.changed.emit()

    def _save(self) -> None:
        item = self._list.currentItem()
        if item is None or not self._note_rel:
            return
        mid = str(item.data(Qt.ItemDataRole.UserRole) or "")
        body = self._editor.toPlainText().strip()
        if not mid or not body:
            return
        self._store.update(self._note_rel, mid, body)
        self.reload()
        self.changed.emit()

    def _delete(self) -> None:
        item = self._list.currentItem()
        if item is None or not self._note_rel:
            return
        mid = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not mid:
            return
        self._store.delete(self._note_rel, mid)
        self._editor.clear()
        self.reload()
        self.changed.emit()

    def toggle_at(self, anchor: QPoint) -> None:
        if self.isVisible():
            self.hide()
            return
        parent = self.parentWidget()
        if parent is not None:
            x = min(max(8, anchor.x()), max(8, parent.width() - self.width() - 8))
            y = min(max(8, anchor.y()), max(8, parent.height() - self.height() - 8))
            self.move(x, y)
        self.raise_()
        self.show()


class WikiQuoteChip(QFrame):
    """채팅 입력창 위 푸른 인용 카드."""

    removed = pyqtSignal()

    def __init__(self, quote: WikiQuote, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.quote = quote
        self.setObjectName("WikiQuoteChip")
        self.setStyleSheet(
            """
            QFrame#WikiQuoteChip {
                background: rgba(14, 165, 233, 0.14);
                border: 1px solid rgba(56, 189, 248, 0.65);
                border-radius: 10px;
            }
            QLabel#WikiQuoteChipTitle { color: #7dd3fc; font-weight: 600; }
            QLabel#WikiQuoteChipBody { color: #e0f2fe; }
            QLabel#WikiQuoteChipPath { color: #64748b; font-size: 11px; }
            """
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 8, 8)
        lay.setSpacing(4)
        head = QHBoxLayout()
        title = QLabel(quote.title)
        title.setObjectName("WikiQuoteChipTitle")
        head.addWidget(title, 1)
        close_btn = QToolButton()
        close_btn.setText("×")
        close_btn.clicked.connect(self.removed.emit)
        head.addWidget(close_btn)
        lay.addLayout(head)
        body = QLabel(chip_preview(quote))
        body.setObjectName("WikiQuoteChipBody")
        body.setWordWrap(True)
        lay.addWidget(body)
        path = QLabel(quote.note_rel)
        path.setObjectName("WikiQuoteChipPath")
        lay.addWidget(path)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)


class ComposerWikiQuoteStrip(QWidget):
    """첨부 스트립과 같은 자리 — 위키 인용 칩 목록."""

    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ComposerWikiQuoteStrip")
        self._quotes: list[WikiQuote] = []
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(6)
        self.hide()

    def quotes(self) -> list[WikiQuote]:
        return list(self._quotes)

    def clear(self) -> None:
        self._quotes.clear()
        self._rebuild()
        self.changed.emit()

    def add_quote(self, quote: WikiQuote) -> None:
        item = quote.normalized()
        if item is None:
            return
        self._quotes.append(item)
        self._rebuild()
        self.changed.emit()

    def take_quotes(self) -> list[WikiQuote]:
        items = list(self._quotes)
        self.clear()
        return items

    def _rebuild(self) -> None:
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for quote in self._quotes:
            chip = WikiQuoteChip(quote, self)

            def _remove(target: WikiQuote = quote) -> None:
                self._quotes = [q for q in self._quotes if q is not target]
                self._rebuild()
                self.changed.emit()

            chip.removed.connect(_remove)
            self._lay.addWidget(chip)
        self.setVisible(bool(self._quotes))

    def sizeHint(self) -> QSize:  # noqa: N802
        if not self._quotes:
            return QSize(0, 0)
        return super().sizeHint()


def parse_wiki_quote_from_mime(source) -> WikiQuote | None:
    if source is None:
        return None
    if source.hasFormat(WIKI_QUOTE_MIME):
        from iris.knowledge.wiki_quote import decode_wiki_quote_bytes

        return decode_wiki_quote_bytes(bytes(source.data(WIKI_QUOTE_MIME)))
    return None


def surrounding_for_cursor(body: QTextBrowser, max_chars: int = 160) -> str:
    cursor = body.textCursor()
    doc = body.document()
    pos = cursor.selectionStart()
    plain = doc.toPlainText()
    start = max(0, pos - max_chars // 2)
    end = min(len(plain), pos + max_chars // 2)
    return plain[start:end]
