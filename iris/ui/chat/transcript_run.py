"""H1 transcript Code Run → ExecutionPart + ImagePart landing (T7).

Bridge: page JS queue (``__irisCodeRunRequests``) like Writing Save (T4).
Exec: ``iris.runtime.chat_code_exec.run_chat_python`` only — not IDE project.run.
Images: data URL in the about:blank WebEngine page (file:// blocked).
"""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path
from typing import Any

from iris.core.message_parts import (
    ExecutionPart,
    ImagePart,
    MessagePart,
)
from iris.runtime.chat_code_exec import run_chat_python

_RUN_LANGS = frozenset({"python", "py"})

EXEC_CARD_CSS = """
.exec-card {
  margin: 0 0 0.85rem;
  padding: 12px;
  border: 1px solid #1f2937;
  border-radius: 10px;
  background: #020617;
}
.exec-card[data-ok="0"] {
  border-color: #7f1d1d;
}
.exec-card .exec-label {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #64748b;
  margin: 0 0 8px;
}
.exec-card .exec-out,
.exec-card .exec-err {
  margin: 0 0 6px;
  padding: 10px 12px;
  border-radius: 8px;
  background: #0b1220;
  color: #e2e8f0;
  font: 12px/1.45 ui-monospace, Consolas, monospace;
  white-space: pre-wrap;
  overflow-x: auto;
}
.exec-card .exec-err {
  color: #fca5a5;
  background: #1c0a0a;
}
.exec-card .exec-empty {
  margin: 0;
  color: #64748b;
  font-size: 0.9rem;
}
.image-card {
  margin: 0 0 0.85rem;
}
.image-card img {
  display: block;
  max-width: min(420px, 100%);
  max-height: 280px;
  border-radius: 10px;
  background: #020617;
}
.image-card .image-alt {
  margin: 6px 0 0;
  font-size: 12px;
  color: #94a3b8;
}
"""

DRAIN_CODE_RUN_REQUESTS_JS = """
(function() {
  var q = window.__irisCodeRunRequests || [];
  window.__irisCodeRunRequests = [];
  return JSON.stringify(q);
})()
"""


def code_run_supported(language: str) -> bool:
    return (language or "").strip().lower() in _RUN_LANGS


def parse_code_run_requests_raw(raw: Any) -> list[dict[str, Any]]:
    """Normalize drain JS result into run-request dicts."""
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
                "source": str(item.get("source") or ""),
                "language": str(item.get("language") or "python"),
            }
        )
    return out


def result_to_run_parts(
    result: dict[str, Any],
    *,
    language: str = "python",
) -> list[MessagePart]:
    """Map chat_code_exec dict to ExecutionPart + ImagePart list."""
    ok = bool(result.get("ok"))
    stdout = str(result.get("stdout") or "")
    stderr = str(result.get("stderr") or "")
    err = str(result.get("error") or "").strip()
    if err and err not in stderr:
        stderr = f"{stderr}\n{err}".strip() if stderr else err
    parts: list[MessagePart] = [
        ExecutionPart(
            stdout=stdout,
            stderr=stderr,
            ok=ok,
            language=(language or "python").strip() or "python",
        )
    ]
    for path in result.get("png_paths") or []:
        p = str(path or "").strip()
        if p:
            parts.append(ImagePart(alt="plot", path=p))
    return parts


def land_code_run_on_transcript(
    host: Any,
    source: str,
    *,
    language: str = "python",
    msg_id: str = "",
    timeout_s: float = 20.0,
) -> dict[str, Any]:
    """Run sandbox Python and append execution/image parts to the same turn.

    ``host`` must implement ``append_parts_to_turn(msg_id, parts)``.
    """
    result = run_chat_python(source or "", timeout_s=timeout_s)
    parts = result_to_run_parts(result, language=language)
    append = getattr(host, "append_parts_to_turn", None)
    if callable(append):
        append(str(msg_id or ""), parts)
    return {
        "ok": bool(result.get("ok")),
        "stdout": result.get("stdout") or "",
        "stderr": result.get("stderr") or "",
        "error": result.get("error") or "",
        "png_paths": list(result.get("png_paths") or []),
        "parts": parts,
    }


def _png_data_url(path: str) -> str:
    p = Path(path)
    if not p.is_file():
        return ""
    try:
        raw = p.read_bytes()
    except OSError:
        return ""
    if not raw:
        return ""
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{b64}"


def render_execution_part_html(part: ExecutionPart) -> str:
    status = "ok" if part.ok else "fail"
    lang = html.escape((part.language or "python").strip() or "python")
    out = (part.stdout or "").rstrip()
    err = (part.stderr or "").rstrip()
    body_bits: list[str] = []
    if out:
        body_bits.append(f'<pre class="exec-out">{html.escape(out)}</pre>')
    if err:
        body_bits.append(f'<pre class="exec-err">{html.escape(err)}</pre>')
    if not body_bits:
        body_bits.append('<p class="exec-empty">(no output)</p>')
    return (
        f'<section class="exec-card" data-part="execution" '
        f'data-ok="{"1" if part.ok else "0"}">'
        f'<div class="exec-label">execution · {lang} · {status}</div>'
        f"{''.join(body_bits)}"
        f"</section>"
    )


def render_image_part_html(part: ImagePart) -> str:
    alt = html.escape(part.alt or "plot")
    path = (part.path or "").strip()
    src = _png_data_url(path) if path else ""
    if not src:
        prose = html.escape(path or "(missing image)")
        return (
            f'<section class="image-card" data-part="image">'
            f'<p class="image-alt">{alt}: {prose}</p></section>'
        )
    src_esc = html.escape(src, quote=True)
    return (
        f'<section class="image-card" data-part="image">'
        f'<img src="{src_esc}" alt="{alt}" />'
        f'<p class="image-alt">{alt}</p></section>'
    )

