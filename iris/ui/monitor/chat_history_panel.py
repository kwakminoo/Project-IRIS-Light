"""좌측 사이드바 — 저장된 대화 목록 + 새 채팅."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QKeyEvent, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QApplication,
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

from iris.storage.chat_projects import ChatProject
from iris.storage.conversations import ChatConversation, DEFAULT_TITLE
from iris.ui.monitor.chat_list_select import apply_list_click
from iris.ui.shared.section_header import (
    SECTION_CONTENT_GAP,
    SECTION_TITLE_LINE_GAP,
    apply_section_panel_layout,
)
from iris.ui.shared.theme_tokens import TOKENS


class ChatHistoryPanel(QWidget):
    """CHATS 섹션 — 세션 목록·제목 수정·삭제 요청."""

    new_chat_requested = pyqtSignal()
    new_project_requested = pyqtSignal(str)
    project_chat_requested = pyqtSignal(int)
    conversation_selected = pyqtSignal(int)
    conversation_delete_requested = pyqtSignal(int)
    conversation_rename_requested = pyqtSignal(int, str)
    items_delete_requested = pyqtSignal(object)
    items_rename_requested = pyqtSignal(object, str)

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
        folder = _NewProjectButton()
        folder.clicked.connect(self._ask_new_project)
        title_row.addWidget(folder, 0, Qt.AlignmentFlag.AlignRight)
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
        self._inner.setMinimumWidth(0)
        self._inner_lay = QVBoxLayout(self._inner)
        self._inner_lay.setContentsMargins(0, 0, 0, 0)
        self._inner_lay.setSpacing(SECTION_CONTENT_GAP)
        self._inner_lay.addStretch(1)
        self._scroll.setWidget(self._inner)
        root.addWidget(self._scroll, 1)

        self._items: list[ChatConversation] = []
        self._projects: list[ChatProject] = []
        self._active_id = 0
        self._editing_id = 0
        self._order: list[tuple[str, int]] = []
        self._selected: list[tuple[str, int]] = []
        self._anchor: tuple[str, int] | None = None
        self._pending: tuple[list[ChatConversation], int, list[ChatProject]] | None = None

    def set_conversations(
        self,
        items: list[ChatConversation],
        *,
        active_id: int = 0,
        projects: list[ChatProject] | None = None,
    ) -> None:
        packed = (list(items), int(active_id or 0), list(projects or []))
        if self._editing_id:
            self._pending = packed
            return
        if getattr(self, "_painted", False) and packed == (
            self._items,
            self._active_id,
            self._projects,
        ):
            return
        self._items, self._active_id, self._projects = packed
        self._painted = True
        self._rebuild()

    def _rebuild(self) -> None:
        while self._inner_lay.count():
            item = self._inner_lay.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.deleteLater()

        order: list[tuple[str, int]] = []
        by_project: dict[int, list[ChatConversation]] = {}
        loose: list[ChatConversation] = []
        known = {int(project.id) for project in self._projects}
        for conv in self._items:
            folder = int(conv.project_id or 0)
            if folder > 0 and folder in known:
                by_project.setdefault(folder, []).append(conv)
            else:
                loose.append(conv)
        if not self._projects and not loose:
            hint = QLabel("— no chats yet")
            hint.setStyleSheet(
                f"color: {TOKENS.text_muted}; font-size: {TOKENS.font_size_micro};"
                " padding: 8px 4px; background: transparent;"
            )
            self._inner_lay.addWidget(hint)
        else:
            for project in self._projects:
                key = ("p", int(project.id))
                order.append(key)
                self._inner_lay.addWidget(
                    _ProjectRow(
                        project,
                        selected=key in self._selected,
                        on_click=self._on_row_click,
                        on_delete=self._on_delete_key,
                        on_rename=self._on_rename_key,
                        on_new_chat=self._on_project_chat,
                        on_edit_start=self._on_edit_start,
                        on_edit_end=self._on_edit_end,
                    )
                )
                for conv in by_project.get(int(project.id), []):
                    child = ("c", int(conv.id))
                    order.append(child)
                    self._inner_lay.addWidget(self._chat_row(conv, nested=True))
            for conv in loose:
                order.append(("c", int(conv.id)))
                self._inner_lay.addWidget(self._chat_row(conv, nested=False))
        self._order = order
        alive = set(order)
        self._selected = [key for key in self._selected if key in alive]
        if self._anchor not in alive:
            self._anchor = self._selected[-1] if self._selected else None
        self._inner_lay.addStretch(1)

    def _chat_row(self, conv: ChatConversation, *, nested: bool) -> _ChatRow:
        key = ("c", int(conv.id))
        sole = self._selected == [key]
        return _ChatRow(
            conv,
            conv.id == self._active_id,
            selected=key in self._selected,
            nested=nested,
            edit_on_plain_click=conv.id == self._active_id and sole,
            on_open=self._on_open,
            on_delete=self._on_delete_key,
            on_rename=self._on_rename_key,
            on_edit_start=self._on_edit_start,
            on_edit_end=self._on_edit_end,
        )

    def _ask_new_project(self) -> None:
        from iris.ui.settings.hud_dialog import run_hud_prompt

        name = run_hud_prompt(
            None,
            title="프로젝트 폴더",
            body="프로젝트 폴더 이름을 입력하세요.",
            hint="만들면 같은 이름으로 위키에 저장됩니다.",
            placeholder="폴더 이름",
            ok_text="생성",
        )
        if name:
            self.new_project_requested.emit(name)

    def _on_project_chat(self, project_id: int) -> None:
        self.project_chat_requested.emit(int(project_id))

    def _on_row_click(self, kind: str, item_id: int, ctrl: bool, shift: bool) -> None:
        key = (kind, int(item_id))
        self._selected, self._anchor = apply_list_click(
            self._order, self._selected, self._anchor, key, ctrl=ctrl, shift=shift,
        )
        self._rebuild()
        if kind == "c" and not ctrl and not shift:
            self.conversation_selected.emit(int(item_id))

    def _target_keys(self, kind: str, item_id: int) -> list[tuple[str, int]]:
        key = (kind, int(item_id))
        if key in self._selected and len(self._selected) > 1:
            return list(self._selected)
        return [key]

    def _on_open(self, conv_id: int, ctrl: bool, shift: bool) -> None:
        self._on_row_click("c", int(conv_id), ctrl, shift)

    def _on_delete_key(self, kind: str, item_id: int) -> None:
        self.items_delete_requested.emit(self._target_keys(kind, item_id))

    def _on_rename_key(self, kind: str, item_id: int, title: str) -> None:
        self.items_rename_requested.emit(self._target_keys(kind, item_id), title)

    def _on_edit_start(self, conv_id: int) -> None:
        self._editing_id = int(conv_id)

    def _on_edit_end(self) -> None:
        self._editing_id = 0
        pending = self._pending
        self._pending = None
        if pending is not None:
            self.set_conversations(pending[0], active_id=pending[1], projects=pending[2])


class _ChatRow(QFrame):
    def __init__(
        self,
        conv: ChatConversation,
        active: bool,
        *,
        selected: bool = False,
        nested: bool = False,
        edit_on_plain_click: bool = False,
        on_open,
        on_delete,
        on_rename,
        on_edit_start,
        on_edit_end,
    ) -> None:
        super().__init__()
        self.setObjectName("HudChatRow")
        # 레이아웃이 이벤트를 먼저 보내도 eventFilter 가 AttributeError 로 앱을 죽이지 않게 둔다.
        self._btn = None
        self._edit = None
        self._conv_id = conv.id
        self._title = (conv.title or DEFAULT_TITLE).strip() or DEFAULT_TITLE
        self._active = active
        self._selected = selected
        self._edit_on_plain_click = edit_on_plain_click
        self._on_open = on_open
        self._on_delete = on_delete
        self._on_rename = on_rename
        self._on_edit_start = on_edit_start
        self._on_edit_end = on_edit_end
        self._editing = False
        self._ignore_focus_out = False
        self._fitting = False
        self._fit_pending = False
        self.setMinimumWidth(0)

        h = QHBoxLayout(self)
        h.setContentsMargins(16 if nested else 2, 2, 2, 2)
        h.setSpacing(2)

        color = TOKENS.neon_cyan if active else (TOKENS.text_primary if selected else TOKENS.text_secondary)
        bg = TOKENS.panel_hover if (active or selected) else "transparent"
        border = (
            f"1px solid {TOKENS.neon_cyan}" if selected and not active else "none"
        )
        self._btn = _ShrinkingTitleButton(self._title)
        self._btn.setToolTip(self._title)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._btn.setMinimumWidth(0)
        self._btn.setStyleSheet(
            f"""
            QPushButton {{
                text-align: left;
                padding: 4px 6px;
                background: {bg};
                border: {border};
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
        self._btn.installEventFilter(self)
        self._edit.hide()
        h.addWidget(self._edit, 1)

        self._pencil = _EditTitleButton()
        self._pencil.clicked.connect(self._begin_edit)
        h.addWidget(self._pencil, 0, Qt.AlignmentFlag.AlignVCenter)

        x = _icon_button("×", f"대화 삭제: {self._title}", TOKENS.error, font_size=14)
        x.clicked.connect(lambda _=False, i=conv.id: on_delete("c", i))
        h.addWidget(x, 0, Qt.AlignmentFlag.AlignVCenter)
        self._schedule_fit_title()

    def _on_title_clicked(self) -> None:
        mods = QApplication.keyboardModifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        if ctrl or shift or not self._edit_on_plain_click:
            self._on_open(self._conv_id, ctrl, shift)
            return
        self._begin_edit()

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
        if text:
            self._on_rename("c", self._conv_id, text)

    def _cancel_edit(self) -> None:
        if not self._editing:
            return
        self._end_edit()

    def _schedule_fit_title(self) -> None:
        if self._fit_pending:
            return
        self._fit_pending = True
        QTimer.singleShot(0, self._fit_title_later)

    def _fit_title_later(self) -> None:
        self._fit_pending = False
        try:
            self._fit_title()
        except RuntimeError:
            return

    def _fit_title(self) -> None:
        if self._editing or self._fitting:
            return
        self._fitting = True
        try:
            avail = max(0, self._btn.width() - 12)
            shown = self._btn.fontMetrics().elidedText(
                self._title, Qt.TextElideMode.ElideRight, avail
            )
            if self._btn.text() != shown:
                self._btn.setText(shown)
        finally:
            self._fitting = False

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        btn = getattr(self, "_btn", None)
        edit = getattr(self, "_edit", None)
        if btn is None or edit is None:
            return False
        if obj is btn and event.type() == QEvent.Type.Resize:
            self._schedule_fit_title()
            return False
        if obj is edit:
            if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
                if event.key() == Qt.Key.Key_Escape:
                    self._cancel_edit()
                    return True
            if event.type() == QEvent.Type.FocusOut:
                if not self._ignore_focus_out:
                    self._commit_edit()
                return False
        return super().eventFilter(obj, event)


class _ShrinkingTitleButton(QPushButton):
    """제목이 길어도 옆 아이콘 폭을 밀지 않는다.

    sizeHint 를 다시 부르면 Qt 가 minimumSizeHint 와 순환한다.
    """

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, 24)


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


class _ProjectRow(QFrame):
    def __init__(
        self,
        project: ChatProject,
        *,
        selected: bool,
        on_click,
        on_delete,
        on_rename,
        on_new_chat,
        on_edit_start,
        on_edit_end,
    ) -> None:
        super().__init__()
        self.setObjectName("HudProjectRow")
        self._project_id = int(project.id)
        self._title = (project.name or "").strip() or "프로젝트"
        self._on_click = on_click
        self._on_delete = on_delete
        self._on_rename = on_rename
        self._on_edit_start = on_edit_start
        self._on_edit_end = on_edit_end
        self._editing = False
        self._ignore_focus_out = False
        self._btn = None
        self._edit = None

        h = QHBoxLayout(self)
        h.setContentsMargins(2, 2, 2, 2)
        h.setSpacing(2)
        bg = TOKENS.panel_hover if selected else "transparent"
        border = f"1px solid {TOKENS.neon_cyan}" if selected else "none"
        self._btn = QPushButton(self._title)
        self._btn.setToolTip(self._title)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._btn.setStyleSheet(
            f"""
            QPushButton {{
                text-align: left;
                padding: 4px 6px;
                background: {bg};
                border: {border};
                border-radius: {TOKENS.radius_sm}px;
                color: {TOKENS.text_primary};
                font-size: {TOKENS.font_size_micro};
                font-weight: 600;
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
        self._edit.setMaxLength(48)
        self._edit.setStyleSheet(
            f"""
            QLineEdit {{
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

        add = _icon_button("+", "이 폴더에 채팅 만들기", TOKENS.neon_cyan, font_size=14)
        add.clicked.connect(lambda _=False, i=project.id: on_new_chat(i))
        h.addWidget(add, 0, Qt.AlignmentFlag.AlignVCenter)
        pencil = _EditTitleButton()
        pencil.clicked.connect(self._begin_edit)
        h.addWidget(pencil, 0, Qt.AlignmentFlag.AlignVCenter)
        remove = _icon_button("×", f"폴더 삭제: {self._title}", TOKENS.error, font_size=14)
        remove.clicked.connect(lambda _=False, i=project.id: on_delete("p", i))
        h.addWidget(remove, 0, Qt.AlignmentFlag.AlignVCenter)

    def _on_title_clicked(self) -> None:
        mods = QApplication.keyboardModifiers()
        self._on_click(
            "p",
            self._project_id,
            bool(mods & Qt.KeyboardModifier.ControlModifier),
            bool(mods & Qt.KeyboardModifier.ShiftModifier),
        )

    def _begin_edit(self) -> None:
        if self._editing:
            return
        self._editing = True
        self._ignore_focus_out = True
        self._on_edit_start(self._project_id)
        self._btn.hide()
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
        self._on_edit_end()

    def _commit_edit(self) -> None:
        if not self._editing:
            return
        text = " ".join(self._edit.text().split())
        self._end_edit()
        if text:
            self._on_rename("p", self._project_id, text)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        edit = getattr(self, "_edit", None)
        if edit is None or obj is not edit:
            return super().eventFilter(obj, event)
        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            if event.key() == Qt.Key.Key_Escape:
                if self._editing:
                    self._end_edit()
                return True
        if event.type() == QEvent.Type.FocusOut and not self._ignore_focus_out:
            self._commit_edit()
        return False


class _NewProjectButton(QPushButton):
    """폴더 아이콘, 오른쪽 아래에 작은 +."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ChatNewProjectButton")
        self.setFixedSize(22, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("프로젝트 폴더")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(
            """
            QPushButton#ChatNewProjectButton {
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

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(TOKENS.neon_cyan if self.underMouse() else TOKENS.text_muted)
        pen = QPen(color, 1.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        tab = QPainterPath()
        tab.moveTo(2.2, 6.2)
        tab.lineTo(2.2, 4.4)
        tab.lineTo(7.2, 4.4)
        tab.lineTo(8.6, 6.2)
        tab.lineTo(15.2, 6.2)
        tab.lineTo(15.2, 13.6)
        tab.lineTo(2.2, 13.6)
        tab.closeSubpath()
        painter.drawPath(tab)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(12.2, 10.2, 8.0, 8.0))
        painter.setPen(QPen(QColor(TOKENS.void_black), 1.3))
        painter.drawLine(QPointF(16.2, 12.4), QPointF(16.2, 16.0))
        painter.drawLine(QPointF(14.4, 14.2), QPointF(18.0, 14.2))
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
