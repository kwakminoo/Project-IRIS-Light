"""T2: H1 WebEngine transcript host renders rich MD (not QTextEdit flat dump)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

# WebEngine + QApplication before ChatPanel import (else 0xC0000409 on Windows).
ensure_qt_webengine_ready()

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.core.message_parts import TextPart
from iris.storage.conversations import ChatMessage
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.typography import TOKENS, Typography, manager
from iris.ui.shared.theme_tokens import TOKENS as THEME

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

# Legacy ChatLog look: one scroll owner, no user bubble, 720 measure + transparent thumb.
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
  function scrollbarRuleBg(selNeedle) {
    var wantHover = selNeedle.indexOf(':hover') >= 0;
    var sheets = document.styleSheets;
    for (var s = 0; s < sheets.length; s++) {
      try {
        var rules = sheets[s].cssRules || sheets[s].rules;
        for (var r = 0; r < rules.length; r++) {
          var sel = String(rules[r].selectorText || '');
          if (sel.indexOf(selNeedle) < 0) continue;
          if (!wantHover && sel.indexOf(':hover') >= 0) continue;
          var st = rules[r].style;
          return (st && (st.backgroundColor || st.background)) || '';
        }
      } catch (e) {}
    }
    var styles = document.querySelectorAll('style');
    for (var i = 0; i < styles.length; i++) {
      var txt = styles[i].textContent || '';
      var idx = txt.indexOf(selNeedle);
      if (idx < 0) continue;
      var chunk = txt.slice(idx, idx + 220);
      var m = chunk.match(/background(?:-color)?\\s*:\\s*([^;}]+)/i);
      if (m) return String(m[1] || '').trim();
    }
    return '';
  }
  function isTransparentBg(bg) {
    if (!bg) return true;
    var v = String(bg).replace(/\\s+/g, '').toLowerCase();
    if (v === 'transparent' || v === 'rgba(0,0,0,0)' || v === 'rgba(0,0,0,0.0)') return true;
    var m = v.match(/^rgba?\\((\\d+),(\\d+),(\\d+)(?:,([0-9.]+))?\\)$/);
    if (m && m[4] !== undefined && parseFloat(m[4]) === 0) return true;
    return false;
  }
  function scrollsY(ov) {
    ov = String(ov || '').toLowerCase();
    return ov === 'auto' || ov === 'scroll' || ov === 'overlay';
  }
  var html = document.documentElement;
  var body = document.body;
  var bodyCs = window.getComputedStyle(body);
  var htmlCs = window.getComputedStyle(html);
  var userBody = document.querySelector('.turn[data-role="user"] .turn-body');
  var asstBody = document.querySelector('.turn[data-role="assistant"] .turn-body');
  var userCs = userBody ? window.getComputedStyle(userBody) : null;
  var userBg = userCs ? userCs.backgroundColor : '';
  var you = document.querySelector('.turn[data-role="user"] .speaker-you');
  var youColor = you ? window.getComputedStyle(you).color : '';
  var htmlOverflowY = htmlCs.overflowY || '';
  var bodyOverflowY = bodyCs.overflowY || '';
  // Only count as scrollable when overflow-y allows scrolling (hidden overflow is not a bar).
  var htmlCanScroll = scrollsY(htmlOverflowY) && (html.scrollHeight > html.clientHeight + 1);
  var bodyCanScroll = scrollsY(bodyOverflowY) && (body.scrollHeight > body.clientHeight + 1);
  var dualScrollCandidate = scrollsY(htmlOverflowY) && scrollsY(bodyOverflowY);
  var bodyPadL = parseFloat(bodyCs.paddingLeft) || 0;
  var userLeft = userBody ? userBody.getBoundingClientRect().left : -1;
  var asstLeft = asstBody ? asstBody.getBoundingClientRect().left : -1;
  var thumbBg = scrollbarRuleBg('::-webkit-scrollbar-thumb');
  var thumbHoverBg = scrollbarRuleBg('::-webkit-scrollbar-thumb:hover');
  var trackBg = scrollbarRuleBg('::-webkit-scrollbar-track');
  var tr = document.getElementById('transcript');
  var trCs = tr ? window.getComputedStyle(tr) : null;
  var trRect = tr ? tr.getBoundingClientRect() : null;
  var mdP = document.querySelector(
    '.turn[data-role="assistant"] .md p, #transcript .md p, .md p'
  );
  var mdPCs = mdP ? window.getComputedStyle(mdP) : null;
  var roleEl = document.querySelector(
    '.turn[data-role="user"] .role, .turn[data-role="user"] .speaker-you, .role'
  );
  var speakerEl = document.querySelector(
    '.turn[data-role="user"] .speaker-you, .speaker-you'
  );
  var roleCs = roleEl ? window.getComputedStyle(roleEl) : null;
  var speakerCs = speakerEl ? window.getComputedStyle(speakerEl) : null;
  var h2 = document.querySelector('.turn[data-role="assistant"] .md h2, .md h2');
  var h2Cs = h2 ? window.getComputedStyle(h2) : null;
  var strong = document.querySelector(
    '.turn[data-role="assistant"] .md strong, .md strong'
  );
  var strongCs = strong ? window.getComputedStyle(strong) : null;
  return JSON.stringify({
    hasScrollbarCss: sheetHasScrollbar(),
    scrollbarThumbBg: thumbBg,
    scrollbarThumbHoverBg: thumbHoverBg,
    scrollbarTrackBg: trackBg,
    scrollbarThumbTransparent: isTransparentBg(thumbBg),
    scrollbarThumbHoverTransparent: isTransparentBg(thumbHoverBg),
    scrollbarTrackTransparent: isTransparentBg(trackBg),
    bodyFontPx: parseFloat(bodyCs.fontSize) || 0,
    bodyFontFamily: bodyCs.fontFamily || '',
    bodyPadBottom: parseFloat(bodyCs.paddingBottom) || 0,
    bodyPadTop: parseFloat(bodyCs.paddingTop) || 0,
    mdPFontPx: mdPCs ? (parseFloat(mdPCs.fontSize) || 0) : -1,
    mdPFontFamily: mdPCs ? (mdPCs.fontFamily || '') : '',
    mdPColor: mdPCs ? (mdPCs.color || '') : '',
    bodyColor: bodyCs.color || '',
    bodyFontWeight: parseInt(bodyCs.fontWeight, 10) || 0,
    hasMdP: !!mdP,
    roleFontWeight: roleCs ? (parseInt(roleCs.fontWeight, 10) || 0) : -1,
    speakerFontWeight: speakerCs ? (parseInt(speakerCs.fontWeight, 10) || 0) : -1,
    h2FontWeight: h2Cs ? (parseInt(h2Cs.fontWeight, 10) || 0) : -1,
    hasH2: !!h2,
    strongFontWeight: strongCs ? (parseInt(strongCs.fontWeight, 10) || 0) : -1,
    userBodyBg: userBg,
    userBodyTransparent: isTransparentBg(userBg),
    userMarginLeft: userCs ? (parseFloat(userCs.marginLeft) || 0) : -1,
    userMarginRight: userCs ? (parseFloat(userCs.marginRight) || 0) : -1,
    youColor: youColor,
    htmlOverflowY: htmlOverflowY,
    bodyOverflowY: bodyOverflowY,
    htmlCanScroll: htmlCanScroll,
    bodyCanScroll: bodyCanScroll,
    dualScrollCandidate: dualScrollCandidate,
    bodyPadL: bodyPadL,
    userLeft: userLeft,
    asstLeft: asstLeft,
    viewportW: window.innerWidth || 0,
    transcriptMaxWidth: trCs ? (trCs.maxWidth || '') : '',
    transcriptWidth: trRect ? trRect.width : -1,
    transcriptLeft: trRect ? trRect.left : -1,
    hasUserTurn: !!userBody,
    hasSpeakerYou: !!you,
    hasTopFadeCss: !!(document.querySelector('style') &&
      ((document.querySelector('style').textContent || '').indexOf('is-scrolled') >= 0 ||
       (document.querySelector('style').textContent || '').indexOf('mask-image') >= 0))
  });
})()
"""


def _seed_chat_typography() -> Typography:
    """Fixed manager.current so body CSS asserts are deterministic."""
    available = set(QFontDatabase.families())
    ui = next(
        (
            n
            for n in ("Noto Sans KR", "Malgun Gothic", "Segoe UI", "Arial")
            if n in available
        ),
        "Arial",
    )
    mono = next(
        (n for n in ("Consolas", "Courier New", "Cascadia Mono") if n in available),
        "Courier New",
    )
    prefs = Typography(
        chat_font_family=ui,
        chat_font_size=14,
        code_font_family=mono,
        code_font_size=13,
    )
    manager.current = prefs
    return prefs

_TALL_ASST_MD = "# Tall\n\n" + ("paragraph line for scroll height.\n\n" * 40)


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


_EMPTY_HOST_OVERFLOW_JS = """
(function() {
  var html = document.documentElement;
  var body = document.body;
  var bodyCs = window.getComputedStyle(body);
  var htmlCs = window.getComputedStyle(html);
  var tr = document.getElementById('transcript');
  return JSON.stringify({
    boxSizingBody: bodyCs.boxSizing || '',
    boxSizingHtml: htmlCs.boxSizing || '',
    bodyScrollHeight: body.scrollHeight || 0,
    htmlClientHeight: html.clientHeight || 0,
    bodyClientHeight: body.clientHeight || 0,
    htmlScrollHeight: html.scrollHeight || 0,
    bodyPadTop: parseFloat(bodyCs.paddingTop) || 0,
    bodyPadBottom: parseFloat(bodyCs.paddingBottom) || 0,
    turnCount: document.querySelectorAll('.turn').length,
    emptyTranscript: !!(tr && tr.children.length === 0)
  });
})()
"""


def _check_empty_host_no_phantom_overflow(app: QApplication) -> None:
    """Empty/short host must not force a vertical scrollbar (ChatLog AsNeeded parity)."""
    del app
    panel = ChatPanel()
    panel.resize(640, 720)
    panel.show()
    settle0 = QEventLoop()
    QTimer.singleShot(50, settle0.quit)
    settle0.exec()

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
    host.clear()
    QTimer.singleShot(15000, loop.quit)
    if not loaded["done"]:
        loop.exec()
    try:
        view.loadFinished.disconnect(_on_finished)
    except TypeError:
        pass
    assert loaded["done"] and loaded["ok"], "empty host loadFinished failed"

    settle = QEventLoop()
    QTimer.singleShot(200, settle.quit)
    settle.exec()

    raw = _run_js(view, _EMPTY_HOST_OVERFLOW_JS)
    assert raw is not None, "empty-host runJavaScript returned None"
    probe = json.loads(raw) if isinstance(raw, str) else raw
    assert isinstance(probe, dict), f"bad empty-host probe: {probe!r}"
    assert int(probe.get("turnCount") or 0) == 0, f"expected empty transcript: {probe}"
    assert probe.get("emptyTranscript"), f"expected empty #transcript: {probe}"

    body_sh = int(probe.get("bodyScrollHeight") or 0)
    html_ch = int(probe.get("htmlClientHeight") or 0)
    assert html_ch > 0, f"html clientHeight must be real after show/resize: {probe}"
    assert body_sh <= html_ch + 1, (
        f"empty body must not overflow viewport (phantom scrollbar): "
        f"body.scrollHeight={body_sh} html.clientHeight={html_ch}: {probe}"
    )
    assert str(probe.get("boxSizingBody") or "").lower() == "border-box", (
        f"body box-sizing must be border-box so height:100% includes padding: {probe}"
    )
    assert str(probe.get("boxSizingHtml") or "").lower() == "border-box", (
        f"html box-sizing must be border-box: {probe}"
    )
    print("transcript_h1 empty host no phantom overflow ok", json.dumps(probe))


def _check_legacy_look(app: QApplication) -> None:
    """Fail if H1 CSS diverges from ChatLog (typography + 720 measure / transparent thumb)."""
    del app  # QApplication must exist; panel needs an event loop host
    prefs = _seed_chat_typography()
    want_size = float(prefs.chat_font_size)
    want_family = prefs.chat_font_family

    panel = ChatPanel()
    # Wider than READING_MEASURE_PX so #transcript max-width 720 is the reading measure.
    panel.resize(1100, 900)
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
        [
            TextPart(
                markdown=(
                    "## Heading Two\n\n"
                    "A paragraph with **bold** for metric Diff.\n\n"
                    + _TALL_ASST_MD
                )
            )
        ],
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
    assert probe.get("scrollbarThumbTransparent"), (
        f"scrollbar thumb must be fully transparent: {probe}"
    )
    assert probe.get("scrollbarThumbHoverTransparent"), (
        f"scrollbar thumb:hover must be fully transparent: {probe}"
    )
    assert probe.get("scrollbarTrackTransparent"), (
        f"scrollbar track must stay transparent: {probe}"
    )
    assert probe.get("userBodyTransparent"), (
        f"user turn-body must not use bubble bg: {probe}"
    )
    expect_you = _normalize_css_rgb(_hex_to_rgb_css(TOKENS.chat_user_name))
    got_you = _normalize_css_rgb(str(probe.get("youColor") or ""))
    assert got_you == expect_you, f"You color {got_you!r} != {expect_you!r}: {probe}"

    html_oy = str(probe.get("htmlOverflowY") or "").lower()
    body_oy = str(probe.get("bodyOverflowY") or "").lower()
    scroll_vals = ("auto", "scroll", "overlay")
    non_scroll = ("hidden", "visible", "clip")
    assert body_oy in scroll_vals, f"body must be sole scroll owner: {probe}"
    assert html_oy in non_scroll, f"html overflow-y must not scroll: {probe}"
    assert not probe.get("dualScrollCandidate"), f"dual scroll surfaces: {probe}"
    assert not (probe.get("htmlCanScroll") and probe.get("bodyCanScroll")), (
        f"both html and body canScroll: {probe}"
    )

    # User turn flush left (same horizontal inset as assistant): margin 0 / 0.
    user_ml = float(probe.get("userMarginLeft") or 0)
    user_mr = float(probe.get("userMarginRight") or 0)
    assert abs(user_ml - 0.0) <= 1.0, (
        f"user turn-body margin-left must be ≈0: {probe}"
    )
    assert abs(user_mr - 0.0) <= 1.0, (
        f"user turn-body margin-right must be ≈0: {probe}"
    )

    # Reading measure: CSS max-width always 720; layout width when viewport is real.
    tr_max = str(probe.get("transcriptMaxWidth") or "").replace(" ", "")
    assert "720" in tr_max, f"#transcript max-width must be 720px: {probe}"
    viewport_w = float(probe.get("viewportW") or 0)
    tr_w = float(probe.get("transcriptWidth") or -1)
    if viewport_w > 720 and tr_w > 0:
        assert tr_w <= 720.5, f"#transcript width must be ≤720 when host wide: {probe}"
        tr_left = float(probe.get("transcriptLeft") or -1)
        right_gap = viewport_w - (tr_left + tr_w)
        assert abs(tr_left - right_gap) <= 24.0, (
            f"#transcript should be horizontally centered: {probe}"
        )

    pad_top = float(probe.get("bodyPadTop") or 0)
    assert pad_top >= 24.0, (
        f"body padding-top should be near ChatLog rootFrame 28: {probe}"
    )

    # Body + .md p from typography manager (not theme Segoe @15).
    live = manager.get()
    assert live.chat_font_family == want_family, (
        f"manager family drifted: {live.chat_font_family!r} != {want_family!r}"
    )
    assert live.chat_font_size == int(want_size), (
        f"manager size drifted: {live.chat_font_size} != {want_size}"
    )
    body_px = float(probe.get("bodyFontPx") or 0)
    assert abs(body_px - want_size) <= 0.5, (
        f"body font-size {body_px} must match manager {want_size}: {probe}"
    )
    family = str(probe.get("bodyFontFamily") or "")
    assert want_family in family, (
        f"body font-family must contain manager family {want_family!r}: {probe}"
    )
    assert probe.get("hasMdP"), f"missing assistant .md p: {probe}"
    p_px = float(probe.get("mdPFontPx") or 0)
    assert abs(p_px - want_size) <= 0.5, (
        f".md p font-size {p_px} must match manager {want_size}: {probe}"
    )
    p_family = str(probe.get("mdPFontFamily") or "")
    assert want_family in p_family, (
        f".md p font-family must contain {want_family!r}: {probe}"
    )
    # No Segoe-vs-typo split: body and p agree with manager, not theme Segoe alone.
    if want_family != "Segoe UI" and "Segoe" not in want_family:
        assert not (
            "Segoe" in family and want_family not in family
        ), f"body stuck on theme Segoe while manager is {want_family!r}: {probe}"

    pad_bottom = float(probe.get("bodyPadBottom") or 0)
    assert pad_bottom <= 16.0, (
        f"body padding-bottom must be ≤16 (ChatLog 12px 16px): {probe}"
    )

    # Same body color as ChatLog / chat_renderer (TOKENS.chat_body).
    log_color = _normalize_css_rgb(_hex_to_rgb_css(str(THEME.chat_body)))
    body_c = _normalize_css_rgb(str(probe.get("bodyColor") or ""))
    p_c = _normalize_css_rgb(str(probe.get("mdPColor") or ""))
    assert body_c == log_color, (
        f"body color must match ChatLog chat_body {THEME.chat_body}: {probe}"
    )
    assert p_c == log_color, (
        f".md p color must match ChatLog chat_body {THEME.chat_body}: {probe}"
    )
    body_w = int(probe.get("bodyFontWeight") or 0)
    assert body_w > 0 and body_w <= 400, (
        f"body font-weight must be ≤400 (ChatLog Regular): {probe}"
    )

    speaker_w = int(probe.get("speakerFontWeight") or 0)
    role_w = int(probe.get("roleFontWeight") or 0)
    assert speaker_w > 0 and speaker_w <= 600, (
        f".speaker-you font-weight must be ≤600 (not 900): {probe}"
    )
    assert role_w > 0 and role_w <= 600, (
        f".role font-weight must be ≤600: {probe}"
    )

    src = Path(__file__).with_name("transcript_h1.py").read_text(encoding="utf-8")
    assert "from iris.ui.chat.typography import TOKENS" in src, (
        "transcript_h1 must import TOKENS from iris.ui.chat.typography"
    )
    # Body font must come from typography manager / TOKENS — not theme_tokens Segoe.
    assert "THEME.chat_ui_font" not in src and "THEME.chat_font_size" not in src, (
        "transcript_h1 must not use THEME.chat_ui_font / THEME.chat_font_size for body"
    )
    assert (
        "manager.get()" in src
        or "TOKENS.chat_ui_font" in src
        or "TOKENS.chat_font_size" in src
    ), "transcript_h1 body font must use manager.get() or typography TOKENS"
    # Heading weight in page CSS must not exceed ChatLog renderer (600).
    h2_w = int(probe.get("h2FontWeight") or 0)
    if probe.get("hasH2") and h2_w > 0:
        assert h2_w <= 600, f".md h2 font-weight must be ≤600: {probe}"
    else:
        for m in re.finditer(
            r"\.md\s+h[12]\s*\{([^}]*)\}", src, flags=re.IGNORECASE | re.DOTALL
        ):
            block = m.group(1)
            wm = re.search(r"font-weight\s*:\s*(\d+)", block, flags=re.IGNORECASE)
            if wm:
                assert int(wm.group(1)) <= 600, (
                    f"page CSS heading weight >600: {block!r}"
                )

    # Metric Diff lever: sample-turn weights / pad / family vs manager.
    assert pad_bottom <= 16.0
    assert speaker_w <= 600 and role_w <= 600
    assert want_family in family
    if int(probe.get("strongFontWeight") or 0) > 0:
        assert int(probe["strongFontWeight"]) <= 600, (
            f".md strong font-weight must be ≤600: {probe}"
        )

    final_probe = {
        "bodyFamily": family,
        "bodySize": body_px,
        "pFamily": p_family,
        "pSize": p_px,
        "bodyColor": body_c,
        "pColor": p_c,
        "bodyWeight": body_w,
        "padBottom": pad_bottom,
        "padTop": float(probe.get("bodyPadTop") or 0),
        "speakerWeight": speaker_w,
        "roleWeight": role_w,
        "h2Weight": h2_w,
        "dualScrollCandidate": bool(probe.get("dualScrollCandidate")),
        "thumbTransparent": bool(probe.get("scrollbarThumbTransparent")),
        "userMarginLeft": float(probe.get("userMarginLeft") or 0),
        "transcriptMaxWidth": str(probe.get("transcriptMaxWidth") or ""),
        "transcriptWidth": float(probe.get("transcriptWidth") or -1),
        "managerFamily": want_family,
        "managerSize": want_size,
    }
    print("transcript_h1 legacy look ok", json.dumps(probe, ensure_ascii=False))
    print("transcript_h1 metric Diff", json.dumps(final_probe, ensure_ascii=False))


def main() -> int:
    app = QApplication.instance() or _APP
    _check_host_typography(app)
    _check_empty_host_no_phantom_overflow(app)
    _check_legacy_look(app)
    print("transcript_h1 ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
