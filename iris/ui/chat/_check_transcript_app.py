"""T5: H1 AppPart inline — complete-HTML gate + calculator iframe in turn."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from iris.core.message_parts import AppPart, TextPart, parse_part
from iris.ui.chat.transcript_app import (
    IncompleteAppHtmlError,
    require_complete_app_html,
)
from iris.ui.chat.transcript_h1 import H1TranscriptHost
from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

_REPO = Path(__file__).resolve().parents[3]
_SAMPLE = (
    _REPO
    / "docs"
    / "code-review"
    / "scratch-b0-gpt-transcript"
    / "shared"
    / "sample_turn.json"
)

_CLICK_CALC_JS = r"""
(function() {
  var card = document.querySelector('.app-card[data-part="app"]');
  if (!card) return JSON.stringify({ok: false, detail: 'no app card'});
  var frame = card.querySelector('iframe.app-frame');
  if (!frame) return JSON.stringify({ok: false, detail: 'no iframe'});
  var doc = null;
  try { doc = frame.contentDocument; } catch (e) {
    return JSON.stringify({ok: false, detail: 'iframe access: ' + String(e)});
  }
  if (!doc || !doc.body) {
    return JSON.stringify({ok: false, detail: 'iframe empty'});
  }
  var a = doc.getElementById('a');
  var b = doc.getElementById('b');
  var go = doc.getElementById('go');
  var out = doc.getElementById('out');
  if (!(a && b && go && out)) {
    return JSON.stringify({ok: false, detail: 'missing calc controls'});
  }
  a.value = '40';
  b.value = '59';
  go.click();
  return JSON.stringify({
    ok: true,
    mode: card.getAttribute('data-display-mode') || '',
    modeClass: /app-mode-inline/.test(card.className),
    outText: (out.textContent || '').trim()
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


def _wait_load(view, timeout_ms: int = 8000) -> None:
    loop = QEventLoop()
    done = {"ok": False}

    def _finished(ok: bool) -> None:
        done["ok"] = bool(ok)
        loop.quit()

    view.loadFinished.connect(_finished)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    try:
        view.loadFinished.disconnect(_finished)
    except TypeError:
        pass


def _sample_app_part() -> AppPart:
    data = json.loads(_SAMPLE.read_text(encoding="utf-8"))
    for raw in data.get("parts") or []:
        if isinstance(raw, dict) and raw.get("type") == "app":
            part = parse_part(raw)
            assert isinstance(part, AppPart)
            return part
    raise AssertionError("sample_turn.json missing app part")


def _check_gate() -> None:
    try:
        require_complete_app_html("")
        raise AssertionError("empty html should fail")
    except IncompleteAppHtmlError:
        pass
    try:
        require_complete_app_html("   \n\t  ")
        raise AssertionError("whitespace html should fail")
    except IncompleteAppHtmlError:
        pass
    try:
        require_complete_app_html("<div>fragment only</div>")
        raise AssertionError("fragment should fail")
    except IncompleteAppHtmlError:
        pass
    ok = require_complete_app_html(
        "<!DOCTYPE html><html><body><p>x</p></body></html>"
    )
    assert "<!DOCTYPE" in ok


def _check_inline_calc(app: QApplication) -> None:
    _ = app
    part = _sample_app_part()
    assert part.display_mode == "inline"
    host = H1TranscriptHost()
    host.resize(720, 640)
    host.show()
    host.append_turn(
        "assistant",
        [TextPart(markdown="계산기"), part],
        msg_id="t5-app",
    )
    view = host.view()
    assert view is not None
    _wait_load(view)
    # iframe srcdoc may need a beat after parent load
    settle = QEventLoop()
    QTimer.singleShot(400, settle.quit)
    settle.exec()

    raw = _run_js(view, _CLICK_CALC_JS)
    assert raw, "JS probe returned nothing"
    probe = json.loads(raw)
    assert probe.get("ok") is True, probe
    assert probe.get("mode") == "inline", probe
    assert probe.get("modeClass") is True, probe
    assert probe.get("outText") == "= 99", probe
    print("transcript_app calc ok", probe)


def main() -> int:
    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)
    _check_gate()
    _check_inline_calc(app)
    print("transcript_app ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
