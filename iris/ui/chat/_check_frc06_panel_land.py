"""FRC-06: ChatPanel public land/stream APIs paint H1 DOM, not ghost `_log`.

Migrates the highest-value observable from tests/test_chat_typography.py
(`test_stream_positions_and_links_survive`) and the land half of
tests/test_chat_scroll.py without QTextEdit `_log` wheel/fade probes.

Run: .venv\\Scripts\\python.exe -m iris.ui.chat._check_frc06_panel_land
"""

from __future__ import annotations

import json
import sys

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.typography import Typography, defaults, manager

_PROBE_JS = r"""
(function() {
  var turns = document.querySelectorAll('#transcript .turn');
  var withId = 0;
  for (var i = 0; i < turns.length; i++) {
    if ((turns[i].getAttribute('data-msg-id') || '').length > 0) withId++;
  }
  var t = document.getElementById('transcript');
  var body = document.body;
  var cs = body ? window.getComputedStyle(body) : null;
  return JSON.stringify({
    turnCount: turns.length,
    withMsgId: withId,
    text: t ? (t.textContent || '') : '',
    bodyFontPx: cs ? (parseFloat(cs.fontSize) || 0) : 0
  });
})()
"""


def _settle(ms: int = 200) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


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
    assert loaded["done"] and loaded["ok"], "H1 loadFinished failed"


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


def _probe(view) -> dict:
    raw = _run_js(view, _PROBE_JS)
    assert raw is not None, "DOM probe returned None"
    data = json.loads(raw) if isinstance(raw, str) else raw
    assert isinstance(data, dict), data
    return data


def _ghost_log_clean(panel: ChatPanel) -> None:
    assert not panel._log.isVisible(), "legacy `_log` must stay hidden"
    plain = panel._log.toPlainText().strip()
    assert plain == "", f"ghost `_log` must stay empty, got: {plain!r}"


def _drain_typing(panel: ChatPanel, *, ticks: int = 200) -> None:
    """Advance plain typing drip without relying on wall-clock QTimer alone."""
    panel._typing_timer.stop()
    for _ in range(ticks):
        if not (panel._typing_text and panel._typing_index < len(panel._typing_text or "")):
            if not panel._stream_active and panel._pending_stream_land is None:
                break
        panel._type_next_chunk()
        _settle(5)
    if panel._stream_active or panel._pending_stream_land is not None:
        panel.end_stream_message()
        _settle(50)
        panel._typing_timer.stop()
        for _ in range(ticks):
            if not panel._typing_text:
                break
            panel._type_next_chunk()
            _settle(5)
    panel.finish_typing()
    _settle(50)


def _check_panel_land_and_stream(app: QApplication) -> None:
    del app
    panel = ChatPanel()
    panel.resize(640, 480)
    panel.show()
    _settle(50)

    host = panel.transcript()
    view = host.view()
    assert view is not None

    panel.append_message_instant("Iris", "## Heading\n\n고정 턴 MARKER_LAND")
    _wait_load(view)
    _settle(200)
    first = _probe(view)
    assert int(first.get("turnCount") or 0) >= 1, first
    assert int(first.get("withMsgId") or 0) >= 1, (
        f"H1 turns must carry data-msg-id (replaces iris-msg-): {first}"
    )
    assert "MARKER_LAND" in str(first.get("text") or ""), first
    _ghost_log_clean(panel)

    panel.begin_stream_message("Iris", speech_sync=False)
    panel.append_stream_chunk("실시간 답변 ABC")
    panel.append_stream_chunk(" 추가 내용")
    _drain_typing(panel)
    _settle(250)

    second = _probe(view)
    blob = str(second.get("text") or "")
    assert "추가 내용" in blob or "실시간 답변" in blob, second
    assert int(second.get("turnCount") or 0) >= 2, second
    _ghost_log_clean(panel)

    print(
        "frc06_panel_land stream ok",
        {"turns": second.get("turnCount"), "withMsgId": second.get("withMsgId")},
    )
    panel.close()


def _check_new_land_picks_typography(app: QApplication) -> None:
    """New H1 paint reads live TOKENS; does not require QTextDocument fragment edits."""
    del app
    panel = ChatPanel()
    panel.resize(640, 480)
    panel.show()
    _settle(50)
    host = panel.transcript()
    view = host.view()
    assert view is not None

    base = defaults()
    large = Typography(
        base.chat_font_family,
        22,
        base.code_font_family,
        21,
        base.typing_chars_per_sec,
    )
    manager.apply(large)
    try:
        panel.append_message_instant("Iris", "TYPO_SIZE_PROBE")
        _wait_load(view)
        _settle(200)
        probe = _probe(view)
        px = float(probe.get("bodyFontPx") or 0)
        assert abs(px - 22.0) <= 1.5, f"new land must use applied chat_font_size: {probe}"
        assert "TYPO_SIZE_PROBE" in str(probe.get("text") or ""), probe
        _ghost_log_clean(panel)
        print("frc06_panel_land typography ok", {"bodyFontPx": px})
    finally:
        manager.apply(defaults())
        panel.close()


def main() -> int:
    app = QApplication.instance() or _APP
    _check_panel_land_and_stream(app)
    _check_new_land_picks_typography(app)
    print("frc06_panel_land ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
