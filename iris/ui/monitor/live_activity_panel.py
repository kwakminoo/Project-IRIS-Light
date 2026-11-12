"""Live Activity / Internal Log — 실제 파이프라인 이벤트 스트림 (English only)."""

from __future__ import annotations

from collections import deque

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPalette, QTextCursor, QWheelEvent
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from iris.core.activity_privacy import prepare_activity_line, strip_emoji
from iris.ui.shared.theme_tokens import TOKENS


class UiActivityRelay(QObject):
    """push_activity_line 싱크를 Qt 메인 스레드로 안전하게 넘김."""

    line = pyqtSignal(str)

    def push(self, message: str) -> None:
        safe = prepare_activity_line(message)
        if safe:
            self.line.emit(safe)


_MAX_DOC_LINES = 800
_CHARS_PER_TICK_IDLE = 2
_CHARS_BURST = 8
_TICK_MS = 32
_PANEL_MAX_HEIGHT = 180
_THINK_PREVIEW = 50
_THINK_EXPANDED_HEIGHT = 320


class _LiveActivityLogEdit(QPlainTextEdit):
    def __init__(self, on_user_scroll, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._on_user_scroll = on_user_scroll

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        super().wheelEvent(event)
        self._on_user_scroll()


class LiveActivityPanel(QWidget):
    """
    Visualizer(구체)와 채팅 패널 사이 — Ollama thinking / 연결 로그.
    줄 단위 큐 + 문자 단위 타핑, thinking 청크는 즉시 삽입.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LiveActivityPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setStyleSheet(
            """
            QWidget#LiveActivityPanel {
                background: transparent;
            }
            """
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 3)
        lay.setSpacing(2)

        hdr = QLabel("Live Activity / Internal Log")
        hdr.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        hdr.setAutoFillBackground(False)
        hdr.setStyleSheet(
            f"color: {TOKENS.text_hud_label}; font-size: {TOKENS.font_size_hud}; font-weight: 500;"
            " letter-spacing: 1px; background: transparent;"
        )
        lay.addWidget(hdr)

        self._think_btn = QPushButton("")
        self._think_btn.setObjectName("LiveActivityThink")
        self._think_btn.setVisible(False)
        self._think_btn.setFlat(True)
        self._think_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._think_btn.setStyleSheet(
            f"color: {TOKENS.text_hud_label}; text-align: left; padding: 0 2px;"
            " background: transparent; border: none;"
        )
        self._think_btn.clicked.connect(self._toggle_think_body)
        lay.addWidget(self._think_btn)

        self._think_body = QPlainTextEdit()
        self._think_body.setObjectName("LiveActivityThinkBody")
        self._think_body.setVisible(False)
        self._think_body.setReadOnly(True)
        self._think_body.setUndoRedoEnabled(False)
        self._think_body.setFrameShape(QFrame.Shape.NoFrame)
        self._think_body.setMaximumHeight(140)
        self._think_body.setStyleSheet(
            "QPlainTextEdit#LiveActivityThinkBody {"
            " background: transparent; color: rgba(226, 232, 240, 0.78);"
            " border: none; padding: 0 2px; }"
        )
        lay.addWidget(self._think_body)

        self._editor = _LiveActivityLogEdit(self._note_user_log_scroll)
        self._editor.setObjectName("LiveActivityLog")
        self._editor.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._editor.setAutoFillBackground(False)
        self._editor.setReadOnly(True)
        self._editor.setUndoRedoEnabled(False)
        self._editor.setPlaceholderText("Idle.")
        self._editor.setMaximumBlockCount(_MAX_DOC_LINES)
        font = QFont("Consolas", 10)
        if not font.exactMatch():
            font = QFont("Courier New", 10)
        self._editor.setFont(font)
        self._editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._editor.setFrameShape(QFrame.Shape.NoFrame)
        transparent = QColor(0, 0, 0, 0)
        editor_pal = self._editor.palette()
        editor_pal.setColor(QPalette.ColorRole.Base, transparent)
        editor_pal.setColor(QPalette.ColorRole.Window, transparent)
        self._editor.setPalette(editor_pal)
        self._editor.setStyleSheet(
            """
            QPlainTextEdit#LiveActivityLog {
                background: transparent;
                background-color: transparent;
                color: rgba(226, 232, 240, 0.68);
                border: none;
                outline: none;
                padding: 0 2px 2px 2px;
            }
            QPlainTextEdit#LiveActivityLog QScrollBar:vertical {
                width: 6px;
                background: transparent;
            }
            QPlainTextEdit#LiveActivityLog QScrollBar::handle:vertical {
                background: rgba(148, 163, 184, 0.35);
                border-radius: 3px;
                min-height: 20px;
            }
            QPlainTextEdit#LiveActivityLog QScrollBar:horizontal {
                height: 0px;
            }
            """
        )
        lay.addWidget(self._editor, 1)
        self.setMinimumHeight(72)
        self.setMaximumHeight(_PANEL_MAX_HEIGHT)

        self._queue: deque[str] = deque()
        self._current_line: str = ""
        self._cursor_pos = 0
        self._reasoning = ""
        self._user_request = ""
        self._scroll_user_hold = False
        self._scroll_follow_tail = True
        self._scroll_hold_value: int | None = None
        self._scroll_programmatic = 0
        self._applying_held_scroll = False
        bar = self._editor.verticalScrollBar()
        bar.actionTriggered.connect(self._on_log_scroll_action)
        bar.sliderMoved.connect(self._on_log_slider_moved)
        bar.rangeChanged.connect(self._reapply_held_log_scroll)
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._on_tick)

    def begin_turn(self, user_text: str = "") -> None:
        self._reasoning = ""
        self._think_body.clear()
        self._think_body.setVisible(False)
        self.setMaximumHeight(_PANEL_MAX_HEIGHT)
        collapsed = " ".join((user_text or "").split())
        self._user_request = strip_emoji(collapsed) if collapsed else ""
        if self._user_request:
            self._think_btn.setText(self._user_request[:_THINK_PREVIEW])
            self._think_btn.setVisible(True)
        else:
            self._think_btn.setText("")
            self._think_btn.setVisible(False)
        self._scroll_user_hold = False
        self._scroll_follow_tail = True
        self._scroll_hold_value = None

    def enqueue_typed_line(self, line: str) -> None:
        """메인 스레드에서만 호출 (Relay 시그널 슬롯)."""
        safe = prepare_activity_line(line) if line else ""
        if not safe:
            return
        self._queue.append(safe)
        if not self._timer.isActive():
            self._timer.start()

    def append_instant_line(self, line: str) -> None:
        """한 줄을 즉시 추가 (줄바꿈 포함)."""
        safe = prepare_activity_line(line) if line else ""
        if not safe:
            return
        self._insert_at_end(safe if safe.endswith("\n") else safe + "\n")

    def append_instant_chunk(self, text: str) -> None:
        """thinking 스트림 청크 — 줄바꿈 없이 이어붙임."""
        safe = strip_emoji(text) if text else ""
        if not safe:
            return
        self._insert_at_end(safe)

    def append_reasoning(self, chunk: str) -> None:
        """Model reasoning stream — preview button + expandable body."""
        safe = strip_emoji(chunk) if chunk else ""
        if not safe:
            return
        self._reasoning += safe
        if self._user_request:
            self._think_btn.setText(self._user_request[:_THINK_PREVIEW])
        else:
            self._think_btn.setText(self._reasoning[:_THINK_PREVIEW])
        self._think_btn.setVisible(True)
        self._think_body.setPlainText(self._reasoning)
        if self._think_body.isVisible():
            self.setMaximumHeight(_THINK_EXPANDED_HEIGHT)

    def _toggle_think_body(self) -> None:
        open_body = not self._think_body.isVisible()
        self._think_body.setVisible(open_body)
        self.setMaximumHeight(
            _THINK_EXPANDED_HEIGHT if open_body else _PANEL_MAX_HEIGHT
        )

    def _insert_at_end(self, text: str) -> None:
        cur = QTextCursor(self._editor.document())
        cur.movePosition(QTextCursor.MoveOperation.End)
        cur.insertText(text)
        self._scroll_log_to_bottom()

    def _scroll_log_to_bottom(self, *, deferred: bool = False) -> None:
        def _do_scroll() -> None:
            bar = self._editor.verticalScrollBar()
            self._scroll_programmatic += 1
            try:
                if self._scroll_user_hold and self._scroll_hold_value is not None:
                    bar.setValue(min(self._scroll_hold_value, bar.maximum()))
                elif self._scroll_follow_tail:
                    bar.setValue(bar.maximum())
            finally:
                self._scroll_programmatic -= 1

        if deferred:
            QTimer.singleShot(0, _do_scroll)
        else:
            _do_scroll()

    def _on_log_scroll_action(self, _action: int) -> None:
        self._note_user_log_scroll(self._editor.verticalScrollBar().sliderPosition())

    def _on_log_slider_moved(self, value: int) -> None:
        self._note_user_log_scroll(value)

    def _note_user_log_scroll(self, value: int | None = None) -> None:
        if self._scroll_programmatic:
            return
        bar = self._editor.verticalScrollBar()
        if value is None:
            value = bar.value()
        self._scroll_follow_tail = value >= bar.maximum() - 2
        self._scroll_user_hold = not self._scroll_follow_tail
        self._scroll_hold_value = value if self._scroll_user_hold else None

    def _reapply_held_log_scroll(self, _minimum: int, maximum: int) -> None:
        if self._scroll_programmatic or self._applying_held_scroll:
            return
        bar = self._editor.verticalScrollBar()
        self._applying_held_scroll = True
        self._scroll_programmatic += 1
        try:
            if self._scroll_user_hold and self._scroll_hold_value is not None:
                bar.setValue(min(self._scroll_hold_value, maximum))
            elif self._scroll_follow_tail:
                bar.setValue(maximum)
        finally:
            self._scroll_programmatic -= 1
            self._applying_held_scroll = False

    def _on_tick(self) -> None:
        if not self._current_line:
            if not self._queue:
                self._timer.stop()
                return
            self._current_line = self._queue.popleft()
            self._cursor_pos = 0

        burst = _CHARS_BURST if len(self._queue) >= 4 else _CHARS_PER_TICK_IDLE
        end = min(len(self._current_line), self._cursor_pos + burst)
        chunk = self._current_line[self._cursor_pos:end]
        self._cursor_pos = end

        cur = QTextCursor(self._editor.document())
        cur.movePosition(QTextCursor.MoveOperation.End)
        cur.insertText(chunk)

        if self._cursor_pos >= len(self._current_line):
            cur = QTextCursor(self._editor.document())
            cur.movePosition(QTextCursor.MoveOperation.End)
            cur.insertText("\n")
            self._current_line = ""
            self._cursor_pos = 0

        self._scroll_log_to_bottom()

    def clear_for_idle(self) -> None:
        """Idle 복귀 시 과한 잔상을 줄이고 placeholder에 맡김."""
        self._queue.clear()
        self._current_line = ""
        self._cursor_pos = 0
        self._reasoning = ""
        self._user_request = ""
        self._timer.stop()
        self._editor.clear()
        self._think_body.clear()
        self._think_body.setVisible(False)
        self._think_btn.setText("")
        self._think_btn.setVisible(False)
        self.setMaximumHeight(_PANEL_MAX_HEIGHT)
