"""H1 plain typing drip: PartStream text grows gradually via _type_next_chunk."""

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

_SAMPLE = "Hello typing drip on H1 surface."


def _settle(ms: int = 40) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _h1_stream_raw(panel: ChatPanel) -> str:
    buf = getattr(panel, "_part_stream_buf", None)
    if buf is None:
        return ""
    return str(getattr(buf, "_raw", "") or "")


def main() -> int:
    panel = ChatPanel()
    panel.resize(640, 480)
    panel.show()
    _settle(30)

    panel.begin_stream_message("Iris", speech_sync=False)
    panel.append_stream_chunk(_SAMPLE)

    assert _h1_stream_raw(panel) == "", (
        f"before ticks H1 must be empty, got {_h1_stream_raw(panel)!r}"
    )
    assert panel._typing_text == _SAMPLE

    lengths: list[int] = []
    for _ in range(8):
        panel._type_next_chunk()
        raw = _h1_stream_raw(panel)
        assert _SAMPLE.startswith(raw), f"H1 must stay a prefix, got {raw!r}"
        lengths.append(len(raw))

    assert lengths[-1] > lengths[0], (
        f"H1 stream length must grow across ticks, lengths={lengths}"
    )
    assert lengths[-1] < len(_SAMPLE) or (
        lengths[0] < lengths[-1] and any(a < b for a, b in zip(lengths, lengths[1:]))
    ), f"expected gradual growth, lengths={lengths}"
    assert any(a < b for a, b in zip(lengths, lengths[1:])), (
        f"prefix length must increase on some tick, lengths={lengths}"
    )
    # Pushes go through PartStreamBuffer (canonical parts path).
    assert panel._part_stream_buf is not None
    assert panel._part_stream_buf._raw == _h1_stream_raw(panel)

    print("h1_stream_typing_drip ok", lengths)

    panel2 = ChatPanel()
    panel2.resize(640, 480)
    panel2.show()
    _settle(30)

    _FINISH_ONLY = (
        "Finish-only Iris turn without content_chunk must drip on H1 "
        "before the final typed parts land."
    )
    panel2.append_message("Iris", _FINISH_ONLY)
    panel2._typing_timer.stop()

    assert panel2._pending_stream_land is not None, "finish-only must defer H1 land"
    assert _h1_stream_raw(panel2) == "", (
        f"finish-only must not instant-land on H1, got {_h1_stream_raw(panel2)!r}"
    )

    lengths2: list[int] = [len(_h1_stream_raw(panel2))]
    for _ in range(12):
        if not panel2.is_typing_active():
            break
        panel2._type_next_chunk()
        raw = _h1_stream_raw(panel2)
        assert _FINISH_ONLY.startswith(raw), f"H1 must stay a prefix, got {raw!r}"
        lengths2.append(len(raw))

    assert lengths2[0] == 0, (
        f"finish-only must start from empty H1 stream, lengths={lengths2}"
    )
    assert any(a < b for a, b in zip(lengths2, lengths2[1:])), (
        f"finish-only prefix must grow across ticks, lengths={lengths2}"
    )

    for _ in range(5000):
        if panel2._pending_stream_land is None and not panel2.is_typing_active():
            break
        panel2._type_next_chunk()

    assert panel2._pending_stream_land is None
    landed = "".join(
        getattr(p, "markdown", "")
        for t in panel2.transcript()._turns
        for p in t.parts
    )
    assert _FINISH_ONLY in landed, landed

    print("h1_typing_drip ok", lengths, lengths2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
