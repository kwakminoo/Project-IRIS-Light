"""H1 transcript WritingPart card: editable title/body + Save → Python queue.

Bridge choice (T4): page JS queue + host ``take_writing_updates`` via
``runJavaScript`` drain. No QWebChannel on the H1 setHtml page (qwebchannel.js
would be needed); App Host keeps QWebChannel for iframe apps.
No App/Run (T5/T7).
"""

from __future__ import annotations

import html
import json
from typing import Any

from iris.core.message_parts import WritingPart

WRITING_CARD_CSS = """
.writing-card {
  margin: 0 0 0.85rem;
  padding: 12px;
  border: 1px solid #1f2937;
  border-radius: 10px;
  background: #0f172a;
}
.writing-card .writing-label {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #64748b;
  margin: 0 0 8px;
}
.writing-card .writing-title {
  width: 100%;
  box-sizing: border-box;
  margin: 0 0 8px;
  padding: 8px 10px;
  border: 1px solid #334155;
  border-radius: 8px;
  background: #020617;
  color: #f8fafc;
  font: inherit;
  font-size: 14px;
  font-weight: 600;
}
.writing-card .writing-body {
  width: 100%;
  min-height: 140px;
  box-sizing: border-box;
  margin: 0 0 8px;
  padding: 10px;
  border: 1px solid #334155;
  border-radius: 8px;
  background: #020617;
  color: #e2e8f0;
  font: inherit;
  font-size: 14px;
  line-height: 1.5;
  resize: vertical;
}
.writing-card .writing-toolbar {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
}
.writing-card .writing-save {
  padding: 6px 14px;
  border-radius: 8px;
  border: 1px solid #334155;
  background: #2563eb;
  color: #f8fafc;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
}
.writing-card .writing-save[data-saved="1"] {
  background: #0f766e;
  border-color: #0f766e;
}
"""

WRITING_CARD_JS = """
(function() {
  window.__irisWritingUpdates = window.__irisWritingUpdates || [];
  document.addEventListener('click', function(ev) {
    var btn = ev.target.closest && ev.target.closest('.writing-card .writing-save');
    if (!btn) return;
    var card = btn.closest('.writing-card');
    if (!card) return;
    var titleEl = card.querySelector('.writing-title');
    var bodyEl = card.querySelector('.writing-body');
    var title = titleEl ? String(titleEl.value || '') : '';
    var body = bodyEl ? String(bodyEl.value || '') : '';
    var msgId = card.getAttribute('data-msg-id') || '';
    var partIndex = parseInt(card.getAttribute('data-part-index') || '-1', 10);
    var update = {
      msg_id: msgId,
      part_index: isNaN(partIndex) ? -1 : partIndex,
      title: title,
      body: body
    };
    window.__irisWritingUpdates.push(update);
    btn.setAttribute('data-saved', '1');
    card.setAttribute('data-saved', '1');
  });
})();
"""

DRAIN_WRITING_UPDATES_JS = """
(function() {
  var q = window.__irisWritingUpdates || [];
  window.__irisWritingUpdates = [];
  return JSON.stringify(q);
})()
"""


def render_writing_part_html(
    part: WritingPart,
    *,
    msg_id: str = "",
    part_index: int = 0,
) -> str:
    """Build one editable writing card for the H1 transcript page."""
    mid = html.escape(str(msg_id or ""))
    idx = int(part_index)
    title = html.escape(part.title or "")
    body = html.escape(part.body or "")
    return (
        f'<section class="writing-card" data-part="writing" '
        f'data-msg-id="{mid}" data-part-index="{idx}" data-saved="0">'
        f'<div class="writing-label">writing</div>'
        f'<input class="writing-title" type="text" value="{title}" '
        f'spellcheck="true" aria-label="Writing title">'
        f'<textarea class="writing-body" spellcheck="true" '
        f'aria-label="Writing body">{body}</textarea>'
        f'<div class="writing-toolbar">'
        f'<button type="button" class="writing-save" data-saved="0">Save</button>'
        f"</div></section>"
    )


def parse_writing_updates_raw(raw: Any) -> list[dict[str, Any]]:
    """Normalize drain JS result into update dicts."""
    if raw is None:
        return []
    if isinstance(raw, list):
        data = raw
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        data = json.loads(text)
    else:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "msg_id": str(item.get("msg_id") or item.get("msgId") or ""),
                "part_index": int(item.get("part_index", item.get("partIndex", -1))),
                "title": str(item.get("title") or ""),
                "body": str(item.get("body") or ""),
            }
        )
    return out
