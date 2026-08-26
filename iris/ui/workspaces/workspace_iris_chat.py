"""워크스페이스(이메일·캘린더 등) Iris 채팅 — IDE ChatPanel과 동일 크롬."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QPalette, QTextCursor
from PyQt6.QtWidgets import (
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from iris.core.activity_privacy import prepare_chat_text, strip_emoji
from iris.core.chat_citations import iris_message_to_chat_html
from iris.ui.chat.chat_display import (
    chat_body_to_html,
    normalize_chat_body,
    typing_body_to_html,
    visible_typing_text,
)
from iris.ui.chat.chat_image_view import (
    attach_image_loader,
    handle_chat_anchor_click,
    prefetch_chat_html_images,
)
from iris.ui.chat.chat_panel import _ChatInputArea
from iris.ui.widgets.particle_visualizer import ParticleVisualizer
from iris.ui.workspaces.ide_companion_page import EMAIL_ORB_SCALE


class WorkspaceIrisChatLog(QTextEdit):
    """우측 Iris 패널 로그 — ChatLog와 동일 투명/패딩 + 마크다운."""

    def __init__(self, object_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setReadOnly(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        transparent = self.palette()
        from PyQt6.QtGui import QColor

        transparent.setColor(QPalette.ColorRole.Base, QColor(0, 0, 0, 0))
        transparent.setColor(QPalette.ColorRole.Window, QColor(0, 0, 0, 0))
        self.setPalette(transparent)
        self.document().setDocumentMargin(8.0)
        self.document().setDefaultFont(self.font())
        self.setStyleSheet(
            f"""
            QTextEdit#{object_name} {{
                background: transparent;
                border: none;
                color: #e2e8f0;
                padding: 8px 10px;
            }}
            """
        )
        attach_image_loader(self)
        self._iris_active = False
        self._iris_buf = ""
        self._iris_body_start: int | None = None

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        anchor = self.anchorAt(event.pos())
        if handle_chat_anchor_click(self, anchor):
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _scroll_bottom(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _append_trailing_blank(self) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml("<br>")
        self.setTextCursor(cursor)

    def append_user(self, text: str) -> None:
        self.end_iris()
        body = normalize_chat_body("You", prepare_chat_text(text))
        if not body:
            return
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(f"<p><b>You</b>: {chat_body_to_html(body)}</p>")
        self.setTextCursor(cursor)
        self._append_trailing_blank()
        self._scroll_bottom()

    def append_iris_chunk(self, text: str) -> None:
        chunk = prepare_chat_text(text or "")
        if not chunk:
            return
        if not self._iris_active:
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertHtml("<p><b>Iris</b>: </p>")
            self._iris_body_start = cursor.position()
            self.setTextCursor(cursor)
            self._iris_active = True
            self._iris_buf = ""
        self._iris_buf += chunk
        self._replace_iris_body(
            typing_body_to_html(
                visible_typing_text(
                    self._iris_buf,
                    len(self._iris_buf),
                    render_markdown=True,
                )
            )
        )

    def _replace_iris_body(self, html_body: str) -> None:
        if self._iris_body_start is None:
            return
        cursor = self.textCursor()
        cursor.setPosition(self._iris_body_start)
        cursor.movePosition(
            QTextCursor.MoveOperation.End,
            QTextCursor.MoveMode.KeepAnchor,
        )
        cursor.removeSelectedText()
        cursor.insertHtml(html_body)
        self.setTextCursor(cursor)
        self._scroll_bottom()

    def end_iris(self, final_text: str | None = None) -> None:
        if not self._iris_active and final_text is None:
            return
        if final_text is not None:
            self._iris_buf = prepare_chat_text(final_text)
            if not self._iris_active:
                cursor = self.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                cursor.insertHtml("<p><b>Iris</b>: </p>")
                self._iris_body_start = cursor.position()
                self.setTextCursor(cursor)
                self._iris_active = True
        body = normalize_chat_body("Iris", self._iris_buf)
        if body and self._iris_body_start is not None:
            html_body = iris_message_to_chat_html(body)
            prefetch_chat_html_images(self, html_body)
            self._replace_iris_body(html_body)
            self._append_trailing_blank()
        self._iris_active = False
        self._iris_buf = ""
        self._iris_body_start = None
        self._scroll_bottom()

    def append_iris_tool(self, text: str) -> None:
        self.end_iris()
        safe = strip_emoji(prepare_chat_text(text or ""))
        if not safe:
            return
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(
            f"<p style='color:#64748b; font-size:11px;'>· {chat_body_to_html(safe)}</p>"
        )
        self.setTextCursor(cursor)
        self._scroll_bottom()

    def append_iris_error(self, text: str) -> None:
        self.end_iris()
        safe = strip_emoji(prepare_chat_text(text or ""))
        if not safe:
            return
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(
            f"<p style='color:#f87171; font-size:12px;'>{chat_body_to_html(safe)}</p>"
        )
        self.setTextCursor(cursor)
        self._scroll_bottom()


class WorkspaceIrisPanel(QWidget):
    """우측 — 오브 + IDE ChatPanel과 동일 입력/로그 크롬 (레이아웃은 워크스페이스 유지)."""

    chat_send = pyqtSignal(str)

    def __init__(
        self,
        *,
        name_prefix: str,
        placeholder: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        # EmailIrisPanel / CalendarIrisPanel — cyberspace_theme 셀렉터 유지
        self.setObjectName(f"{name_prefix}IrisPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)

        # IDE Companion 과 동일 스택: 오브 · Live Activity · 채팅 로그 · 입력
        self.orb = ParticleVisualizer(self)
        self.orb.setMinimumHeight(220)
        self.orb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.orb.set_size_scale(EMAIL_ORB_SCALE)
        col.addWidget(self.orb, 0)

        # LiveActivityPanel 슬롯 — main_window가 addWidget으로 원자적 reparent
        self._activity_host = QWidget(self)
        self._activity_host.setObjectName(f"{name_prefix}ActivityHost")
        self._activity_host.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._activity_lay = QVBoxLayout(self._activity_host)
        self._activity_lay.setContentsMargins(0, 0, 0, 0)
        self._activity_lay.setSpacing(0)
        self._activity_host.setMinimumHeight(0)
        self._activity_host.setMaximumHeight(0)
        self._activity_host.hide()
        self._live_mounted: QWidget | None = None
        col.addWidget(self._activity_host, 0)

        self._log = WorkspaceIrisChatLog(f"{name_prefix}ChatLog")
        col.addWidget(self._log, 1)

        # ponytail: IDE ChatPanel 입력 크롬 그대로 (+ · 입력 · 전송 · 파형).
        # 모델 콤보는 메인 ChatPanel이 소유 — 이중 피커 방지로 숨김.
        self._default_placeholder = placeholder
        self._input_area = _ChatInputArea()
        bar = self._input_area.input_bar
        bar._model_shell.hide()
        bar.input.setPlaceholderText(placeholder)
        bar.input.submit_requested.connect(self._emit_send)
        bar.send_button.clicked.connect(self._emit_send)
        bar.input.textChanged.connect(self._sync_send_enabled)
        self._sync_send_enabled()
        col.addWidget(self._input_area, 0)

    def _sync_send_enabled(self) -> None:
        has = bool(self._input_area.input_bar.input.text().strip())
        self._input_area.input_bar.send_button.setEnabled(has)

    def set_listening_status(self, status: str) -> None:
        """상시 듣기 상태 문구 — IDE ChatPanel placeholder와 동일 역할."""
        text = (status or "").strip()
        self._input_area.input_bar.input.setPlaceholderText(
            text or self._default_placeholder
        )

    def reset_listening_status(self) -> None:
        self._input_area.input_bar.input.setPlaceholderText(self._default_placeholder)

    def set_mic_level(self, level: float) -> None:
        self._input_area.waveform.set_level(level)

    def _emit_send(self) -> None:
        text = self._input_area.input_bar.input.text().strip()
        if not text:
            return
        self._input_area.input_bar.input.clear()
        self._sync_send_enabled()
        self.chat_send.emit(text)

    def append_user(self, text: str) -> None:
        self._log.append_user(text)

    def append_iris_chunk(self, text: str) -> None:
        self._log.append_iris_chunk(text)

    def end_iris(self, final_text: str | None = None) -> None:
        self._log.end_iris(final_text)

    def append_iris_tool(self, text: str) -> None:
        self._log.append_iris_tool(text)

    def append_iris_error(self, text: str) -> None:
        self._log.append_iris_error(text)

    def set_orb_state(self, state_name: str) -> None:
        self.orb.set_state(state_name)

    def mount_live_activity(self, live: QWidget, *, height: int = 96) -> None:
        """IDE Companion과 같은 위치(오브 아래)에 Live Activity 마운트."""
        h = max(72, min(140, int(height)))
        live.setMinimumHeight(h)
        live.setMaximumHeight(h)
        live.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._activity_host.setMinimumHeight(h)
        self._activity_host.setMaximumHeight(h)
        self._activity_host.show()
        # addWidget이 이전 부모에서 원자적으로 옮김 (orphan 창 금지)
        self._activity_lay.addWidget(live)
        self._live_mounted = live
        live.show()

    def has_live_activity(self) -> bool:
        return self._live_mounted is not None

    def clear_live_slot(self) -> None:
        """슬롯만 비움 — 위젯 reparent는 호출측 addWidget이 담당."""
        self._live_mounted = None
        self._activity_host.setMinimumHeight(0)
        self._activity_host.setMaximumHeight(0)
        self._activity_host.hide()


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    log = WorkspaceIrisChatLog("WorkspaceIrisChatLog")
    log.append_user("첫 줄\n둘째 줄")
    log.append_iris_chunk("**굵게**와\n줄바꿈")
    log.end_iris()
    assert "br" in log.toHtml().lower() or "\n" in log.toPlainText()
    assert "You" in log.toPlainText() and "Iris" in log.toPlainText()
    panel = WorkspaceIrisPanel(name_prefix="Email", placeholder="test")
    assert panel.objectName() == "EmailIrisPanel"
    assert panel._input_area.objectName() == "ChatInputArea"
    assert not panel._input_area.input_bar._model_shell.isVisible()
    print("workspace_iris_chat ok")
