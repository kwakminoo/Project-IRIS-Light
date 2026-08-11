"""워크스페이스(이메일·캘린더 등) Iris 채팅 — 기본 ChatPanel과 동일 마크다운/줄바꿈."""

from __future__ import annotations

import html

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMouseEvent, QTextCursor
from PyQt6.QtWidgets import QTextEdit

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


class WorkspaceIrisChatLog(QTextEdit):
    """우측 Iris 패널 로그 — 사용자 줄바꿈 + Iris 마크다운(스트리밍 후 확정)."""

    def __init__(self, object_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setReadOnly(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(
            f"QTextEdit#{object_name} {{ background: transparent; border: none; color: #e2e8f0; }}"
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
        body = normalize_chat_body("나", prepare_chat_text(text))
        if not body:
            return
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(
            f"<p><b style='color:#93c5fd'>나</b>: {chat_body_to_html(body)}</p>"
        )
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
            cursor.insertHtml("<p><b style='color:#5eead4'>아이리스</b>: </p>")
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
                cursor.insertHtml("<p><b style='color:#5eead4'>아이리스</b>: </p>")
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


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    log = WorkspaceIrisChatLog("WorkspaceIrisChatLog")
    log.append_user("첫 줄\n둘째 줄")
    log.append_iris_chunk("**굵게**와\n줄바꿈")
    log.end_iris()
    assert "br" in log.toHtml().lower() or "\n" in log.toPlainText()
    print("workspace_iris_chat ok")
