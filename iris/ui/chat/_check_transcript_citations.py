"""H1 assistant TextPart / stream close keep citation chips (ChatLog parity)."""

from __future__ import annotations

import json
import sys

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.core.message_parts import TextPart
from iris.core.part_stream import PartStreamBuffer
from iris.ui.chat.chat_panel import ChatPanel

# Same shape as iris.core.chat_citations / _check_chat_blocks iris citations sample.
_CITE_MD = (
    "See [Docs](https://docs.example.com/a) and https://bare.example.com/x"
)

_PROBE_JS = """
(function() {
  function turnHtml(role) {
    var el = document.querySelector('.turn[data-role="' + role + '"]');
    return el ? (el.innerHTML || '') : '';
  }
  function hasCite(html) {
    html = String(html || '');
    var hasHref = html.indexOf('href=') >= 0;
    var hasSources = html.indexOf('SOURCES') >= 0;
    var hasBracket = /\\[[0-9]+\\]/.test(html);
    return {
      hasHref: hasHref,
      hasSources: hasSources,
      hasBracket: hasBracket,
      ok: hasHref && (hasSources || hasBracket)
    };
  }
  var asst = turnHtml('assistant');
  var user = turnHtml('user');
  return JSON.stringify({
    asst: hasCite(asst),
    user: hasCite(user),
    asstHasSources: asst.indexOf('SOURCES') >= 0,
    userHasSources: user.indexOf('SOURCES') >= 0,
    asstLen: asst.length,
    userLen: user.length
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
    assert loaded["done"] and loaded["ok"], "citation host loadFinished failed"


def _settle(ms: int = 250) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _probe(view) -> dict:
    raw = _run_js(view, _PROBE_JS)
    assert raw is not None, "citation probe returned None"
    probe = json.loads(raw) if isinstance(raw, str) else raw
    assert isinstance(probe, dict), f"bad probe: {probe!r}"
    return probe


def _check_landed_turns() -> None:
    panel = ChatPanel()
    panel.resize(640, 720)
    host = panel.transcript()
    view = host.view()
    assert view is not None

    host.append_turn("user", [TextPart(markdown=_CITE_MD)], msg_id="cite-user")
    host.append_turn(
        "assistant",
        [TextPart(markdown=_CITE_MD)],
        msg_id="cite-asst",
    )
    _wait_load(view)
    _settle(200)

    probe = _probe(view)
    asst = probe.get("asst") or {}
    assert asst.get("ok"), f"assistant must show citation chips: {probe}"
    assert probe.get("asstHasSources"), f"assistant missing SOURCES: {probe}"
    # User keeps citations=False — no SOURCES footer / chip strip.
    assert not probe.get("userHasSources"), f"user must not get SOURCES: {probe}"
    print("transcript_citations land ok", json.dumps(probe, ensure_ascii=False))


def _check_stream_close() -> None:
    panel = ChatPanel()
    panel.resize(640, 720)
    host = panel.transcript()
    view = host.view()
    assert view is not None

    host.begin_part_stream(role="assistant", msg_id="cite-stream")
    _wait_load(view)
    _settle(150)

    buf = PartStreamBuffer()
    host.apply_part_events(buf.push(_CITE_MD))
    host.apply_part_events(buf.finish())
    _settle(300)

    probe = _probe(view)
    asst = probe.get("asst") or {}
    assert asst.get("ok"), f"stream close must keep citation chips: {probe}"
    assert probe.get("asstHasSources"), f"stream close missing SOURCES: {probe}"
    print("transcript_citations stream ok", json.dumps(probe, ensure_ascii=False))


def main() -> int:
    _ = QApplication.instance() or _APP
    _check_landed_turns()
    _check_stream_close()
    print("transcript_citations ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
