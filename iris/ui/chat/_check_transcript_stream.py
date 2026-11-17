"""T6: H1 part stream — incomplete fence locks into one code card (no turn thrash)."""

from __future__ import annotations

import json
import sys

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from iris.core.part_stream import PartStreamBuffer
from iris.ui.chat.transcript_h1 import H1TranscriptHost
from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

_PROBE_JS = r"""
(function() {
  return JSON.stringify({
    turnCount: document.querySelectorAll('#transcript .turn').length,
    codeCards: document.querySelectorAll('.code-card').length,
    partNodes: document.querySelectorAll('[id^="part-"]').length,
    hasStreamApi: !!(window.__irisPartStream),
    streamingLeft: document.querySelectorAll('[data-streaming="1"]').length
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


def _wait_load(view, timeout_ms: int = 15000) -> None:
    loaded = {"ok": False, "done": False}
    loop = QEventLoop()

    def _on_finished(ok: bool) -> None:
        loaded["ok"] = bool(ok)
        loaded["done"] = True
        loop.quit()

    view.loadFinished.connect(_on_finished)
    QTimer.singleShot(timeout_ms, loop.quit)
    if not loaded["done"]:
        loop.exec()
    try:
        view.loadFinished.disconnect(_on_finished)
    except TypeError:
        pass
    assert loaded["done"] and loaded["ok"], "stream host loadFinished failed"


def _settle(ms: int = 250) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _flush_js(view) -> None:
    raw = _run_js(view, "1+1")
    assert raw == 2 or raw == "2" or raw == 2.0, f"js flush failed: {raw!r}"


def main() -> int:
    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)

    host = H1TranscriptHost()
    host.resize(640, 720)
    view = host.view()
    assert view is not None

    host.begin_part_stream(role="assistant", msg_id="t6-stream")
    _wait_load(view)
    _settle(200)

    buf = PartStreamBuffer()
    chunks = [
        "Before fence\n",
        "```python\n",
        "def hello():\n",
        "    return 42\n",
        # incomplete — no closing fence
    ]
    for chunk in chunks:
        host.apply_part_events(buf.push(chunk))
    host.apply_part_events(buf.finish())
    _flush_js(view)
    _settle(300)

    raw = _run_js(view, _PROBE_JS)
    assert raw is not None, "probe returned None"
    probe = json.loads(raw) if isinstance(raw, str) else raw
    assert isinstance(probe, dict), f"bad probe: {probe!r}"
    assert int(probe.get("turnCount") or 0) == 1, f"turn thrash: {probe}"
    assert int(probe.get("codeCards") or 0) >= 1, f"missing code card: {probe}"
    assert probe.get("hasStreamApi"), f"missing stream JS api: {probe}"
    assert int(probe.get("streamingLeft") or 0) == 0, f"still streaming: {probe}"

    parts = host.parts_for_message("t6-stream")
    assert any(getattr(p, "type", "") == "code" for p in parts), f"parts: {parts!r}"

    print("transcript_stream probe ok", json.dumps(probe, ensure_ascii=False))
    print("transcript_stream ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
