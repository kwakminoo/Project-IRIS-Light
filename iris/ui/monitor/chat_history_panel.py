"""좌측 사이드바 — 저장된 대화 목록 + 새 채팅."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QPointF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QKeyEvent, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from iris.storage.conversations import ChatConversation, DEFAULT_TITLE
from iris.ui.shared.section_header import (
    SECTION_CONTENT_GAP,
    SECTION_TITLE_LINE_GAP,
    apply_section_panel_layout,
)
from iris.ui.shared.theme_tokens import TOKENS


class ChatHistoryPanel(QWidget):
    """CHATS 섹션 — 세션 목록·제목 수정·삭제 요청."""

    new_chat_requested = pyqtSignal()
    conversation_selected = pyqtSignal(int)
    conversation_delete_requested = pyqtSignal(int)
    conversation_rename_requested = pyqtSignal(int, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ChatHistoryPanel")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        root = QVBoxLayout(self)
        apply_section_panel_layout(root)

        header = QWidget()
        header.setObjectName("SectionHeader")
        header_lay = QVBoxLayout(header)
        header_lay.setContentsMargins(0, 0, 0, 0)
        header_lay.setSpacing(SECTION_TITLE_LINE_GAP)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(4)
        title = QLabel("CHATS")
        title.setObjectName("SidebarTitle")
        title.setStyleSheet("background: transparent; border: none;")
        title_row.addWidget(title, 1)

        plus = QPushButton("+")
        plus.setObjectName("ChatNewButton")
        plus.setFixedSize(20, 20)
        plus.setCursor(Qt.CursorShape.PointingHandCursor)
        plus.setToolTip("새 채팅")
        plus.setStyleSheet(
            f"""
            QPushButton#ChatNewButton {{
                background: transparent;
                border: none;
                padding: 0;
                color: {TOKENS.text_muted};
                font-size: 16px;
            }}
            QPushButton#ChatNewButton:hover {{ color: {TOKENS.neon_cyan}; }}
            """
        )
        plus.clicked.connect(self.new_chat_requested.emit)
        title_row.addWidget(plus, 0, Qt.AlignmentFlag.AlignRight)
        header_lay.addLayout(title_row)

        line = QFrame()
        line.setObjectName("SectionUnderline")
        line.setFixedHeight(1)
        line.setStyleSheet(
            f"background: {TOKENS.panel_border}; border: none; max-height: 1px;"
        )
        header_lay.addWidget(line)
        root.addWidget(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._inner = QWidget()
        self._inner.setObjectName("SidebarInner")
        self._inner_lay = QVBoxLayout(self._inner)
        self._inner_lay.setContentsMargins(0, 0, 0, 0)
        self._inner_lay.setSpacing(SECTION_CONTENT_GAP)
        self._inner_lay.addStretch(1)
        self._scroll.setWidget(self._inner)
        root.addWidget(self._scroll, 1)

        self._items: list[ChatConversation] = []
        self._active_id = 0
        self._editing_id = 0
        self._pending: tuple[list[ChatConversation], int] | None = None

    def set_conversations(
        self,
        items: list[ChatConversation],
        *,
        active_id: int = 0,
    ) -> None:
        packed = (list(items), int(active_id or 0))
        if self._editing_id:
            self._pending = packed
            return
        self._items, self._active_id = packed
        self._rebuild()

    def _rebuild(self) -> None:
        while self._inner_lay.count():
            item = self._inner_lay.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.deleteLater()

        if not self._items:
            hint = QLabel("— no chats yet")
            hint.setStyleSheet(
                f"color: {TOKENS.text_muted}; font-size: {TOKENS.font_size_micro};"
                " padding: 8px 4px; background: transparent;"
            )
            self._inner_lay.addWidget(hint)
        else:
            for conv in self._items:
                row = _ChatRow(
                    conv,
                    conv.id == self._active_id,
                    on_open=self._on_open,
                    on_delete=self._on_delete,
                    on_rename=self._on_rename,
                    on_edit_start=self._on_edit_start,
                    on_edit_end=self._on_edit_end,
                )
                self._inner_lay.addWidget(row)
        self._inner_lay.addStretch(1)

    def _on_open(self, conv_id: int) -> None:
        self.conversation_selected.emit(int(conv_id))

    def _on_delete(self, conv_id: int) -> None:
        self.conversation_delete_requested.emit(int(conv_id))

    def _on_rename(self, conv_id: int, title: str) -> None:
        self.conversation_rename_requested.emit(int(conv_id), title)

    def _on_edit_start(self, conv_id: int) -> None:
        self._editing_id = int(conv_id)

    def _on_edit_end(self) -> None:
        self._editing_id = 0
        pending = self._pending
        self._pending = None
        if pending is not None:
            self.set_conversations(pending[0], active_id=pending[1])


class _ChatRow(QFrame):
    def __init__(
        self,
        conv: ChatConversation,
        active: bool,
        *,
        on_open,
        on_delete,
        on_rename,
        on_edit_start,
        on_edit_end,
    ) -> None:
        super().__init__()
        self.setObjectName("HudChatRow")
        self._conv_id = conv.id
        self._title = (conv.title or DEFAULT_TITLE).strip() or DEFAULT_TITLE
        self._active = active
        self._on_open = on_open
        self._on_delete = on_delete
        self._on_rename = on_rename
        self._on_edit_start = on_edit_start
        self._on_edit_end = on_edit_end
        self._editing = False
        self._ignore_focus_out = False

        h = QHBoxLayout(self)
        h.setContentsMargins(2, 2, 2, 2)
        h.setSpacing(2)

        display = self._title if len(self._title) <= 24 else self._title[:22] + "…"
        color = TOKENS.neon_cyan if active else TOKENS.text_secondary
        bg = TOKENS.panel_hover if active else "transparent"
        self._btn = QPushButton(display)
        self._btn.setToolTip(self._title)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._btn.setStyleSheet(
            f"""
            QPushButton {{
                text-align: left;
                padding: 4px 6px;
                background: {bg};
                border: none;
                border-radius: {TOKENS.radius_sm}px;
                color: {color};
                font-size: {TOKENS.font_size_micro};
            }}
            QPushButton:hover {{
                color: {TOKENS.neon_cyan};
                background: {TOKENS.panel_hover};
            }}
            """
        )
        self._btn.clicked.connect(self._on_title_clicked)
        h.addWidget(self._btn, 1)

        self._edit = QLineEdit(self._title)
        self._edit.setObjectName("ChatTitleEdit")
        self._edit.setMaxLength(48)
        self._edit.setStyleSheet(
            f"""
            QLineEdit#ChatTitleEdit {{
                background: {TOKENS.panel_hover};
                border: 1px solid {TOKENS.neon_cyan};
                border-radius: {TOKENS.radius_sm}px;
                color: {TOKENS.text_primary};
                padding: 2px 6px;
                font-size: {TOKENS.font_size_micro};
            }}
            """
        )
        self._edit.returnPressed.connect(self._commit_edit)
        self._edit.installEventFilter(self)
        self._edit.hide()
        h.addWidget(self._edit, 1)

        self._pencil = _EditTitleButton()
        self._pencil.clicked.connect(self._begin_edit)
        h.addWidget(self._pencil, 0, Qt.AlignmentFlag.AlignVCenter)

        x = _icon_button("×", f"대화 삭제: {self._title}", TOKENS.error, font_size=14)
        x.clicked.connect(lambda _=False, i=conv.id: on_delete(i))
        h.addWidget(x, 0, Qt.AlignmentFlag.AlignVCenter)

    def _on_title_clicked(self) -> None:
        if self._active:
            self._begin_edit()
            return
        self._on_open(self._conv_id)

    def _begin_edit(self) -> None:
        if self._editing:
            return
        self._editing = True
        self._ignore_focus_out = True
        self._on_edit_start(self._conv_id)
        self._btn.hide()
        self._pencil.hide()
        self._edit.setText(self._title)
        self._edit.show()
        self._edit.setFocus(Qt.FocusReason.OtherFocusReason)
        self._edit.selectAll()
        QTimer.singleShot(0, self._arm_focus_out)

    def _arm_focus_out(self) -> None:
        try:
            if self._editing:
                self._ignore_focus_out = False
        except RuntimeError:
            return

    def _end_edit(self) -> None:
        if not self._editing:
            return
        self._editing = False
        self._edit.hide()
        self._btn.show()
        self._pencil.show()
        self._on_edit_end()

    def _commit_edit(self) -> None:
        if not self._editing:
            return
        text = " ".join(self._edit.text().split())
        self._end_edit()
        if text and text != self._title:
            self._on_rename(self._conv_id, text)

    def _cancel_edit(self) -> None:
        if not self._editing:
            return
        self._end_edit()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._edit:
            if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
                if event.key() == Qt.Key.Key_Escape:
                    self._cancel_edit()
                    return True
            if event.type() == QEvent.Type.FocusOut:
                if not self._ignore_focus_out:
                    self._commit_edit()
                return False
        return super().eventFilter(obj, event)


class _EditTitleButton(QPushButton):
    """사이드바 제목 옆 — 가는 선 Edit 펜 아이콘."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ChatTitleEditButton")
        self.setFixedSize(16, 16)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("제목 수정")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(
            """
            QPushButton#ChatTitleEditButton {
                background: transparent;
                border: none;
                padding: 0;
            }
            """
        )

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(TOKENS.neon_cyan if self.underMouse() else TOKENS.text_muted)
        pen = QPen(color, 1.25)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        body = QPainterPath()
        body.moveTo(11.4, 2.6)
        body.lineTo(13.4, 4.6)
        body.lineTo(6.4, 11.6)
        body.lineTo(4.4, 9.6)
        body.closeSubpath()
        painter.drawPath(body)
        tip = QPainterPath()
        tip.moveTo(4.4, 9.6)
        tip.lineTo(2.6, 13.4)
        tip.lineTo(6.4, 11.6)
        painter.drawPath(tip)
        painter.drawLine(QPointF(10.2, 3.8), QPointF(12.2, 5.8))
        painter.end()


def _icon_button(text: str, tooltip: str, hover: str, *, font_size: int = 12) -> QPushButton:
    btn = QPushButton(text)
    btn.setFixedSize(20, 20)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setToolTip(tooltip)
    btn.setStyleSheet(
        f"""
        QPushButton {{
            background: transparent;
            border: none;
            padding: 0;
            color: {TOKENS.text_muted};
            font-size: {font_size}px;
        }}
        QPushButton:hover {{ color: {hover}; }}
        """
    )
    return btn
