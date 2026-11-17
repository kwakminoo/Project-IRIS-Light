"""T2: H1 WebEngine transcript host renders rich MD (not QTextEdit flat dump)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from iris.core.message_parts import TextPart
from iris.storage.conversations import ChatMessage
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.typography import TOKENS, manager
from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

_SAMPLE_MD = """# Transcript Typography

A paragraph with **bold** emphasis and enough line length to show spacing.

- first list item
- second list item

Closing paragraph after the list.
"""

_PROBE_JS = """
(function() {
  var body = document.body;
  var h1 = document.querySelector('#transcript h1, .md h1, h1');
  var ul = document.querySelector('#transcript ul, .md ul, ul');
  var li = document.querySelector('#transcript li, .md li, li');
  var strong = document.querySelector('#transcript strong, .md strong, strong');
  var cs = window.getComputedStyle(body);
  var padTop = parseFloat(cs.paddingTop) || 0;
  var padLeft = parseFloat(cs.paddingLeft) || 0;
  var lh = cs.lineHeight;
  var lhNum = parseFloat(lh);
  var fontSize = parseFloat(cs.fontSize) || 15;
  var lhRatio = (lh === 'normal') ? 1.2 : (lhNum / fontSize);
  return JSON.stringify({
    hasH1: !!h1,
    hasUl: !!ul,
    hasLi: !!li,
    hasStrong: !!strong,
    h1Text: h1 ? (h1.textContent || '').trim() : '',
    padTop: padTop,
    padLeft: padLeft,
    lineHeight: lh,
    lineHeightRatio: lhRatio,
    turnCount: document.querySelectorAll('.turn').length
  });
})()
"""

# Legacy ChatLog look: scrollbar, no user bubble, body 15px, You color.
_LEGACY_LOOK_JS = """
(function() {
  function sheetHasScrollbar() {
    var styles = document.querySelectorAll('style');
    for (var i = 0; i < styles.length; i++) {
      var txt = styles[i].textContent || '';
      if (txt.indexOf('::-webkit-scrollbar') >= 0) return true;
    }
    var sheets = document.styleSheets;
    for (var s = 0; s < sheets.length; s++) {
      try {
        var rules = sheets[s].cssRules || sheets[s].rules;
        for (var r = 0; r < rules.length; r++) {
          var sel = rules[r].selectorText || '';
          if (sel.indexOf('::-webkit-scrollbar') >= 0) return true;
        }
      } catch (e) {}
    }
    return false;
  }
  function isTransparentBg(bg) {
    if (!bg) return true;
    var v = String(bg).replace(/\\s+/g, '').toLowerCase();
    if (v === 'transparent' || v === 'rgba(0,0,0,0)' || v === 'rgba(0,0,0,0.0)') return true;
    var m = v.match(/^rgba?\\((\\d+),(\\d+),(\\d+)(?:,([0-9.]+))?\\)$/);
    if (m && m[4] !== undefined && parseFloat(m[4]) === 0) return true;
    return false;
  }
  var bodyCs = window.getComputedStyle(document.body);
  var htmlCs = window.getComputedStyle(document.documentElement);
  var userBody = document.querySelector('.turn[data-role="user"] .turn-body');
  var userCs = userBody ? window.getComputedStyle(userBody) : null;
  var userBg = userCs ? userCs.backgroundColor : '';
  var you = document.querySelector('.turn[data-role="user"] .speaker-you');
  var youColor = you ? window.getComputedStyle(you).color : '';
  var overflowY = bodyCs.overflowY || htmlCs.overflowY || '';
  return JSON.stringify({
    hasScrollbarCss: sheetHasScrollbar(),
    bodyFontPx: parseFloat(bodyCs.fontSize) || 0,
    bodyFontFamily: bodyCs.fontFamily || '',
    userBodyBg: userBg,
    userBodyTransparent: isTransparentBg(userBg),
    userMarginLeft: userCs ? (parseFloat(userCs.marginLeft) || 0) : -1,
    userMarginRight: userCs ? (parseFloat(userCs.marginRight) || 0) : -1,
    youColor: youColor,
    overflowY: overflowY,
    hasUserTurn: !!userBody,
    hasSpeakerYou: !!you
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

    def _on_timeout() -> None:
        loop.quit()

    view.page().runJavaScript(script, _cb)
    QTimer.singleShot(timeout_ms, _on_timeout)
    if not box["done"]:
        loop.exec()
    return box["raw"]


def _check_host_typography(app: QApplication) -> None:
    panel = ChatPanel()
    panel.resize(640, 720)
    host = panel.transcript()
    assert host is panel._transcript_h1
    assert host.widget() is host

    # Create the view before setHtml so loadFinished is not missed.
    view = host.view()
    assert view is not None

    loaded = {"ok": False, "done": False}
    loop = QEventLoop()

    def _on_finished(ok: bool) -> None:
        loaded["ok"] = bool(ok)
        loaded["done"] = True
        loop.quit()

    view.loadFinished.connect(_on_finished)
    host.append_turn(
        "assistant",
        [TextPart(markdown=_SAMPLE_MD)],
        msg_id="t2-sample",
    )
    QTimer.singleShot(15000, loop.quit)
    if not loaded["done"]:
        loop.exec()
    try:
        view.loadFinished.disconnect(_on_finished)
    except TypeError:
        pass
    assert loaded["done"] and loaded["ok"], "H1 setHtml loadFinished failed"

    settle = QEventLoop()
    QTimer.singleShot(200, settle.quit)
    settle.exec()

    raw = _run_js(view, _PROBE_JS)
    assert raw is not None, "runJavaScript returned None"
    if isinstance(raw, str):
        probe = json.loads(raw)
    else:
        probe = raw
    assert isinstance(probe, dict), f"bad probe: {probe!r}"
    assert probe.get("hasH1"), f"missing h1: {probe}"
    assert "Typography" in (probe.get("h1Text") or ""), f"h1 text: {probe}"
    assert probe.get("hasUl") and probe.get("hasLi"), f"missing list: {probe}"
    assert probe.get("hasStrong"), f"missing strong: {probe}"
    # Legacy ChatLog padding was 12px 16px; line-height token is 165%.
    assert float(probe.get("padTop") or 0) >= 12.0, f"body padding-top: {probe}"
    assert float(probe.get("padLeft") or 0) >= 12.0, f"body padding-left: {probe}"
    assert float(probe.get("lineHeightRatio") or 0) >= 1.45, f"line-height: {probe}"
    assert int(probe.get("turnCount") or 0) >= 1, f"turnCount: {probe}"

    # load_transcript_messages wire (history path) — patches DOM, no second setHtml.
    msg = ChatMessage(
        id=42,
        conversation_id=1,
        role="assistant",
        content=_SAMPLE_MD,
        created_at="2026-11-17T00:00:00",
        parts_json="",
    )
    panel.load_transcript_messages([msg])
    settle2 = QEventLoop()
    QTimer.singleShot(250, settle2.quit)
    settle2.exec()
    raw2 = _run_js(view, _PROBE_JS)
    probe2 = json.loads(raw2) if isinstance(raw2, str) else raw2
    assert probe2.get("hasH1") and probe2.get("turnCount") == 1, f"load wire: {probe2}"

    print("transcript_h1 probe ok", json.dumps(probe, ensure_ascii=False))


def _hex_to_rgb_css(hex_color: str) -> str:
    """'#7dd3fc' -> 'rgb(125, 211, 252)' for computed-style compare."""
    h = (hex_color or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgb({r}, {g}, {b})"


def _normalize_css_rgb(value: str) -> str:
    v = (value or "").replace(" ", "").lower()
    if v.startswith("rgba(") and v.endswith(",1)"):
        return "rgb(" + v[5:-3] + ")"
    return v


def _check_legacy_look(app: QApplication) -> None:
    """Fail if H1 CSS diverges from ChatLog (scrollbar / no bubble / type)."""
    del app  # QApplication must exist; panel needs an event loop host
    panel = ChatPanel()
    panel.resize(640, 720)
    host = panel.transcript()
    view = host.view()
    assert view is not None

    loaded = {"ok": False, "done": False}
    loop = QEventLoop()

    def _on_finished(ok: bool) -> None:
        loaded["ok"] = bool(ok)
        loaded["done"] = True
        loop.quit()

    view.loadFinished.connect(_on_finished)
    host.append_turn("user", [TextPart(markdown="hello from you")], msg_id="legacy-you")
    host.append_turn(
        "assistant",
        [TextPart(markdown="hello from iris")],
        msg_id="legacy-iris",
    )
    QTimer.singleShot(15000, loop.quit)
    if not loaded["done"]:
        loop.exec()
    try:
        view.loadFinished.disconnect(_on_finished)
    except TypeError:
        pass
    assert loaded["done"] and loaded["ok"], "legacy look loadFinished failed"

    settle = QEventLoop()
    QTimer.singleShot(200, settle.quit)
    settle.exec()

    raw = _run_js(view, _LEGACY_LOOK_JS)
    assert raw is not None, "legacy look runJavaScript returned None"
    probe = json.loads(raw) if isinstance(raw, str) else raw
    assert isinstance(probe, dict), f"bad legacy probe: {probe!r}"

    assert probe.get("hasUserTurn"), f"missing user turn: {probe}"
    assert probe.get("hasSpeakerYou"), f"missing speaker-you: {probe}"
    assert probe.get("hasScrollbarCss"), f"missing ::-webkit-scrollbar CSS: {probe}"
    assert probe.get("userBodyTransparent"), (
        f"user turn-body must not use bubble bg: {probe}"
    )
    font_px = float(probe.get("bodyFontPx") or 0)
    assert 14.0 <= font_px <= 16.0, f"body font-size ~15px expected: {probe}"
    expect_you = _normalize_css_rgb(_hex_to_rgb_css(TOKENS.chat_user_name))
    got_you = _normalize_css_rgb(str(probe.get("youColor") or ""))
    assert got_you == expect_you, f"You color {got_you!r} != {expect_you!r}: {probe}"
    overflow = str(probe.get("overflowY") or "").lower()
    assert overflow in ("auto", "scroll", "overlay"), (
        f"html/body must scroll (overflow-y): {probe}"
    )

    # Match render_user_message inset: margin-left 24px, margin-right 12px.
    assert float(probe.get("userMarginLeft") or 0) == 24.0, (
        f"user turn-body margin-left must be 24px: {probe}"
    )
    assert float(probe.get("userMarginRight") or 0) == 12.0, (
        f"user turn-body margin-right must be 12px: {probe}"
    )

    # Body font from iris.ui.chat.typography (Pretendard path), not Segoe-only theme.
    family = str(probe.get("bodyFontFamily") or "")
    expected_family = manager.get().chat_font_family
    family_ok = (
        "Pretendard" in family
        or (expected_family and expected_family in family)
    )
    assert family_ok, (
        f"body font-family must use Pretendard or typography manager "
        f"({expected_family!r}): {probe}"
    )

    # Source contract: _page_css TOKENS come from chat.typography.
    src = Path(__file__).with_name("transcript_h1.py").read_text(encoding="utf-8")
    assert "from iris.ui.chat.typography import TOKENS" in src, (
        "transcript_h1 must import TOKENS from iris.ui.chat.typography"
    )

    print("transcript_h1 legacy look ok", json.dumps(probe, ensure_ascii=False))


def main() -> int:
    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)
    _check_host_typography(app)
    _check_legacy_look(app)
    print("transcript_h1 ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
