"""모델 정리 상태줄 ActivityRing + 채팅 배지 공유 위젯 자검."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QFrame, QLabel

from iris.config.settings import Settings
from iris.storage.conversations import ChatConversation
from iris.ui.ai_hub.providers_panel import AiProvidersPanel
from iris.ui.monitor.chat_activity import ChatActivity
from iris.ui.monitor.chat_history_panel import ChatHistoryPanel
from iris.ui.widgets.activity_ring import ActivityKind, ActivityRing


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    panel = AiProvidersPanel(db=None, settings=Settings())
    app.processEvents()
    ring = panel._api_status_ring
    assert isinstance(ring, ActivityRing)
    assert isinstance(panel._api_status, QLabel)
    assert ring.isHidden()
    assert ring.kind() is ActivityKind.IDLE
    assert not ring._anim_timer.isActive()

    ring.set_working(True)
    app.processEvents()
    assert not ring.isHidden()
    assert ring.kind() is ActivityKind.WORKING
    assert ring._anim_timer.isActive()

    ring.set_working(False)
    app.processEvents()
    assert ring.isHidden()
    assert ring.kind() is ActivityKind.IDLE
    assert not ring._anim_timer.isActive()

    panel._set_verify_ring_working(True)
    app.processEvents()
    assert panel._api_status_ring.kind() is ActivityKind.WORKING
    panel._set_verify_ring_working(False)
    app.processEvents()
    assert panel._api_status_ring.kind() is ActivityKind.IDLE

    history = ChatHistoryPanel()
    history.set_conversations(
        [ChatConversation(7, "작업 중", "", "", 1)],
        active_id=7,
    )
    app.processEvents()
    row = next(
        f for f in history._inner.findChildren(QFrame) if f.objectName() == "HudChatRow"
    )
    assert isinstance(row._badge, ActivityRing)
    history.set_activity({7: ChatActivity.WORKING})
    app.processEvents()
    assert row._badge.kind() is ActivityKind.WORKING
    assert row._badge._anim_timer.isActive()

    print("providers_status_ring OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
