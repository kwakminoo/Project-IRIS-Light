"""Stream end must idle typing: H1 land clears sticky stop / scroll yank."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.composer_plus_menu import ComposerSendButton

_FINAL = (
    "Hermes PDF turn landed on H1 already. "
    "After end_stream_message, typing must be idle and stop must clear."
)


def _settle(ms: int = 40) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main() -> int:
    panel = ChatPanel()
    panel.resize(640, 480)
    panel.show()
    _settle(30)

    btn = panel._input_area.input_bar.send_button
    assert isinstance(btn, ComposerSendButton)

    panel.set_generating(True)
    panel.begin_stream_message("Iris", speech_sync=False)
    # Mid-stream chunks must not arm the plain typing timer (PartStream paints).
    panel.append_stream_chunk("Hermes PDF turn landed on H1 already. ")
    assert not panel._typing_timer.isActive(), (
        "append_stream_chunk must not start plain typing while PartStream is active"
    )
    panel.append_stream_chunk("After end_stream_message, typing must be idle and stop must clear.")
    assert not panel._typing_timer.isActive(), (
        "append_stream_chunk must not start plain typing while PartStream is active"
    )

    panel.end_stream_message(_FINAL)
    _settle(20)

    assert not panel.is_typing_active(), (
        f"after H1 land, typing must be inactive "
        f"(index={panel._typing_index} text_len={len(panel._typing_text)})"
    )
    assert not panel._typing_timer.isActive(), "typing timer must be stopped after stream end"
    assert panel._typing_text == "", f"typing buffer must be cleared, got {panel._typing_text!r}"

    scrolls: list[int] = []
    panel._scroll_log_to_bottom = lambda *a, **k: scrolls.append(1)  # type: ignore[method-assign]
    for _ in range(3):
        if not panel.is_typing_active():
            break
        panel._type_next_chunk()
    assert scrolls == [], (
        f"paint-no-op typing ticks must not scroll after stream end, got {len(scrolls)} scrolls"
    )

    panel.set_generating(False)
    panel.set_presenting(panel.is_typing_active())
    _settle(20)
    assert not panel.is_presenting(), "presenting must clear when typing idle"
    assert not btn.is_stop_mode(), "send button must leave stop mode after idle land"

    print("stream_end_idle ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
