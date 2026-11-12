"""ChatActivityMap 전이 + 행 set_activity 타이머 자검."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QFrame

from iris.storage.conversations import ChatConversation
from iris.ui.monitor.chat_activity import ChatActivity, ChatActivityMap
from iris.ui.monitor.chat_history_panel import ChatHistoryPanel


def _check_map() -> None:
    m = ChatActivityMap()
    assert m.get(1) is ChatActivity.IDLE
    assert m.snapshot() == {}

    m.mark_working(1)
    assert m.get(1) is ChatActivity.WORKING
    assert dict(m.snapshot()) == {1: ChatActivity.WORKING}

    m.mark_finished(1, viewing=True)
    assert m.get(1) is ChatActivity.IDLE
    assert m.snapshot() == {}

    m.mark_working(2)
    m.mark_finished(2, viewing=False)
    assert m.get(2) is ChatActivity.DONE

    m.clear_done(2)
    assert m.get(2) is ChatActivity.IDLE

    m.mark_working(3)
    m.clear_done(3)
    assert m.get(3) is ChatActivity.WORKING

    m.mark_finished(3, viewing=False)
    m.mark_working(3)
    assert m.get(3) is ChatActivity.WORKING

    m.mark_finished(99, viewing=False)
    assert m.get(99) is ChatActivity.IDLE

    m.mark_working(4)
    m.mark_failed(4, viewing=False)
    assert m.get(4) is ChatActivity.FAILED
    m.clear_done(4)
    assert m.get(4) is ChatActivity.IDLE


def _check_row_timer(app: QApplication) -> None:
    panel = ChatHistoryPanel()
    panel.set_conversations(
        [ChatConversation(7, "작업 중", "", "", 1)],
        active_id=7,
    )
    app.processEvents()
    row = next(
        f for f in panel._inner.findChildren(QFrame) if f.objectName() == "HudChatRow"
    )
    assert row._activity is ChatActivity.IDLE
    assert not row._anim_timer.isActive()

    panel.set_activity({7: ChatActivity.WORKING})
    app.processEvents()
    assert row._activity is ChatActivity.WORKING
    assert row._anim_timer.isActive()
    assert row._badge is not None and not row._badge.isHidden()

    panel.set_activity({7: ChatActivity.DONE})
    app.processEvents()
    assert row._activity is ChatActivity.DONE
    assert not row._anim_timer.isActive()
    assert row._badge is not None and not row._badge.isHidden()

    panel.set_activity({7: ChatActivity.FAILED})
    app.processEvents()
    assert row._activity is ChatActivity.FAILED
    assert not row._anim_timer.isActive()

    panel.set_activity({})
    app.processEvents()
    assert row._activity is ChatActivity.IDLE
    assert not row._anim_timer.isActive()
    assert row._badge is not None and row._badge.isHidden()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    _check_map()
    _check_row_timer(app)
    print("chat activity OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
