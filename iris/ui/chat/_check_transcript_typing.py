"""H1 typing reveal: append_message_typed grows TextPart char-by-char (ChatLog parity)."""

from __future__ import annotations

import json
import sys

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.core.message_parts import TextPart
from iris.ui.chat.chat_panel import ChatPanel

_LONG = (
    "Typing reveal must grow on the H1 transcript surface one chunk at a time "
    "so the finished turn feels like the old ChatLog character paint path."
)

_PROBE_JS = r"""
(function() {
  var turn = document.querySelector('#transcript .turn.assistant')
    || document.querySelector('#transcript .turn');
  var text = turn ? (turn.innerText || turn.textContent || '') : '';
  return JSON.stringify({
    turnCount: document.querySelectorAll('#transcript .turn').length,
    text: (text || '').replace(/\s+/g, ' ').trim(),
    len: (text || '').replace(/\s+/g, ' ').trim().length
  });
})()
"""


def _run_js(view, script: str, timeout_ms: int = 10000):
    box: dict = {"raw": None, "done": False}
    loop = QEventLoop()

    def _cb(raw) -> None:
        box["raw"] = raw
        box["done"] = True
        loop.quit()

    view.page().runJavaScript(script, _cb)
    QTimer.singleShot(timeout_ms, loop.quit)
    if not box["done"]:
        loop.exec()
    return box["raw"]


def _wait_h1_ready(host, *, rounds: int = 80) -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(rounds):
        app.processEvents()
        if host._view is not None and getattr(host, "_page_ready", False):
            return
        loop = QEventLoop()
        QTimer.singleShot(50, loop.quit)
        loop.exec()
    assert host._view is not None and getattr(host, "_page_ready", False), "H1 not ready"


def _settle(ms: int = 80) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _probe(host) -> dict:
    view = host.view()
    assert view is not None
    raw = _run_js(view, _PROBE_JS)
    assert raw is not None, "probe returned None"
    data = json.loads(raw) if isinstance(raw, str) else raw
    assert isinstance(data, dict), data
    return data


def _text_parts_md(host, msg_id: str) -> str:
    parts = host.parts_for_message(msg_id)
    return "".join(
        p.markdown for p in parts if isinstance(p, TextPart)
    )


def main() -> int:
    panel = ChatPanel()
    panel.resize(640, 480)
    panel.show()
    host = panel.transcript()
    assert panel._log.isHidden()

    # Force slow plain typing so a few ticks stay partial.
    from iris.ui.chat.typography import manager

    manager.get().typing_chars_per_sec = 20

    panel.append_message_typed("Iris", _LONG, speech_sync=False)
    panel._typing_timer.stop()  # manual ticks only — avoid race with QTimer
    mid = panel._pending_iris_msg_id
    assert mid, "typed turn must keep pending msg_id while revealing"
    assert panel.is_typing_active(), "plain typed turn must keep typing state"
    _wait_h1_ready(host)

    lengths: list[int] = []
    md_lens: list[int] = []
    for _ in range(8):
        panel._type_next_chunk()
        _settle(40)
        probe = _probe(host)
        lengths.append(int(probe.get("len") or 0))
        md_lens.append(len(_text_parts_md(host, mid)))

    assert any(a < b for a, b in zip(lengths, lengths[1:])), (
        f"H1 DOM text must grow between ticks: {lengths}"
    )
    assert any(a < b for a, b in zip(md_lens, md_lens[1:])), (
        f"TextPart markdown must grow between ticks: {md_lens}"
    )
    assert lengths[0] < len(_LONG.replace("  ", " ").strip()), (
        f"first ticks must be partial, got {lengths[0]}"
    )

    panel.finish_typing()
    _settle(120)
    final = _probe(host)
    final_text = str(final.get("text") or "")
    for token in ("Typing reveal", "ChatLog", "character paint"):
        assert token in final_text, f"missing {token!r} in {final_text!r}"
    assert not panel.is_typing_active()
    assert panel._pending_iris_msg_id == ""

    # speech_sync: land empty/short until sync_typing_to_speech
    panel.append_message_typed("Iris", "Speech sync typing body here", speech_sync=True)
    panel._typing_timer.stop()
    mid2 = panel._pending_iris_msg_id
    assert mid2
    assert panel.is_typing_active()
    _settle(100)
    early = _text_parts_md(host, mid2)
    assert len(early.strip()) < len("Speech sync typing body here"), (
        f"speech_sync must not dump full body before TTS sync: {early!r}"
    )
    panel.sync_typing_to_speech(800.0)
    panel._typing_timer.stop()
    before = len(_text_parts_md(host, mid2).strip())
    for _ in range(6):
        panel._type_next_chunk()
        _settle(40)
    after = len(_text_parts_md(host, mid2).strip())
    assert after > before, f"speech_sync ticks must grow reveal: {before} -> {after}"
    panel.finish_typing()
    _settle(80)
    done = _text_parts_md(host, mid2)
    assert "Speech sync typing body here" in done, done

    print("transcript_typing ok", json.dumps({"plain_lens": lengths, "md_lens": md_lens}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
