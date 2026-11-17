"""T9: matrix / diagram absorb into H1 typed parts; primary surface is H1."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from iris.core.message_parts import DiagramPart, TextPart
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

_MATRIX_MD = """# Matrix absorb

```matrix
# step1
0 1 0
1 1 1
0 1 0
```
"""

_PROBE_JS = """
(function() {
  var matrix = document.querySelector('table[data-iris-matrix="1"]');
  var cells = document.querySelectorAll('[data-iris-matrix-cell]');
  var diagram = document.querySelector('.diagram-card[data-part="diagram"]');
  var link = diagram ? diagram.querySelector('a.diagram-open') : null;
  var h1Visible = true;
  return JSON.stringify({
    hasMatrix: !!matrix,
    cellCount: cells ? cells.length : 0,
    hasDiagram: !!diagram,
    diagramPath: diagram ? (diagram.getAttribute('data-diagram-path') || '') : '',
    diagramKind: diagram ? (diagram.getAttribute('data-diagram-kind') || '') : '',
    hasOpenLink: !!(link && (link.getAttribute('href') || '').indexOf('iris-diagram://') === 0),
    turnCount: document.querySelectorAll('.turn').length
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


def _wait_load(view, timeout_ms: int = 12000) -> None:
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
    assert loaded["done"] and loaded["ok"], "H1 loadFinished failed"
    _settle()


def _settle(ms: int = 250) -> None:
    """Later lands patch #transcript via JS — no second setHtml/loadFinished."""
    settle = QEventLoop()
    QTimer.singleShot(ms, settle.quit)
    settle.exec()


def main() -> int:
    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)
    _ = app

    panel = ChatPanel()
    panel.resize(640, 720)
    host = panel.transcript()
    assert host is panel._transcript_h1
    assert panel._log.isHidden()
    assert panel.layout().indexOf(panel._transcript_h1) >= 0
    assert panel.layout().indexOf(panel._log) < 0

    view = host.view()
    host.append_turn("assistant", [TextPart(markdown=_MATRIX_MD)], msg_id="absorb-matrix")
    _wait_load(view)

    with tempfile.TemporaryDirectory() as tmp:
        html = Path(tmp) / "diagram.html"
        html.write_text(
            "<!DOCTYPE html><html><body><svg></svg></body></html>",
            encoding="utf-8",
        )
        host.append_turn(
            "assistant",
            [
                DiagramPart(
                    path=str(html),
                    kind="workflow",
                    title="Absorb Flow",
                )
            ],
            msg_id="absorb-diagram",
        )
        _settle()

        raw = _run_js(view, _PROBE_JS)
        assert raw is not None, "probe None"
        probe = json.loads(raw) if isinstance(raw, str) else raw
        assert isinstance(probe, dict), probe
        assert probe.get("hasMatrix"), f"matrix missing: {probe}"
        assert int(probe.get("cellCount") or 0) >= 9, f"matrix cells: {probe}"
        assert probe.get("hasDiagram"), f"diagram missing: {probe}"
        assert probe.get("diagramKind") == "workflow", probe
        assert str(html) in str(probe.get("diagramPath") or ""), probe
        assert probe.get("hasOpenLink"), probe
        assert int(probe.get("turnCount") or 0) >= 2, probe

        # Instant user land → TextPart on H1
        panel.append_message_instant("You", "hello absorb")
        _settle()
        turns = host._turns
        assert turns and turns[-1].role == "user"
        assert any(isinstance(p, TextPart) and "hello absorb" in p.markdown for p in turns[-1].parts)

    print("transcript_absorb ok", json.dumps(probe, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
