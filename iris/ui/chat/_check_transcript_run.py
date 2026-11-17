"""T7: Code Run → ExecutionPart + ImagePart land on the H1 transcript."""

from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from iris.core.message_parts import CodePart, ExecutionPart, ImagePart, TextPart
from iris.ui.chat.transcript_h1 import H1TranscriptHost
from iris.ui.chat.transcript_run import land_code_run_on_transcript
from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

_PRINT_SNIPPET = "print('iris-run-ok')\n"

_PLOT_SNIPPET = """
import matplotlib.pyplot as plt
import numpy as np
fig, ax = plt.subplots(figsize=(1, 1))
ax.imshow(np.array([[1]], dtype=int), cmap='gray', vmin=0, vmax=1)
ax.axis('off')
plt.tight_layout()
"""

_CLICK_RUN_JS = r"""
(function() {
  var card = document.querySelector('.code-card[data-runnable="1"]');
  if (!card) return JSON.stringify({ok: false, detail: 'no runnable card'});
  var btn = card.querySelector('.code-run');
  if (!btn) return JSON.stringify({ok: false, detail: 'no run button'});
  btn.click();
  return JSON.stringify({
    ok: true,
    ran: card.getAttribute('data-ran') === '1',
    queueLen: (window.__irisCodeRunRequests || []).length
  });
})()
"""

_PROBE_DOM_JS = r"""
(function() {
  var exec = document.querySelector('.exec-card[data-part="execution"]');
  var img = document.querySelector('.image-card img');
  var out = exec ? (exec.querySelector('.exec-out') || exec.querySelector('.exec-err')) : null;
  return JSON.stringify({
    hasExec: !!exec,
    execOk: exec ? exec.getAttribute('data-ok') : '',
    execText: out ? (out.textContent || '').trim().slice(0, 200) : '',
    hasImg: !!(img && (img.getAttribute('src') || '').indexOf('data:image') === 0),
    runnable: !!document.querySelector('.code-card[data-runnable="1"] .code-run')
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


def _arm_load(view) -> tuple[dict, object]:
    loaded = {"ok": False, "done": False}
    loop = QEventLoop()

    def _on_finished(ok: bool) -> None:
        loaded["ok"] = bool(ok)
        loaded["done"] = True
        loop.quit()

    view.loadFinished.connect(_on_finished)
    return loaded, loop


def _wait_armed(view, loaded: dict, loop: QEventLoop, timeout_ms: int = 15000) -> None:
    QTimer.singleShot(timeout_ms, loop.quit)
    if not loaded["done"]:
        loop.exec()
    try:
        view.loadFinished.disconnect()
    except TypeError:
        pass
    assert loaded["done"] and loaded["ok"], "setHtml loadFinished failed"
    settle = QEventLoop()
    QTimer.singleShot(250, settle.quit)
    settle.exec()


def _check_print_land(app: QApplication) -> None:
    _ = app
    host = H1TranscriptHost()
    host.resize(640, 720)
    view = host.view()
    assert view is not None

    msg_id = "run-print-1"
    loaded, loop = _arm_load(view)
    host.append_turn(
        "assistant",
        [
            TextPart(markdown="Run print"),
            CodePart(language="python", source=_PRINT_SNIPPET, filename="print.py"),
        ],
        msg_id=msg_id,
    )
    _wait_armed(view, loaded, loop)

    click = _run_js(view, _CLICK_RUN_JS)
    assert click is not None, "Run click JS returned None"
    probe = json.loads(click) if isinstance(click, str) else click
    assert isinstance(probe, dict) and probe.get("ok"), f"run click: {probe}"
    assert int(probe.get("queueLen") or 0) >= 1, f"queue empty: {probe}"

    loaded2, loop2 = _arm_load(view)
    landed = host.take_code_run_requests()
    assert landed, "no landed run results"
    assert landed[0].get("ok") is True, landed[0]
    parts = host.parts_for_message(msg_id)
    assert any(isinstance(p, ExecutionPart) and p.ok for p in parts), parts
    assert any(
        isinstance(p, ExecutionPart) and "iris-run-ok" in (p.stdout or "") for p in parts
    ), parts
    _wait_armed(view, loaded2, loop2)

    dom_raw = _run_js(view, _PROBE_DOM_JS)
    assert dom_raw is not None
    dom = json.loads(dom_raw) if isinstance(dom_raw, str) else dom_raw
    assert dom.get("hasExec"), f"DOM missing execution: {dom}"
    assert "iris-run-ok" in (dom.get("execText") or ""), dom
    assert dom.get("runnable"), dom
    print("transcript_run print land ok")


def _check_plot_land(app: QApplication) -> None:
    _ = app
    host = H1TranscriptHost()
    host.resize(640, 720)
    view = host.view()
    assert view is not None

    msg_id = "run-plot-1"
    loaded, loop = _arm_load(view)
    host.append_turn(
        "assistant",
        [CodePart(language="python", source=_PLOT_SNIPPET, filename="plot.py")],
        msg_id=msg_id,
    )
    _wait_armed(view, loaded, loop)

    loaded2, loop2 = _arm_load(view)
    result = land_code_run_on_transcript(
        host, _PLOT_SNIPPET, language="python", msg_id=msg_id
    )
    assert result.get("ok") is True, result
    assert result.get("png_paths"), result
    parts = host.parts_for_message(msg_id)
    assert any(isinstance(p, ExecutionPart) for p in parts), parts
    assert any(isinstance(p, ImagePart) and p.path for p in parts), parts
    _wait_armed(view, loaded2, loop2)

    dom_raw = _run_js(view, _PROBE_DOM_JS)
    assert dom_raw is not None
    dom = json.loads(dom_raw) if isinstance(dom_raw, str) else dom_raw
    assert dom.get("hasExec"), f"DOM missing execution: {dom}"
    assert dom.get("hasImg"), f"DOM missing plot image: {dom}"
    print("transcript_run plot land ok")


def main() -> int:
    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)
    _check_print_land(app)
    _check_plot_land(app)
    print("transcript_run ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
