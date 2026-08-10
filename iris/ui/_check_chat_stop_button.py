"""전송↔정지 버튼 토글 자검."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.composer_plus_menu import ComposerSendButton


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    panel = ChatPanel()
    panel.show()
    app.processEvents()

    btn = panel._input_area.input_bar.send_button
    assert isinstance(btn, ComposerSendButton)
    assert not btn.is_stop_mode()
    assert not panel.is_generating()

    stopped: list[int] = []
    panel.stop_clicked.connect(lambda: stopped.append(1))

    panel.set_generating(True)
    app.processEvents()
    assert panel.is_generating() and btn.is_stop_mode() and btn.isEnabled()
    assert btn.toolTip() == "중지"

    btn.click()
    app.processEvents()
    assert stopped == [1]

    panel.set_generating(False)
    app.processEvents()
    assert not btn.is_stop_mode() and btn.toolTip() == "전송"

    print("chat_stop_button ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
