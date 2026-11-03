"""메일/캘린더/위키 오른쪽 칸이 IDE IdeUnifiedShell 8:2 + 채팅 호스트를 쓰는지 자검."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.workspaces.calendar_workspace_page import CalendarWorkspacePage
from iris.ui.workspaces.email_workspace_page import EmailWorkspacePage
from iris.ui.workspaces.ide_companion_page import (
    CHAT_LIST_WIDTH,
    COMPANION_CONTENT_RATIO,
    IdeCompanionPage,
    IdeUnifiedShell,
)
from iris.ui.workspaces.obsidian_workspace_page import ObsidianWorkspacePage


def _assert_ratio_8020(page: QWidget, *, label: str) -> None:
    page.resize(1000, 800)
    page.show()
    QApplication.instance().processEvents()
    shell = page._companion_shell
    assert isinstance(shell, IdeUnifiedShell), label
    sizes = page._splitter.sizes()
    total = sum(sizes)
    assert total > 0, (label, sizes)
    assert abs(sizes[0] / total - COMPANION_CONTENT_RATIO) < 0.02, (label, sizes)
    assert page._chat_host is shell.iris_host()


def main() -> None:
    app = QApplication([])
    email = EmailWorkspacePage()
    calendar = CalendarWorkspacePage()
    wiki = ObsidianWorkspacePage()
    assert not hasattr(email, "iris_panel")
    assert not hasattr(calendar, "iris_panel")

    _assert_ratio_8020(email, label="email")
    _assert_ratio_8020(calendar, label="calendar")
    _assert_ratio_8020(wiki, label="wiki")

    host = IdeCompanionPage()
    email.place_chat_host(host)
    assert host.parent() is email._chat_host
    closed = email._splitter.sizes()[1]

    host.set_width_delta_callback(email.shift_chat_column)
    host.set_chat_list_open(True)
    opened = email._splitter.sizes()[1]
    assert opened >= closed + CHAT_LIST_WIDTH - 8, (closed, opened)

    calendar.place_chat_host(host)
    assert host.parent() is calendar._chat_host
    assert calendar._chat_list_extra == CHAT_LIST_WIDTH
    assert host.chat_history.objectName() == "ChatHistoryPanel"

    wiki.place_chat_host(host)
    assert host.parent() is wiki._chat_host

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
