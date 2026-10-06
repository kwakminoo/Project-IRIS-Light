"""메일/캘린더 오른쪽 칸이 IDE 채팅 호스트를 받는지 자검."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.workspaces.calendar_workspace_page import CalendarWorkspacePage
from iris.ui.workspaces.email_workspace_page import EmailWorkspacePage
from iris.ui.workspaces.ide_companion_page import CHAT_LIST_WIDTH, IdeCompanionPage


def main() -> None:
    app = QApplication([])
    email = EmailWorkspacePage()
    calendar = CalendarWorkspacePage()
    assert not hasattr(email, "iris_panel")
    assert not hasattr(calendar, "iris_panel")

    host = IdeCompanionPage()
    email.resize(1200, 800)
    email.show()
    app.processEvents()
    email.place_chat_host(host)
    assert host.parent() is email._chat_host
    closed = email._splitter.sizes()[1]

    host.set_width_delta_callback(email.shift_chat_column)
    host.set_chat_list_open(True)
    opened = email._splitter.sizes()[1]
    assert opened >= closed + CHAT_LIST_WIDTH - 8, (closed, opened)

    calendar.resize(1200, 800)
    calendar.show()
    app.processEvents()
    calendar.place_chat_host(host)
    assert host.parent() is calendar._chat_host
    assert calendar._chat_list_extra == CHAT_LIST_WIDTH
    assert host.chat_history.objectName() == "ChatHistoryPanel"

    orb = QWidget()
    activity = QWidget()
    chat = ChatPanel()
    fresh = IdeCompanionPage()
    fresh.mount(
        orb_spacer=orb,
        live_activity=activity,
        chat=chat,
        activity_height=96,
    )
    assert fresh.is_mounted()
    back = QWidget()
    lay = QVBoxLayout(back)
    fresh.transfer_to(lay, (2, 0, 3))
    assert not fresh.is_mounted()
    assert lay.indexOf(chat) >= 0
    assert chat.objectName() == "ChatPanel"
    print("workspace chat host ok")


if __name__ == "__main__":
    main()
