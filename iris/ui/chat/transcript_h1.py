"""H1 transcript host: one QWebEngineView page for chat turns (T2–T9).

Primary ChatPanel surface (T9). Legacy ChatLogTextEdit (`_log`) may stay hidden
for leftover helpers. T10: assistant turns expose iris-tts://; navigation emits
speaker_clicked. Canonical parts stream is PartStreamEvent (open/delta/close)
via begin_part_stream / apply_part_events.

XSS: TextPart markdown goes through chat_renderer (python-markdown + sanitize),
including ```matrix → data-iris-matrix tables.
CodePart cards use escaped source + sandboxed preview iframes (html/svg only).
WritingPart cards are editable title/body with Save → JS queue drain.
AppPart cards use complete-HTML gate + sandboxed srcdoc iframes (displayMode).
Code Run → ExecutionPart + ImagePart on the same turn (chat_code_exec).
DiagramPart → card link (iris-diagram://) → ChatPanel.show_diagram.
Other non-text parts render as muted escaped prose via parts_display_md.
"""

from __future__ import annotations

import html
import json
import sys
from dataclasses import dataclass, replace
from typing import Any, Sequence
from urllib.parse import quote

from PyQt6.QtCore import QCoreApplication, QEvent, QEventLoop, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QWheelEvent
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from iris.core.message_parts import (
    AppPart,
    CodePart,
    DiagramPart,
    ExecutionPart,
    ImagePart,
    MessagePart,
    TextPart,
    ToolPart,
    ToolShellPart,
    WritingPart,
    parts_display_md,
)
from iris.core.part_stream import PartClose, PartDelta, PartOpen, PartStreamEvent
from iris.ui.chat.chat_blocks import ToolShellBlock, marked_tool_shell_to_html
from iris.ui.chat.chat_renderer import (
    _ATTACH_TOKEN,
    _swap_local_attachments,
    matrix_grid_to_html,
    parse_matrix_grid,
    render_markdown_document,
)
from iris.ui.chat.transcript_app import APP_CARD_CSS, render_app_part_html
from iris.ui.chat.transcript_code import CODE_CARD_CSS, CODE_CARD_JS, render_code_part_html
from iris.ui.chat.transcript_run import (
    DRAIN_CODE_RUN_REQUESTS_JS,
    EXEC_CARD_CSS,
    land_code_run_on_transcript,
    parse_code_run_requests_raw,
    render_execution_part_html,
    render_image_part_html,
)
from iris.ui.chat.transcript_writing import (
    DRAIN_WRITING_UPDATES_JS,
    WRITING_CARD_CSS,
    WRITING_CARD_JS,
    parse_writing_updates_raw,
    render_writing_part_html,
)
from iris.ui.chat.typography import TOKENS, manager


def _style_font_family(family: str) -> str:
    """CSS <style> font-family; not html.escape (entities break Chromium style blocks)."""
    safe = (family or "").replace("\\", "\\\\").replace("'", "\\'")
    return f"'{safe}'"


def _page_css() -> str:
    """Match legacy ChatLog look: transparent log, typography tokens, speaker labels."""
    t = TOKENS
    prefs = manager.get()
    ui_font = _style_font_family(prefs.chat_font_family)
    mono_font = _style_font_family(prefs.code_font_family)
    # Match ChatLog QScrollBar: 8px track, transparent thumb.
    base = f"""
:root {{ color-scheme: dark; }}
html, body {{
  margin: 0;
  height: 100%;
  overflow-x: hidden;
  overflow-y: auto;
  background: transparent !important;
}}
body {{
  padding: 12px 16px 28px;
  font-family: {ui_font};
  font-size: {t.chat_font_size};
  line-height: {t.chat_line_height};
  color: {t.chat_body};
  background: transparent;
}}
::-webkit-scrollbar {{
  width: 8px;
  height: 8px;
}}
::-webkit-scrollbar-track {{
  background: transparent;
}}
::-webkit-scrollbar-thumb {{
  background: transparent;
  border-radius: 4px;
  min-height: 28px;
}}
::-webkit-scrollbar-thumb:hover {{
  background: transparent;
}}
::selection {{
  background: {t.chat_selection_bg};
  color: {t.chat_selection_fg};
}}
#transcript {{ max-width: none; }}
.turn {{
  margin: 0 0 10px;
  padding: 0;
  border: none;
  border-radius: 0;
  background: transparent;
}}
.turn[data-role="user"] .turn-body {{
  max-width: 100%;
  margin-left: 0;
  margin-right: 12px;
  padding: 0;
  border-radius: 0;
  background: transparent;
}}
.role {{
  margin: 8px 0 6px;
  font-family: {ui_font};
  font-size: {t.font_size_micro};
  font-weight: 600;
  letter-spacing: 0;
  text-transform: none;
  color: inherit;
}}
.turn[data-role="user"] .role {{
  display: inline;
  margin: 0 0.35em 0 0;
}}
.turn[data-role="user"] .turn-body > .md > p:first-child {{
  display: inline;
}}
.role .speaker-you {{ color: {t.chat_user_name}; }}
.role .speaker-iris {{ color: {t.chat_iris_name}; }}
.md h1 {{
  font-size: 1.35rem;
  font-weight: 700;
  line-height: 1.35;
  margin: 0 0 0.65rem;
  color: {t.chat_body};
}}
.md h2 {{
  font-size: 1.15rem;
  font-weight: 650;
  line-height: 1.4;
  margin: 0.85rem 0 0.5rem;
  color: {t.chat_body};
}}
.md p {{
  margin: 0 0 0.75rem;
  line-height: {t.chat_line_height};
}}
.md ul, .md ol {{
  margin: 0 0 0.75rem;
  padding-left: 1.35rem;
  line-height: {t.chat_line_height};
}}
.md li {{ margin: 0.2rem 0; }}
.md strong {{ color: {t.chat_body}; font-weight: 650; }}
.md code {{
  font-family: {mono_font};
  font-size: 0.9em;
  line-height: {t.chat_block_line_height};
  background: {t.chat_inline_code_bg};
  color: {t.chat_inline_code_color};
  padding: 0.1em 0.35em;
  border-radius: 4px;
}}
.md pre {{
  margin: 0 0 0.75rem;
  padding: 10px 12px;
  border-radius: {t.chat_block_radius}px;
  border: 1px solid {t.chat_block_border_solid};
  background: {t.chat_block_bg};
  overflow-x: auto;
}}
.md pre code {{ padding: 0; background: transparent; color: inherit; }}
.part-muted {{
  margin: 0;
  padding: 8px 10px;
  border-radius: {t.chat_block_radius}px;
  border: 1px solid {t.chat_block_border_solid};
  background: {t.chat_block_bg};
  color: {t.text_secondary};
  white-space: pre-wrap;
  line-height: {t.chat_line_height};
  font-size: 0.95rem;
}}
.md table[data-iris-matrix="1"] {{
  border-collapse: collapse;
  margin: 6px 0 0.75rem;
}}
.md table[data-iris-matrix="1"] td {{
  text-align: center;
  min-width: 28px;
}}
.diagram-card {{
  margin: 0 0 0.75rem;
  padding: 10px 12px;
  border: 1px solid {t.chat_block_border_solid};
  border-radius: {t.chat_block_radius}px;
  background: {t.chat_block_bg};
}}
.diagram-card .diagram-label {{
  font-size: 11px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: {t.text_muted};
  margin: 0 0 6px;
}}
.diagram-card .diagram-title {{
  margin: 0 0 6px;
  color: {t.chat_body};
  font-weight: 600;
}}
.diagram-card a.diagram-open {{
  color: {t.chat_user_name};
  text-decoration: none;
  font-size: 0.95rem;
}}
.diagram-card a.diagram-open:hover {{ text-decoration: underline; }}
.tts-row {{ margin: 6px 0 0; }}
.tts-row a.tts-link {{
  color: {t.chat_user_name};
  text-decoration: none;
  font-size: 0.9rem;
}}
.tts-row a.tts-link:hover {{ text-decoration: underline; }}
"""
    return base + CODE_CARD_CSS + WRITING_CARD_CSS + APP_CARD_CSS + EXEC_CARD_CSS


# Top fade + scroll notify (iris-scroll://y/max) when body scrolls.
# Mute flag suppresses notify during set_scroll_y / scroll_to_bottom / DOM patch.
_SCROLL_BRIDGE_JS = """
(function() {
  if (!document.__irisZoomWheelBound) {
    document.__irisZoomWheelBound = true;
    document.addEventListener('wheel', function(e) {
      if (e.ctrlKey) e.preventDefault();
    }, { passive: false });
  }
  var b = document.body;
  if (!b || b.__irisScrollBound) return;
  b.__irisScrollBound = true;
  var pending = null;
  function syncFade() {
    b.classList.toggle('is-scrolled', (b.scrollTop || 0) > 0);
  }
  function notify() {
    syncFade();
    if (b.__irisScrollMute) return;
    if (pending != null) return;
    pending = requestAnimationFrame(function() {
      pending = null;
      if (b.__irisScrollMute) return;
      var y = Math.round(b.scrollTop || 0);
      var max = Math.max(0, (b.scrollHeight || 0) - (b.clientHeight || 0));
      var a = document.createElement('a');
      a.href = 'iris-scroll://' + y + '/' + max;
      a.click();
    });
  }
  b.addEventListener('scroll', notify, { passive: true });
  syncFade();
})();
"""


def _speaker_label(role: str) -> tuple[str, str]:
    """Return (display name, css class) matching legacy ChatLog speaker prefixes."""
    key = (role or "").strip().lower()
    if key in ("user", "you"):
        return "You", "speaker-you"
    if key in ("assistant", "iris"):
        return "Iris", "speaker-iris"
    name = (role or "Iris").strip() or "Iris"
    return name, "speaker-iris"

_PART_STREAM_JS = r"""
(function() {
  if (window.__irisPartStream) return;
  function lastTurn() {
    var nodes = document.querySelectorAll('#transcript .turn');
    return nodes.length ? nodes[nodes.length - 1] : null;
  }
  window.__irisPartStream = {
    open: function(partId, type, html) {
      var turn = lastTurn();
      if (!turn) return false;
      turn.querySelectorAll('p.part-muted').forEach(function(p) {
        if (!(p.textContent || '').trim()) p.remove();
      });
      var wrap = document.createElement('div');
      wrap.innerHTML = html;
      var node = wrap.firstElementChild;
      if (!node) return false;
      node.id = 'part-' + partId;
      node.setAttribute('data-part-id', partId);
      node.setAttribute('data-stream-type', type);
      node.setAttribute('data-streaming', '1');
      turn.appendChild(node);
      return true;
    },
    delta: function(partId, text) {
      var el = document.getElementById('part-' + partId);
      if (!el) return false;
      var type = el.getAttribute('data-stream-type') || '';
      if (type === 'code') {
        var ta = el.querySelector('.code-src');
        if (!ta) return false;
        ta.value = (ta.value || '') + text;
        return true;
      }
      el.textContent = (el.textContent || '') + text;
      return true;
    },
    close: function(partId, html) {
      var el = document.getElementById('part-' + partId);
      if (!el) return false;
      if (html) {
        var wrap = document.createElement('div');
        wrap.innerHTML = html;
        var node = wrap.firstElementChild;
        if (node) {
          node.id = 'part-' + partId;
          node.setAttribute('data-part-id', partId);
          el.replaceWith(node);
          el = node;
        }
      }
      if (el) el.removeAttribute('data-streaming');
      return true;
    }
  };
})();
"""


@dataclass(frozen=True)
class _Turn:
    role: str
    parts: tuple[MessagePart, ...]
    msg_id: str


@dataclass
class _StreamPart:
    type: str
    text: str = ""
    language: str = ""
    name: str = ""


def _webengine_import_safe() -> bool:
    """True when QWebEngineWidgets can be imported (ShareOpenGLContexts before QApp)."""
    if "PyQt6.QtWebEngineWidgets" in sys.modules:
        return True
    app = QCoreApplication.instance()
    if app is None:
        return False
    try:
        return bool(
            app.testAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        )
    except Exception:
        return False


def render_diagram_part_html(part: DiagramPart) -> str:
    """Card + iris-diagram:// reopen link (ChatPanel.show_diagram)."""
    title = (part.title or part.kind or "구조도").strip() or "구조도"
    kind = (part.kind or "").strip()
    path = (part.path or "").strip()
    href = "iris-diagram://" + quote(path, safe="")
    kind_bit = f" · {html.escape(kind)}" if kind else ""
    return (
        f'<section class="diagram-card" data-part="diagram" '
        f'data-diagram-path="{html.escape(path, quote=True)}" '
        f'data-diagram-kind="{html.escape(kind, quote=True)}">'
        f'<div class="diagram-label">diagram{kind_bit}</div>'
        f'<p class="diagram-title">{html.escape(title)}</p>'
        f'<a class="diagram-open" href="{html.escape(href, quote=True)}">다시 보기</a>'
        f"</section>"
    )


class H1TranscriptHost(QWidget):
    """One Chromium page; implements TranscriptApi for text + code + writing + stream + run."""

    writing_saved = pyqtSignal(str, int, str, str)  # msg_id, part_index, title, body
    code_run_landed = pyqtSignal(str, bool)  # msg_id, ok
    diagram_open_requested = pyqtSignal(str)  # html_path
    speaker_clicked = pyqtSignal(str)  # iris-tts:// msg_id
    update_action_clicked = pyqtSignal(str)  # iris-update:// apply | later
    iris_agent_update_action_clicked = pyqtSignal(str)  # iris-agent-update:// apply | later
    ollama_login_clicked = pyqtSignal()
    shell_approval_clicked = pyqtSignal(str)  # iris-run|always|skip|mode://block_id
    scrolled_by_user = pyqtSignal()  # body scroll → ChatPanel hold/follow

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("H1TranscriptHost")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._turns: list[_Turn] = []
        self._view = None
        self._code_seq = 0
        self._writing_inbox: list[dict[str, Any]] = []
        self._code_run_inbox: list[dict[str, Any]] = []
        self._stream_active = False
        self._stream_parts: dict[str, _StreamPart] = {}
        self._stream_order: list[str] = []
        self._page_ready = False
        self._scroll_y_cache = 0
        self._scroll_max_cache = 0
        self._slot = QWidget(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._slot, 1)

    _PAGE_ZOOM = 1.0

    def reset_page_zoom(self) -> None:
        """Pin Chromium paint zoom; chat typography stays in CSS tokens."""
        view = self._view
        if view is None:
            return
        view.setZoomFactor(float(self._PAGE_ZOOM))

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.reset_page_zoom()

    def widget(self) -> QWidget:
        return self

    def clear(self) -> None:
        self._turns.clear()
        self._writing_inbox.clear()
        self._code_run_inbox.clear()
        self._reset_stream_state()
        if self._view is not None:
            self._render()

    def append_parts_to_turn(
        self,
        msg_id: str,
        parts: Sequence[MessagePart],
        *,
        re_render: bool = True,
    ) -> bool:
        """Append parts onto the turn matching msg_id (or the last turn if empty)."""
        if not parts:
            return False
        mid = str(msg_id or "")
        target_i = -1
        if mid:
            for i, turn in enumerate(self._turns):
                if turn.msg_id == mid:
                    target_i = i
                    break
        elif self._turns:
            target_i = len(self._turns) - 1
        if target_i < 0:
            return False
        turn = self._turns[target_i]
        self._turns[target_i] = replace(turn, parts=tuple(turn.parts) + tuple(parts))
        if re_render:
            self._render()
        return True

    def append_turn(
        self,
        role: str,
        parts: Sequence[MessagePart],
        *,
        msg_id: str = "",
    ) -> None:
        self._reset_stream_state()
        self._turns.append(
            _Turn(role=str(role or ""), parts=tuple(parts), msg_id=str(msg_id or ""))
        )
        self._render()

    def upsert_tool_shell_part(self, part: ToolShellPart) -> bool:
        """Insert or replace a ToolShellPart by block_id without full-page rebuild when possible."""
        bid = str(part.block_id or "").strip()
        if not bid:
            return False
        for ti, turn in enumerate(self._turns):
            for pi, existing in enumerate(turn.parts):
                if isinstance(existing, ToolShellPart) and str(existing.block_id) == bid:
                    new_parts = list(turn.parts)
                    new_parts[pi] = part
                    self._turns[ti] = replace(turn, parts=tuple(new_parts))
                    html_body = marked_tool_shell_to_html(
                        ToolShellBlock(
                            title=part.title or "Shell",
                            command=part.command or "",
                            output=part.output or "",
                            status=part.status or "ok",
                            block_id=bid,
                            collapsed=bool(part.collapsed),
                            phase=(part.phase or "done").strip() or "done",
                        )
                    )
                    self._patch_tool_shell_dom(bid, html_body)
                    return True
        self.append_turn("assistant", [part], msg_id=f"shell-{bid}")
        return True

    def _patch_tool_shell_dom(self, block_id: str, html_body: str) -> None:
        """Replace one marked shell card in #transcript; fall back to full patch."""
        view = self._view
        if view is None or not self._page_ready:
            self._render()
            return
        start = f"IRIS_TOOL_{block_id}_START"
        end = f"IRIS_TOOL_{block_id}_END"
        script = (
            "(function(){"
            "var t=document.getElementById('transcript');"
            "if(!t)return false;"
            f"var s={json.dumps(start)}, e={json.dumps(end)};"
            "var html=" + json.dumps(html_body) + ";"
            "var spans=t.querySelectorAll('span');"
            "var a=null,b=null;"
            "for(var i=0;i<spans.length;i++){"
            " var tx=(spans[i].textContent||'').trim();"
            " if(tx===s)a=spans[i];"
            " if(tx===e){b=spans[i]; if(a)break;}"
            "}"
            "if(!a||!b||!a.parentNode)return false;"
            "var range=document.createRange();"
            "range.setStartBefore(a); range.setEndAfter(b);"
            "range.deleteContents();"
            "var tmp=document.createElement('div'); tmp.innerHTML=html;"
            "var frag=document.createDocumentFragment();"
            "while(tmp.firstChild) frag.appendChild(tmp.firstChild);"
            "range.insertNode(frag);"
            "return true;"
            "})();"
        )

        def _cb(ok: Any) -> None:
            if not ok:
                self._render()

        view.page().runJavaScript(script, _cb)

    def begin_part_stream(self, role: str = "assistant", msg_id: str = "") -> None:
        """Start one assistant/user turn shell for card-stable part streaming.

        Full page render once here; later open/delta/close update `#part-{id}`
        via JS (no transcript rewrite per chunk).
        """
        self._reset_stream_state()
        self._stream_active = True
        self._turns.append(
            _Turn(role=str(role or "assistant"), parts=(), msg_id=str(msg_id or ""))
        )
        self._render()

    def apply_part_events(self, events: Sequence[PartStreamEvent]) -> None:
        """Apply open/delta/close without rebuilding the whole transcript page."""
        if not events:
            return
        if not self._stream_active or not self._turns:
            return
        for ev in events:
            if isinstance(ev, PartOpen):
                self._on_part_open(ev)
            elif isinstance(ev, PartDelta):
                self._on_part_delta(ev)
            elif isinstance(ev, PartClose):
                self._on_part_close(ev)
        self._sync_stream_turn_parts()

    def view(self):
        """QWebEngineView once created (checks / probes)."""
        return self._ensure_view()

    def _run_js_sync(self, script: str, *, timeout_ms: int = 3000) -> Any:
        """runJavaScript with a short event-loop wait (scroll probes)."""
        view = self._view
        if view is None:
            return None
        box: dict[str, Any] = {"raw": None, "done": False}
        loop = QEventLoop()

        def _cb(raw: Any) -> None:
            box["raw"] = raw
            box["done"] = True
            loop.quit()

        view.page().runJavaScript(script, _cb)
        QTimer.singleShot(timeout_ms, loop.quit)
        if not box["done"]:
            loop.exec()
        return box["raw"]

    def scroll_y(self) -> int:
        """Current body.scrollTop (cache, else probe)."""
        raw = self._run_js_sync(
            "(function(){var b=document.body;return Math.round((b&&b.scrollTop)||0);})()"
        )
        if raw is None:
            return int(self._scroll_y_cache)
        try:
            y = int(raw)
        except (TypeError, ValueError):
            y = int(self._scroll_y_cache)
        self._scroll_y_cache = y
        return y

    def set_scroll_y(self, value: int) -> None:
        """Programmatic body.scrollTop (mutes user-scroll notify)."""
        v = max(0, int(value))
        self._scroll_y_cache = v
        if self._view is None:
            return
        self._run_js_sync(
            "(function(){"
            "var b=document.body;if(!b)return;"
            "b.__irisScrollMute=true;"
            f"b.scrollTop={v};"
            "b.classList.toggle('is-scrolled',(b.scrollTop||0)>0);"
            "b.__irisScrollMute=false;"
            "})();"
        )

    def _apply_wrapper_wheel(self, event: QWheelEvent) -> bool:
        """Scroll H1 body when wheel hits host/view wrappers (Chromium child already scrolls)."""
        pixel = event.pixelDelta()
        dy = int(pixel.y()) if not pixel.isNull() else int(event.angleDelta().y())
        if dy == 0:
            return False
        self.set_scroll_y(int(self._scroll_y_cache) - dy)
        self.scrolled_by_user.emit()
        return True

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if self._apply_wrapper_wheel(event):
            event.accept()
            return
        event.ignore()

    def eventFilter(self, watched: object, event: QEvent) -> bool:  # noqa: N802
        if watched is self._view and event.type() == QEvent.Type.Wheel:
            wheel = event
            if isinstance(wheel, QWheelEvent) and self._apply_wrapper_wheel(wheel):
                wheel.accept()
                return True
        return super().eventFilter(watched, event)

    def scroll_to_bottom(self) -> None:
        """Scroll body to max (mutes user-scroll notify)."""
        if self._view is None:
            return
        raw = self._run_js_sync(
            "(function(){"
            "var b=document.body;if(!b)return 0;"
            "b.__irisScrollMute=true;"
            "var max=Math.max(0,(b.scrollHeight||0)-(b.clientHeight||0));"
            "b.scrollTop=max;"
            "b.classList.toggle('is-scrolled',(b.scrollTop||0)>0);"
            "b.__irisScrollMute=false;"
            "return Math.round(max);"
            "})();"
        )
        try:
            self._scroll_max_cache = int(raw or 0)
            self._scroll_y_cache = self._scroll_max_cache
        except (TypeError, ValueError):
            pass

    def at_bottom(self, threshold: int = 2) -> bool:
        """True when body scrollTop is within threshold of max."""
        thr = max(0, int(threshold))
        raw = self._run_js_sync(
            "(function(){"
            "var b=document.body;if(!b)return true;"
            "var max=Math.max(0,(b.scrollHeight||0)-(b.clientHeight||0));"
            f"return ((b.scrollTop||0)>=max-{thr});"
            "})();"
        )
        return bool(raw) if raw is not None else (
            self._scroll_y_cache >= max(0, self._scroll_max_cache - thr)
        )

    def _on_body_scroll_notify(self, y: int, max_y: int) -> None:
        """JS iris-scroll:// bridge → cache + scrolled_by_user."""
        self._scroll_y_cache = max(0, int(y))
        self._scroll_max_cache = max(0, int(max_y))
        self.scrolled_by_user.emit()

    def take_writing_updates(self, *, timeout_ms: int = 5000) -> list[dict[str, Any]]:
        """Drain Save events from the page JS queue (runJavaScript poll)."""
        view = self._view
        if view is None:
            pending = list(self._writing_inbox)
            self._writing_inbox.clear()
            return pending
        box: dict[str, Any] = {"raw": None, "done": False}
        loop = QEventLoop()

        def _cb(raw: Any) -> None:
            box["raw"] = raw
            box["done"] = True
            loop.quit()

        view.page().runJavaScript(DRAIN_WRITING_UPDATES_JS, _cb)
        QTimer.singleShot(timeout_ms, loop.quit)
        if not box["done"]:
            loop.exec()
        drained = parse_writing_updates_raw(box["raw"])
        if self._writing_inbox:
            drained = list(self._writing_inbox) + drained
            self._writing_inbox.clear()
        for item in drained:
            self.apply_writing_update(
                str(item.get("msg_id") or ""),
                int(item.get("part_index", -1)),
                str(item.get("title") or ""),
                str(item.get("body") or ""),
                emit=True,
            )
        return drained

    def apply_writing_update(
        self,
        msg_id: str,
        part_index: int,
        title: str,
        body: str,
        *,
        emit: bool = False,
        re_render: bool = False,
    ) -> bool:
        """Replace WritingPart in memory for msg_id / part_index."""
        mid = str(msg_id or "")
        idx = int(part_index)
        for ti, turn in enumerate(self._turns):
            if mid and turn.msg_id != mid:
                continue
            if idx < 0 or idx >= len(turn.parts):
                continue
            part = turn.parts[idx]
            if not isinstance(part, WritingPart):
                continue
            new_parts = list(turn.parts)
            new_parts[idx] = WritingPart(title=str(title or ""), body=str(body or ""))
            self._turns[ti] = replace(turn, parts=tuple(new_parts))
            if emit:
                self.writing_saved.emit(mid or turn.msg_id, idx, str(title or ""), str(body or ""))
            if re_render:
                self._render()
            return True
        return False

    def take_code_run_requests(self, *, timeout_ms: int = 5000) -> list[dict[str, Any]]:
        """Drain Run clicks from the page JS queue and land each on the transcript."""
        view = self._view
        if view is None:
            pending = list(self._code_run_inbox)
            self._code_run_inbox.clear()
            drained = pending
        else:
            box: dict[str, Any] = {"raw": None, "done": False}
            loop = QEventLoop()

            def _cb(raw: Any) -> None:
                box["raw"] = raw
                box["done"] = True
                loop.quit()

            view.page().runJavaScript(DRAIN_CODE_RUN_REQUESTS_JS, _cb)
            QTimer.singleShot(timeout_ms, loop.quit)
            if not box["done"]:
                loop.exec()
            drained = parse_code_run_requests_raw(box["raw"])
            if self._code_run_inbox:
                drained = list(self._code_run_inbox) + drained
                self._code_run_inbox.clear()
        landed: list[dict[str, Any]] = []
        for item in drained:
            mid = str(item.get("msg_id") or "")
            result = land_code_run_on_transcript(
                self,
                str(item.get("source") or ""),
                language=str(item.get("language") or "python"),
                msg_id=mid,
            )
            self.code_run_landed.emit(mid, bool(result.get("ok")))
            landed.append(result)
        return landed

    def parts_for_message(self, msg_id: str) -> list[MessagePart]:
        mid = str(msg_id or "")
        for turn in self._turns:
            if turn.msg_id == mid:
                return list(turn.parts)
        return []

    def _reset_stream_state(self) -> None:
        self._stream_active = False
        self._stream_parts.clear()
        self._stream_order.clear()

    def _sync_stream_turn_parts(self) -> None:
        if not self._turns:
            return
        parts: list[MessagePart] = []
        for pid in self._stream_order:
            sp = self._stream_parts.get(pid)
            if sp is None:
                continue
            parts.append(self._stream_part_to_message(sp))
        turn = self._turns[-1]
        self._turns[-1] = replace(turn, parts=tuple(parts))

    def _stream_part_to_message(self, sp: _StreamPart) -> MessagePart:
        if sp.type == "code":
            return CodePart(language=sp.language or "", source=sp.text)
        if sp.type == "tool":
            return ToolPart(name=sp.name or "tool", detail=sp.text)
        return TextPart(markdown=sp.text)

    def _on_part_open(self, ev: PartOpen) -> None:
        kind = str(ev.type or "text")
        self._stream_parts[ev.part_id] = _StreamPart(
            type=kind,
            language=str(ev.language or ""),
            name=str(ev.name or ""),
        )
        self._stream_order.append(ev.part_id)
        if kind == "code":
            self._code_seq += 1
            pane_id = f"codepane-stream-{self._code_seq}"
            turn = self._turns[-1] if self._turns else None
            shell = render_code_part_html(
                CodePart(language=str(ev.language or ""), source=""),
                pane_id=pane_id,
                msg_id=turn.msg_id if turn else "",
                part_index=max(0, len(self._stream_order) - 1),
            )
        else:
            shell = '<div class="md part-stream"></div>'
        self._eval_stream_js(
            "window.__irisPartStream && window.__irisPartStream.open("
            f"{json.dumps(ev.part_id)}, {json.dumps(kind)}, {json.dumps(shell)})"
        )

    def _on_part_delta(self, ev: PartDelta) -> None:
        sp = self._stream_parts.get(ev.part_id)
        if sp is None:
            return
        sp.text += ev.text or ""
        self._eval_stream_js(
            "window.__irisPartStream && window.__irisPartStream.delta("
            f"{json.dumps(ev.part_id)}, {json.dumps(ev.text or '')})"
        )

    def _on_part_close(self, ev: PartClose) -> None:
        sp = self._stream_parts.get(ev.part_id)
        if sp is None:
            return
        final_html = ""
        if sp.type == "text":
            rendered = render_markdown_document(sp.text or "", citations=False)
            if rendered.strip():
                final_html = f'<div class="md">{rendered}</div>'
            else:
                final_html = '<div class="md part-stream"></div>'
        elif sp.type == "code":
            lang = (sp.language or "").strip().lower()
            if lang == "matrix":
                final_html = (
                    '<div class="md">'
                    + matrix_grid_to_html(parse_matrix_grid(sp.text or ""))
                    + "</div>"
                )
            else:
                self._code_seq += 1
                pane_id = f"codepane-stream-{self._code_seq}"
                turn = self._turns[-1] if self._turns else None
                part_index = 0
                for i, pid in enumerate(self._stream_order):
                    if pid == ev.part_id:
                        part_index = i
                        break
                final_html = render_code_part_html(
                    CodePart(language=sp.language or "", source=sp.text or ""),
                    pane_id=pane_id,
                    msg_id=turn.msg_id if turn else "",
                    part_index=part_index,
                )
        self._eval_stream_js(
            "window.__irisPartStream && window.__irisPartStream.close("
            f"{json.dumps(ev.part_id)}, {json.dumps(final_html)})"
        )

    def _eval_stream_js(self, script: str) -> None:
        view = self._view
        if view is None:
            return
        view.page().runJavaScript(script)

    def _ensure_view(self):
        if self._view is not None:
            return self._view
        if not _webengine_import_safe():
            raise ImportError(
                "QtWebEngineWidgets requires ensure_qt_webengine_ready "
                "before QApplication"
            )
        # WebEngine import must follow ensure_qt_webengine_ready + QApplication.
        from PyQt6.QtWebEngineCore import QWebEnginePage
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        host = self

        class _TranscriptPage(QWebEnginePage):
            def acceptNavigationRequest(self, url, nav_type, is_main_frame):  # noqa: N802
                text = url.toString() if url is not None else ""
                scheme = ((url.scheme() or "") if url is not None else "").lower()
                if scheme == "iris-scroll" or text.startswith("iris-scroll:"):
                    # iris-scroll://y/max — body scroll bridge (not a chat anchor).
                    y, max_y = 0, 0
                    try:
                        host_part = ""
                        if url is not None:
                            host_part = (url.authority() or url.host() or "").strip()
                            path = (url.path() or "").strip("/")
                            if host_part and path:
                                host_part = f"{host_part}/{path}"
                            elif path and not host_part:
                                host_part = path
                        if not host_part and "://" in text:
                            host_part = text.split("://", 1)[1]
                        bits = [p for p in host_part.replace("\\", "/").split("/") if p]
                        if bits:
                            y = int(float(bits[0]))
                        if len(bits) >= 2:
                            max_y = int(float(bits[1]))
                    except (TypeError, ValueError):
                        y, max_y = 0, 0
                    host._on_body_scroll_notify(y, max_y)
                    return False
                if text.startswith("iris-diagram://"):
                    from iris.ui.chat.diagram_card import parse_diagram_href

                    path = parse_diagram_href(text)
                    if path:
                        host.diagram_open_requested.emit(path)
                    return False
                if text.startswith("iris-tts://"):
                    token = text.removeprefix("iris-tts://").strip()
                    if token:
                        host.speaker_clicked.emit(token)
                    return False
                if text.startswith("iris-agent-update://"):
                    action = text.removeprefix("iris-agent-update://").strip().lower()
                    if action in ("apply", "later"):
                        host.iris_agent_update_action_clicked.emit(action)
                    return False
                if text.startswith("iris-update://"):
                    action = text.removeprefix("iris-update://").strip().lower()
                    if action in ("apply", "later"):
                        host.update_action_clicked.emit(action)
                    return False
                if "iris-ollama-login" in text:
                    host.ollama_login_clicked.emit()
                    return False
                if text.startswith(
                    ("iris-run://", "iris-always://", "iris-skip://", "iris-mode://")
                ):
                    host.shell_approval_clicked.emit(text)
                    return False
                return super().acceptNavigationRequest(url, nav_type, is_main_frame)

        view = QWebEngineView(self)
        view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        view.setStyleSheet("background: transparent;")
        page = _TranscriptPage(view)
        page.setBackgroundColor(QColor(0, 0, 0, 0))
        view.setPage(page)
        layout = self.layout()
        assert layout is not None
        layout.replaceWidget(self._slot, view)
        self._slot.hide()
        self._slot.deleteLater()
        self._slot = None
        self._view = view
        self._page_ready = False
        view.setZoomFactor(self._PAGE_ZOOM)
        view.installEventFilter(self)
        view.loadFinished.connect(self._on_page_load_finished)
        return view

    def _on_page_load_finished(self, ok: bool) -> None:
        """First successful setHtml paint; later lands patch #transcript via JS.

        Ignore failed loadFinished — iris-scroll:// clicks (and other aborted
        navigations) must not clear _page_ready or the next land uses setHtml
        and yanks scroll.
        """
        if not ok:
            return
        self._page_ready = True
        self.reset_page_zoom()

    def _transcript_inner_html(self) -> str:
        self._code_seq = 0
        return "\n".join(self._turn_html(turn) for turn in self._turns)

    def _patch_transcript_dom(self, view) -> None:
        """Replace #transcript only — keeps page scripts (__irisPartStream, cards).

        Mute iris-scroll notify and restore body.scrollTop so a full innerHTML
        land does not yank the viewport or look like a user scroll to hold/follow.
        """
        inner = self._transcript_inner_html()
        script = (
            "(function(){"
            "var t=document.getElementById('transcript');"
            "if(!t)return false;"
            "var b=document.body;"
            "var y=0,max=0,follow=false;"
            "if(b){"
            "b.__irisScrollMute=true;"
            "y=Math.round(b.scrollTop||0);"
            "max=Math.max(0,(b.scrollHeight||0)-(b.clientHeight||0));"
            "follow=y>=Math.max(0,max-2);"
            "}"
            f"t.innerHTML={json.dumps(inner)};"
            "if(!window.__irisPartStream){"
            f"{_PART_STREAM_JS}"
            "}"
            f"{_SCROLL_BRIDGE_JS}"
            "if(b){"
            "void t.offsetHeight;"
            "var max2=Math.max(0,(b.scrollHeight||0)-(b.clientHeight||0));"
            "b.scrollTop=follow?max2:Math.min(y,max2);"
            "b.classList.toggle('is-scrolled',(b.scrollTop||0)>0);"
            "requestAnimationFrame(function(){b.__irisScrollMute=false;});"
            "}"
            "return true;"
            "})();"
        )
        view.page().runJavaScript(script)

    def _render(self) -> None:
        """Paint DOM when WebEngine is available; otherwise keep turns in memory.

        First paint uses setHtml once. After loadFinished, lands update via
        runJavaScript so transparent WebEngine does not blank/flicker.
        """
        if self._view is None and not _webengine_import_safe():
            return
        view = self._ensure_view()
        if self._page_ready:
            self._patch_transcript_dom(view)
            return
        view.setHtml(self._page_html(), QUrl("about:blank"))

    def _page_html(self) -> str:
        body = self._transcript_inner_html()
        return (
            "<!DOCTYPE html><html lang=\"ko\"><head><meta charset=\"utf-8\">"
            f"<style>{_page_css()}</style></head><body>"
            f'<div id="transcript">{body}</div>'
            f"<script>{CODE_CARD_JS}</script>"
            f"<script>{WRITING_CARD_JS}</script>"
            f"<script>{_PART_STREAM_JS}</script>"
            f"<script>{_SCROLL_BRIDGE_JS}</script>"
            "</body></html>"
        )

    def set_speaker_status(self, msg_id: str, label: str) -> None:
        """Update [재생] link label on the H1 page (idle/busy/playing/error)."""
        mid = (msg_id or "").strip()
        if not mid or self._view is None:
            return
        script = (
            "(function(){"
            f"var mid={json.dumps(mid)};"
            f"var label={json.dumps(str(label or ''))};"
            "var links=document.querySelectorAll('a.tts-link[data-tts-id]');"
            "for(var i=0;i<links.length;i++){"
            "if((links[i].getAttribute('data-tts-id')||'')===mid){"
            "links[i].textContent=label;break;}}"
            "})();"
        )
        self._view.page().runJavaScript(script)

    def _turn_html(self, turn: _Turn) -> str:
        role_raw = turn.role or "assistant"
        role = html.escape(role_raw)
        mid = html.escape(turn.msg_id)
        speaker, speaker_cls = _speaker_label(role_raw)
        label = (
            f'<b class="{speaker_cls}">{html.escape(speaker)}</b>: '
        )
        parts_html = "\n".join(
            self._part_html(part, msg_id=turn.msg_id, part_index=i)
            for i, part in enumerate(turn.parts)
        )
        if not parts_html:
            parts_html = '<p class="part-muted"></p>'
        tts = ""
        role_key = (turn.role or "").strip().lower()
        mid_raw = turn.msg_id.strip()
        # notice-* system rows are not chat answers — skip [재생]/TTS.
        if (
            role_key in ("assistant", "iris")
            and mid_raw
            and not mid_raw.startswith("notice-")
        ):
            href = html.escape(f"iris-tts://{turn.msg_id}", quote=True)
            tts = (
                f'<p class="tts-row"><a class="tts-link" href="{href}" '
                f'data-tts-id="{mid}">[재생]</a></p>'
            )
        # Legacy ChatLog: You: sits inline before body; Iris keeps role above.
        if role_key in ("user", "you"):
            body = (
                f'<div class="turn-body">'
                f'<span class="role">{label}</span>'
                f"{parts_html}"
                f"</div>"
            )
            return (
                f'<article class="turn" data-role="{role}" data-msg-id="{mid}">'
                f"{body}"
                "</article>"
            )
        body = f'<div class="turn-body">{parts_html}</div>'
        return (
            f'<article class="turn" data-role="{role}" data-msg-id="{mid}">'
            f'<div class="role">{label}</div>'
            f"{body}"
            f"{tts}"
            "</article>"
        )

    def _part_html(
        self,
        part: MessagePart,
        *,
        msg_id: str = "",
        part_index: int = 0,
    ) -> str:
        if isinstance(part, TextPart):
            source, chips = _swap_local_attachments(part.markdown or "")
            rendered = render_markdown_document(source, citations=False)
            for index, chip in enumerate(chips):
                rendered = rendered.replace(_ATTACH_TOKEN.format(index), chip)
            if not rendered.strip():
                return ""
            return f'<div class="md">{rendered}</div>'
        if isinstance(part, CodePart):
            if (part.language or "").strip().lower() == "matrix":
                return (
                    '<div class="md">'
                    + matrix_grid_to_html(parse_matrix_grid(part.source or ""))
                    + "</div>"
                )
            self._code_seq += 1
            pane_id = f"codepane-{self._code_seq}"
            return render_code_part_html(
                part,
                pane_id=pane_id,
                msg_id=msg_id,
                part_index=part_index,
            )
        if isinstance(part, WritingPart):
            return render_writing_part_html(
                part, msg_id=msg_id, part_index=part_index
            )
        if isinstance(part, ExecutionPart):
            return render_execution_part_html(part)
        if isinstance(part, ToolShellPart):
            block = ToolShellBlock(
                title=part.title or "Shell",
                command=part.command or "",
                output=part.output or "",
                status=part.status or "ok",
                block_id=part.block_id or "tool",
                collapsed=bool(part.collapsed),
                phase=(part.phase or "done").strip() or "done",
            )
            return marked_tool_shell_to_html(block)
        if isinstance(part, ImagePart):
            return render_image_part_html(part)
        if isinstance(part, AppPart):
            try:
                return render_app_part_html(part)
            except ValueError:
                prose = parts_display_md([part])
                return f'<div class="part-muted">{html.escape(prose)}</div>'
        if isinstance(part, DiagramPart):
            return render_diagram_part_html(part)
        prose = parts_display_md([part])
        return f'<div class="part-muted">{html.escape(prose)}</div>'
