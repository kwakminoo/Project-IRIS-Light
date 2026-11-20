"""H1 transcript CodePart card: editable source, Copy, Code/Preview, Run.

Preview (iframe srcdoc) is for language in {html, svg} only (case-insensitive).
Other languages keep a Preview tab that shows a short unsupported note.
Run (python/py) queues requests for the host to land via chat_code_exec (T7).
Host page script lives once in the H1 document.
"""

from __future__ import annotations

import html

from iris.core.message_parts import CodePart
from iris.ui.chat.transcript_run import code_run_supported
from iris.ui.chat.typography import TOKENS

_PREVIEW_LANGS = frozenset({"html", "svg"})

_t = TOKENS
CODE_CARD_CSS = f"""
.code-card {{
  margin: 0 0 0.85rem;
  padding: 12px;
  border: 1px solid {_t.chat_block_border_solid};
  border-radius: {_t.chat_block_radius}px;
  background: {_t.chat_block_bg};
}}
.code-card .code-label {{
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #64748b;
  margin: 0 0 8px;
}}
.code-card .code-toolbar {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin: 0 0 8px;
}}
.code-card .tabs {{ display: flex; gap: 6px; }}
.code-card .tab {{
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid #334155;
  background: {_t.chat_table_header_bg};
  color: #e2e8f0;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
}}
.code-card .tab.on {{
  background: #2563eb;
  border-color: #2563eb;
}}
.code-card .code-actions {{
  margin-left: auto;
  display: flex;
  gap: 6px;
  align-items: center;
}}
.code-card .code-copy,
.code-card .code-run {{
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid #334155;
  background: {_t.chat_table_header_bg};
  color: #e2e8f0;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
}}
.code-card .code-run {{
  background: #0f766e;
  border-color: #0f766e;
}}
.code-card .code-run[data-ran="1"] {{
  background: #115e59;
}}
.code-card .codepane textarea,
.code-card .codepane iframe {{
  width: 100%;
  height: 220px;
  border: 0;
  border-radius: 8px;
  background: #020617;
  color: #e2e8f0;
  box-sizing: border-box;
}}
.code-card .codepane textarea {{
  padding: 10px;
  font: 13px/1.4 ui-monospace, Consolas, monospace;
  resize: vertical;
}}
.code-card .code-preview-unsupported {{
  margin: 0;
  padding: 14px 12px;
  border-radius: 8px;
  background: #020617;
  color: #94a3b8;
  font-size: 0.95rem;
  line-height: 1.5;
}}
"""

CODE_CARD_JS = """
(function() {
  window.__irisCodeRunRequests = window.__irisCodeRunRequests || [];
  function paneFor(btn) {
    var id = btn && btn.getAttribute('data-target');
    return id ? document.getElementById(id) : null;
  }
  document.addEventListener('click', function(ev) {
    var tab = ev.target.closest && ev.target.closest('.code-card .tab');
    if (tab) {
      var group = tab.parentElement;
      var pane = paneFor(tab);
      if (!group || !pane) return;
      group.querySelectorAll('.tab').forEach(function(b) {
        b.classList.toggle('on', b === tab);
      });
      var showPreview = tab.getAttribute('data-tab') === 'preview';
      var code = pane.querySelector('.code-src');
      var prev = pane.querySelector('.code-preview');
      var note = pane.querySelector('.code-preview-unsupported');
      if (code) code.hidden = showPreview;
      if (prev) {
        prev.hidden = !showPreview;
        if (showPreview && code) prev.srcdoc = code.value;
      }
      if (note) note.hidden = !showPreview;
      return;
    }
    var runBtn = ev.target.closest && ev.target.closest('.code-card .code-run');
    if (runBtn) {
      var runCard = runBtn.closest('.code-card');
      if (!runCard) return;
      var runTa = runCard.querySelector('.code-src');
      var source = runTa ? String(runTa.value || '') : '';
      var msgId = runCard.getAttribute('data-msg-id') || '';
      var partIndex = parseInt(runCard.getAttribute('data-part-index') || '-1', 10);
      var language = runCard.getAttribute('data-lang') || 'python';
      window.__irisCodeRunRequests.push({
        msg_id: msgId,
        part_index: isNaN(partIndex) ? -1 : partIndex,
        source: source,
        language: language
      });
      runBtn.setAttribute('data-ran', '1');
      runCard.setAttribute('data-ran', '1');
      return;
    }
    var copyBtn = ev.target.closest && ev.target.closest('.code-card .code-copy');
    if (!copyBtn) return;
    var card = copyBtn.closest('.code-card');
    var ta = card && card.querySelector('.code-src');
    var text = ta ? ta.value : '';
    // Flag first so probes see the handler without waiting on clipboard permission.
    copyBtn.setAttribute('data-copied', '1');
    if (card) card.setAttribute('data-copied', '1');
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).catch(function() {
        if (ta) {
          ta.focus();
          ta.select();
          try { document.execCommand('copy'); } catch (e) {}
        }
      });
    } else if (ta) {
      ta.focus();
      ta.select();
      try { document.execCommand('copy'); } catch (e) {}
    }
  });
})();
"""


def code_preview_supported(language: str) -> bool:
    return (language or "").strip().lower() in _PREVIEW_LANGS


def render_code_part_html(
    part: CodePart,
    *,
    pane_id: str,
    msg_id: str = "",
    part_index: int = 0,
) -> str:
    """Build one code card for the H1 transcript page."""
    lang_raw = part.language or ""
    lang = html.escape(lang_raw)
    fname = html.escape((part.filename or "").strip() or "snippet")
    src = part.source or ""
    src_esc = html.escape(src)
    preview_ok = code_preview_supported(lang_raw)
    run_ok = code_run_supported(lang_raw)
    mid = html.escape(str(msg_id or ""))
    idx = int(part_index)
    label_bits = [fname]
    if lang:
        label_bits.append(lang)
    label = " · ".join(label_bits)

    if preview_ok:
        srcdoc = html.escape(src, quote=True)
        preview_body = (
            f'<iframe class="code-preview" sandbox="allow-scripts allow-same-origin" '
            f'srcdoc="{srcdoc}" hidden></iframe>'
        )
    else:
        preview_body = (
            '<p class="code-preview-unsupported" hidden>'
            "Preview is only available for HTML and SVG."
            "</p>"
        )

    actions = '<div class="code-actions">'
    if run_ok:
        actions += (
            '<button type="button" class="code-run" data-ran="0">Run</button>'
        )
    actions += (
        '<button type="button" class="code-copy" data-copied="0">Copy</button>'
        "</div>"
    )

    return (
        f'<section class="code-card" data-part="code" data-lang="{lang}" '
        f'data-msg-id="{mid}" data-part-index="{idx}" '
        f'data-previewable="{"1" if preview_ok else "0"}" '
        f'data-runnable="{"1" if run_ok else "0"}" data-ran="0">'
        f'<div class="code-label">code · {label}</div>'
        f'<div class="code-toolbar">'
        f'<div class="tabs" role="tablist">'
        f'<button type="button" class="tab on" data-tab="code" '
        f'data-target="{html.escape(pane_id)}" role="tab">Code</button>'
        f'<button type="button" class="tab" data-tab="preview" '
        f'data-target="{html.escape(pane_id)}" role="tab">Preview</button>'
        f"</div>"
        f"{actions}"
        f"</div>"
        f'<div class="codepane" id="{html.escape(pane_id)}">'
        f'<textarea class="code-src" spellcheck="false">{src_esc}</textarea>'
        f"{preview_body}"
        f"</div></section>"
    )
