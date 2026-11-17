"""T3: H1 CodePart card — Code/Preview tabs, HTML preview, Copy control."""

from __future__ import annotations

import json
import sys

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from iris.core.message_parts import CodePart, TextPart
from iris.ui.chat.transcript_h1 import H1TranscriptHost
from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

_BADGE_HTML = (
    "<!DOCTYPE html>\n<html><head><style>\n"
    "body{font:16px system-ui;margin:12px;background:#0f172a;color:#e2e8f0}\n"
    ".badge{display:inline-block;padding:8px 14px;border-radius:999px;"
    "background:linear-gradient(90deg,#22d3ee,#818cf8)}\n"
    "</style></head><body>\n"
    '<span class="badge">IRIS Preview OK</span>\n'
    "<p>Code 탭과 Preview 탭을 전환하세요.</p>\n"
    "</body></html>"
)

_OPEN_PREVIEW_JS = r"""
(function() {
  var card = document.querySelector('.code-card[data-previewable="1"]');
  if (!card) return JSON.stringify({ok: false, detail: 'no card'});
  var copyBtn = card.querySelector('.code-copy');
  if (copyBtn) copyBtn.click();
  var previewBtn = card.querySelector('.tab[data-tab="preview"]');
  if (previewBtn) previewBtn.click();
  var other = document.querySelector('.code-card[data-previewable="0"]');
  if (other) {
    var pBtn = other.querySelector('.tab[data-tab="preview"]');
    if (pBtn) pBtn.click();
  }
  return JSON.stringify({
    ok: true,
    hasCard: true,
    hasCopy: !!copyBtn,
    copyFlag: !!(copyBtn && copyBtn.getAttribute('data-copied') === '1')
  });
})()
"""

_PROBE_JS = r"""
(function() {
  var out = {
    hasCard: false,
    hasCopy: false,
    copyFlag: false,
    toggleOk: false,
    previewText: '',
    previewHasBadge: false,
    unsupportedNote: false,
    detail: ''
  };
  var card = document.querySelector('.code-card[data-previewable="1"]');
  out.hasCard = !!card;
  if (!card) {
    out.detail = 'no previewable code card';
    return JSON.stringify(out);
  }
  var copyBtn = card.querySelector('.code-copy');
  out.hasCopy = !!copyBtn;
  out.copyFlag = !!(copyBtn && (
    copyBtn.getAttribute('data-copied') === '1'
    || card.getAttribute('data-copied') === '1'
  ));
  var previewBtn = card.querySelector('.tab[data-tab="preview"]');
  var codeBtn = card.querySelector('.tab[data-tab="code"]');
  var pane = card.querySelector('.codepane');
  if (!(previewBtn && codeBtn && pane)) {
    out.detail = 'missing tabs/pane';
    return JSON.stringify(out);
  }
  var prev = pane.querySelector('.code-preview');
  var code = pane.querySelector('.code-src');
  var previewShown = !!(prev && !prev.hidden && code && code.hidden);
  var bodyText = '';
  try {
    var doc = prev && prev.contentDocument;
    bodyText = doc && doc.body ? (doc.body.innerText || doc.body.textContent || '') : '';
  } catch (e) {
    out.detail = 'iframe read: ' + String(e);
  }
  out.previewText = (bodyText || '').trim().slice(0, 200);
  out.previewHasBadge = /IRIS Preview/i.test(bodyText || '');
  codeBtn.click();
  var codeShown = !!(code && !code.hidden && prev && prev.hidden);
  out.toggleOk = previewShown && codeShown;

  var other = document.querySelector('.code-card[data-previewable="0"]');
  if (other) {
    var note = other.querySelector('.code-preview-unsupported');
    out.unsupportedNote = !!(note && !note.hidden
      && /preview/i.test(note.textContent || ''));
  }
  if (!out.detail) {
    out.detail = out.toggleOk && out.previewHasBadge && out.hasCopy
      ? 'ok' : 'partial';
  }
  return JSON.stringify(out);
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


def _check_code_card(app: QApplication) -> None:
    _ = app
    host = H1TranscriptHost()
    host.resize(640, 720)
    view = host.view()
    assert view is not None

    # Connect before append so we do not miss loadFinished.
    loaded = {"ok": False, "done": False}
    loop = QEventLoop()

    def _on_finished(ok: bool) -> None:
        loaded["ok"] = bool(ok)
        loaded["done"] = True
        loop.quit()

    view.loadFinished.connect(_on_finished)
    host.append_turn(
        "assistant",
        [
            TextPart(markdown="Code card check with **badge** sample."),
            CodePart(
                language="html",
                source=_BADGE_HTML,
                filename="badge.html",
            ),
            CodePart(
                language="python",
                source="print('no preview')",
                filename="skip.py",
            ),
        ],
        msg_id="t3-code",
    )
    QTimer.singleShot(15000, loop.quit)
    if not loaded["done"]:
        loop.exec()
    try:
        view.loadFinished.disconnect(_on_finished)
    except TypeError:
        pass
    assert loaded["done"] and loaded["ok"], "code card setHtml loadFinished failed"

    settle = QEventLoop()
    QTimer.singleShot(300, settle.quit)
    settle.exec()

    opened = _run_js(view, _OPEN_PREVIEW_JS)
    open_probe = json.loads(opened) if isinstance(opened, str) else opened
    assert isinstance(open_probe, dict) and open_probe.get("ok"), f"open preview: {open_probe}"
    assert open_probe.get("hasCopy") and open_probe.get("copyFlag"), f"copy: {open_probe}"

    # Reassigning srcdoc on Preview needs a beat before contentDocument is ready.
    settle2 = QEventLoop()
    QTimer.singleShot(800, settle2.quit)
    settle2.exec()

    raw = _run_js(view, _PROBE_JS)
    assert raw is not None, "runJavaScript returned None"
    probe = json.loads(raw) if isinstance(raw, str) else raw
    assert isinstance(probe, dict), f"bad probe: {probe!r}"
    assert probe.get("hasCard"), f"missing code card: {probe}"
    assert probe.get("hasCopy"), f"missing Copy control: {probe}"
    assert probe.get("copyFlag"), f"Copy handler did not set data-copied: {probe}"
    assert probe.get("toggleOk"), f"Code/Preview toggle failed: {probe}"
    assert probe.get("previewHasBadge"), f"preview missing IRIS Preview: {probe}"
    assert probe.get("unsupportedNote"), f"unsupported lang note missing: {probe}"
    print("transcript_code probe ok", json.dumps(probe, ensure_ascii=False))


def main() -> int:
    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)
    _check_code_card(app)
    print("transcript_code ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
