"""H1 must not blank the page on every land — setHtml only for first paint.

Symptom: transparent WebEngine + full setHtml flashes Iris chrome behind the
chat, so the UI looks like it is switching between chat and the app.
"""

from __future__ import annotations

import json
import sys

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from iris.core.message_parts import TextPart
from iris.ui.chat.transcript_h1 import H1TranscriptHost
from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

_PROBE_JS = r"""
(function() {
  var t = document.getElementById('transcript');
  return JSON.stringify({
    turnCount: document.querySelectorAll('#transcript .turn').length,
    hasTranscript: !!t,
    textLen: t ? (t.textContent || '').length : 0
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
    assert loaded["done"] and loaded["ok"], "loadFinished failed"


def _settle(ms: int = 200) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main() -> int:
    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)

    host = H1TranscriptHost()
    host.resize(480, 640)
    view = host.view()
    assert view is not None

    set_html_calls = {"n": 0}
    original = view.setHtml

    def _counting_set_html(*args, **kwargs):
        set_html_calls["n"] += 1
        return original(*args, **kwargs)

    view.setHtml = _counting_set_html  # type: ignore[method-assign]

    host.append_turn("user", [TextPart(markdown="first")], msg_id="m1")
    _wait_load(view)
    _settle(150)
    first_loads = set_html_calls["n"]
    assert first_loads >= 1, "first land must paint via setHtml"

    raw1 = _run_js(view, _PROBE_JS)
    probe1 = json.loads(raw1) if isinstance(raw1, str) else raw1
    assert int(probe1.get("turnCount") or 0) == 1, f"first turn missing: {probe1}"

    # Second land must patch DOM — another full setHtml blanks transparent page.
    host.append_turn("assistant", [TextPart(markdown="second reply")], msg_id="m2")
    _settle(250)
    raw2 = _run_js(view, _PROBE_JS)
    probe2 = json.loads(raw2) if isinstance(raw2, str) else raw2
    assert int(probe2.get("turnCount") or 0) == 2, f"second turn missing: {probe2}"
    assert set_html_calls["n"] == first_loads, (
        f"extra setHtml after first paint causes blank flash: "
        f"first={first_loads} now={set_html_calls['n']} probe={probe2}"
    )

    # Stream end path: begin + land replacement must also avoid a second navigation.
    before_stream = set_html_calls["n"]
    host.begin_part_stream(role="assistant", msg_id="m3")
    _settle(200)
    # begin_part_stream may need one paint only if page was never loaded; here page exists.
    assert set_html_calls["n"] == before_stream, (
        f"begin_part_stream navigated setHtml on live page: "
        f"before={before_stream} now={set_html_calls['n']}"
    )

    print(
        "transcript_no_blank_flash ok",
        json.dumps(
            {"setHtml": set_html_calls["n"], "probe": probe2},
            ensure_ascii=False,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
