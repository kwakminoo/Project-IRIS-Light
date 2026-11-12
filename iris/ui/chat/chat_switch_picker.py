"""Ctrl+Tab 채팅 목록. MainWindow 자식이고 세션은 열지 않는다."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QKeySequence, QMouseEvent, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from iris.runtime.chat_session import ChatSession
from iris.storage.conversations import DEFAULT_TITLE

_STYLE = """
QFrame#ChatSwitchPicker {
    background-color: #1b1e27;
    border: 1px solid #3a4154;
    border-radius: 8px;
}
QLabel#ChatSwitchRow {
    color: #e7e9ee;
    background: transparent;
    padding-left: 12px;
    padding-right: 12px;
}
QLabel#ChatSwitchRow[hot="true"] {
    background: #2c3344;
}
QLabel#ChatSwitchRow[current="true"] {
    color: #9ec1ff;
}
QLabel#ChatSwitchEmpty {
    color: #a3a8b4;
    padding-left: 12px;
}
"""


@dataclass(frozen=True)
class ChatSwitchRow:
    """한 번의 열기에서 고정된 대화 한 줄."""

    conversation_id: int
    title: str
    current: bool


def chat_switch_rows(session: ChatSession) -> tuple[ChatSwitchRow, ...]:
    """list_items() 순서를 유지한다. 세션을 만들지 않는다."""
    current = int(session.conversation_id)
    rows: list[ChatSwitchRow] = []
    for item in session.list_items():
        cid = int(item.id)
        if cid <= 0:
            continue
        title = (item.title or "").strip() or DEFAULT_TITLE
        rows.append(ChatSwitchRow(cid, title, cid == current))
    return tuple(rows)


def install_chat_switch_shortcut(
    host: QWidget,
    callback: Callable[[], None],
    *,
    existing: QShortcut | None = None,
) -> QShortcut:
    """Ctrl+Tab, WindowShortcut. 키 시퀀스와 컨텍스트의 단일 출처."""
    if existing is not None:
        try:
            existing.activated.disconnect()
        except TypeError:
            pass
        existing.activated.connect(callback)
        return existing
    shortcut = QShortcut(QKeySequence("Ctrl+Tab"), host)
    shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
    shortcut.activated.connect(callback)
    return shortcut


def _current_index(rows: tuple[ChatSwitchRow, ...]) -> int:
    for index, row in enumerate(rows):
        if row.current:
            return index
    if rows:
        return 0
    return -1


class ChatSwitchPicker(QFrame):
    """MainWindow 자식 오버레이. 창 플래그 없음."""

    conversation_chosen = pyqtSignal(int)

    def __init__(
        self,
        host: QWidget,
        on_dismiss: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(host)
        # Window 플래그는 부모를 잃고 «Iris Light» 창이 된다.
        self.setWindowFlags(Qt.WindowType.Widget)
        if self.parentWidget() is not host:
            self.setParent(host)
        self._rows: tuple[ChatSwitchRow, ...] = ()
        self._index = -1
        self._on_dismiss = on_dismiss
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 14, 0, 14)
        layout.setSpacing(0)
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetNoConstraint)
        self.setObjectName("ChatSwitchPicker")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(_STYLE)
        self.hide()
        host.installEventFilter(self)
        self.destroyed.connect(self._forget_app_filter)

    def toggle(self, rows: Sequence[ChatSwitchRow]) -> None:
        if self.is_open():
            self.dismiss()
            return
        self._open(tuple(rows))

    def dismiss(self) -> None:
        if not self.isVisible():
            return
        self.hide()
        self._index = -1
        self._set_outside_filter(False)
        callback = self._on_dismiss
        if callback is not None:
            callback()

    def is_open(self) -> bool:
        return self.isVisible()

    def _open(self, rows: tuple[ChatSwitchRow, ...]) -> None:
        self._rows = rows
        self._index = _current_index(rows)
        self._fill()
        self._place()
        self._set_outside_filter(True)
        self.raise_()
        self.show()
        self.setFocus()

    def _choose(self, index: int) -> None:
        if not self.is_open():
            return
        if index < 0 or index >= len(self._rows):
            return
        cid = self._rows[index].conversation_id
        self.dismiss()
        self.conversation_chosen.emit(cid)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        mods = event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.ShiftModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
        )
        if key == Qt.Key.Key_Tab and mods == Qt.KeyboardModifier.ControlModifier:
            event.ignore()
            return
        count = len(self._rows)
        if key == Qt.Key.Key_Up and count:
            self._index = (self._index - 1) % count
            self._sync_hot()
            event.accept()
            return
        if key == Qt.Key.Key_Down and count:
            self._index = (self._index + 1) % count
            self._sync_hot()
            event.accept()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._choose(self._index)
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self.dismiss()
            event.accept()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        if not self.is_open() or event is None or watched is None:
            return False
        if event.type() != QEvent.Type.MouseButtonPress or not isinstance(event, QMouseEvent):
            return False
        host = self.parentWidget()
        if host is None:
            return False
        if watched is not host and not host.isAncestorOf(watched):
            return False
        # 피커 자식 클릭은 행 선택이다. 밖은 닫기만 하고 사이드바로 내리지 않는다.
        if watched is self or self.isAncestorOf(watched):
            return False
        local = self.mapFromGlobal(event.globalPosition().toPoint())
        if self.rect().contains(local):
            return False
        self.dismiss()
        return True

    def _place(self) -> None:
        host = self.parentWidget()
        count = len(self._rows) if self._rows else 1
        height = min(360, 28 + 32 * count)
        width = 280
        left = 0
        if host is not None:
            left = max(0, (host.width() - width) // 2)
        self.setFixedSize(width, height)
        self.move(left, 72)

    def _fill(self) -> None:
        layout = self.layout()
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        if not self._rows:
            empty = QLabel("대화 없음", self)
            empty.setObjectName("ChatSwitchEmpty")
            empty.setEnabled(False)
            empty.setFixedHeight(32)
            empty.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            layout.addWidget(empty)
            return
        for index, row in enumerate(self._rows):
            layout.addWidget(
                _SwitchRow(
                    self,
                    index,
                    row.title,
                    current=row.current,
                    hot=index == self._index,
                )
            )

    def _sync_hot(self) -> None:
        layout = self.layout()
        if layout is None:
            return
        for index in range(layout.count()):
            item = layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is None or widget.objectName() != "ChatSwitchRow":
                continue
            widget.setProperty("hot", index == self._index)
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)
            widget.update()

    def _forget_app_filter(self, *_args: object) -> None:
        self._set_outside_filter(False)

    def _set_outside_filter(self, active: bool) -> None:
        # 호스트 필터는 호스트 자신에게만 온다. 자식(사이드바) 클릭은 앱에서 본다.
        app = QApplication.instance()
        if app is None:
            return
        app.removeEventFilter(self)
        if active:
            app.installEventFilter(self)


class _SwitchRow(QLabel):
    def __init__(
        self,
        picker: ChatSwitchPicker,
        index: int,
        title: str,
        *,
        current: bool,
        hot: bool,
    ) -> None:
        super().__init__(title, picker)
        self._picker = picker
        self._index = index
        self.setObjectName("ChatSwitchRow")
        self.setFixedHeight(32)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setProperty("current", current)
        self.setProperty("hot", hot)

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        self._picker._choose(self._index)
        if event is not None:
            event.accept()
