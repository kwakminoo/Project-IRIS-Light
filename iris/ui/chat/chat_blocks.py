"""채팅 출력 블록 — Cursor식 prose / code / tool / citation HTML."""

from __future__ import annotations

import base64
import html
import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from iris.ui.shared.theme_tokens import TOKENS

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QTextEdit

_IRIS_TOOL_MARKER_STYLE = (
    "font-size:0;line-height:0;max-height:0;overflow:hidden;color:transparent;"
)


class ChatBlockKind(Enum):
    PROSE = "prose"
    INLINE_CODE = "inline_code"
    FENCED_CODE = "fenced_code"
    DIFF = "diff"
    TOOL_SHELL = "tool_shell"
    TOOL_FILE = "tool_file"
    FILE_CHIP = "file_chip"
    ERROR = "error"
    CITATION_CHIP = "citation_chip"


@dataclass(frozen=True)
class ProseBlock:
    html: str


@dataclass(frozen=True)
class FencedCodeBlock:
    code: str
    language: str = ""


@dataclass(frozen=True)
class ToolShellBlock:
    title: str
    command: str
    output: str
    status: str = "ok"
    block_id: str = ""
    collapsed: bool = False


def tool_block_markers(block_id: str) -> tuple[str, str]:
    bid = (block_id or "tool").strip() or "tool"
    return f"IRIS_TOOL_{bid}_START", f"IRIS_TOOL_{bid}_END"


def collapse_anchor_for(block_id: str) -> str:
    return f"iris-collapse://{(block_id or 'tool').strip() or 'tool'}"


def copy_anchor_for(code: str) -> str:
    payload = base64.urlsafe_b64encode((code or "").encode("utf-8")).decode("ascii")
    return f"iris-copy://{payload}"


def parse_copy_anchor(anchor: str) -> str | None:
    raw = (anchor or "").strip()
    if not raw.startswith("iris-copy://"):
        return None
    try:
        return base64.urlsafe_b64decode(raw.removeprefix("iris-copy://").encode("ascii")).decode(
            "utf-8"
        )
    except Exception:
        return None


def parse_collapse_block_id(anchor: str) -> str | None:
    raw = (anchor or "").strip()
    if not raw.startswith("iris-collapse://"):
        return None
    bid = raw.removeprefix("iris-collapse://").strip()
    return bid or None


IRIS_FILE_SCHEME = "iris-file://"

_FILE_LOC = re.compile(r"^(.*?)(?::(\d+)(?::(\d+))?)?$")


def file_anchor_for(rel_path: str) -> str:
    from urllib.parse import quote

    rel = (rel_path or "").strip().replace("\\", "/")
    return f"{IRIS_FILE_SCHEME}{quote(rel, safe='/:@')}"


def parse_iris_file_anchor(anchor: str) -> str | None:
    raw = (anchor or "").strip()
    if not raw.startswith(IRIS_FILE_SCHEME):
        return None
    from urllib.parse import unquote

    return unquote(raw[len(IRIS_FILE_SCHEME) :]) or None


def parse_file_chip_location(raw_path: str) -> tuple[str, int, int]:
    s = (raw_path or "").strip().replace("\\", "/")
    if not s:
        return "", 1, 1
    m = _FILE_LOC.match(s)
    if not m:
        return s, 1, 1
    path = (m.group(1) or "").strip()
    line = max(1, int(m.group(2) or 1))
    column = max(1, int(m.group(3) or 1))
    return path, line, column


def file_chip_to_html(rel_path: str, *, enabled: bool = True) -> str:
    t = TOKENS
    label = html.escape((rel_path or "").strip().replace("\\", "/"))
    mono = f"font-family:{t.chat_block_mono_font};"
    base = (
        f"display:inline;font-size:{t.font_size_micro};font-weight:600;"
        f"padding:1px 7px;margin:0 1px;border-radius:7px;{mono}"
    )
    if enabled:
        href = html.escape(file_anchor_for(rel_path or ""), quote=True)
        return (
            f'<a href="{href}" title="IDE에서 열기" '
            f'style="{base}'
            f"background-color:rgba(56,189,248,0.14);color:#7dd3fc;"
            f"text-decoration:none;border:1px solid rgba(56,189,248,0.38);"
            f'cursor:pointer;">{label}</a>'
        )
    return (
        f'<span title="IDE 미연결" '
        f'style="{base}'
        f"background-color:rgba(71,85,105,0.18);color:{t.disabled};"
        f'border:1px solid rgba(100,116,139,0.28);cursor:default;">'
        f"{label}</span>"
    )


def diff_block_to_html(diff_text: str) -> str:
    t = TOKENS
    lines = (diff_text or "").splitlines()
    rows: list[str] = []
    for line in lines:
        if line.startswith("+"):
            fg = t.success
            bg = "rgba(52,211,153,0.12)"
        elif line.startswith("-"):
            fg = t.error
            bg = "rgba(248,113,113,0.12)"
        elif line.startswith("@@"):
            fg = t.text_accent
            bg = "rgba(56,189,248,0.08)"
        elif line.startswith(("diff ", "--- ", "+++ ", "index ")):
            fg = t.text_muted
            bg = "transparent"
        else:
            fg = t.text_secondary
            bg = "transparent"
        esc = html.escape(line)
        rows.append(
            f'<span style="display:block;background:{bg};color:{fg};">{esc}</span>'
        )
    body = "".join(rows) if rows else f'<span style="color:{t.text_muted};">&nbsp;</span>'
    return (
        f'<pre style="display:block;margin:4px 0;padding:0;white-space:pre-wrap;'
        f'{_shell_style(mono=True)}color:{t.text_primary};">'
        f'<span style="display:block;padding:4px 10px;'
        f'border-bottom:1px solid {t.chat_block_border};'
        f'color:{t.text_muted};font-size:{t.font_size_micro};">diff</span>'
        f'<code style="display:block;padding:8px 10px;font-family:{t.chat_block_mono_font};'
        f'font-size:{t.font_size_caption};">{body}</code></pre>'
    )


def _shell_style(*, mono: bool = False) -> str:
    t = TOKENS
    bits = [
        f"background-color:{t.chat_block_bg};",
        f"border:1px solid {t.chat_block_border};",
        f"border-radius:{t.chat_block_radius}px;",
    ]
    if mono:
        bits.append(f"font-family:{t.chat_block_mono_font};")
    return "".join(bits)


def wrap_document_html(inner: str) -> str:
    """공통 body 색·line-height."""
    t = TOKENS
    return (
        f'<span style="color:{t.text_primary};'
        f'line-height:1.45;font-size:{t.font_size_body};">'
        f"{inner}</span>"
    )


def inline_code_to_html(text: str) -> str:
    esc = html.escape(text or "")
    return f'<code style="color:#a5b4fc;">{esc}</code>'


def fenced_code_to_html(block: FencedCodeBlock) -> str:
    t = TOKENS
    lang = html.escape((block.language or "").strip(), quote=True)
    code = html.escape(block.code or "")
    lang_label = (
        f'<span style="color:{t.text_muted};font-size:{t.font_size_micro};'
        f'letter-spacing:0.3px;">{lang}</span>'
        if lang
        else ""
    )
    copy_href = html.escape(copy_anchor_for(block.code or ""), quote=True)
    copy_link = (
        f'<a href="{copy_href}" style="float:right;color:{t.text_accent};'
        f'font-size:{t.font_size_micro};text-decoration:none;">복사</a>'
    )
    header = (
        f'<span style="display:block;padding:4px 10px;'
        f'border-bottom:1px solid {t.chat_block_border};">'
        f"{lang_label}{copy_link}</span>"
    )
    return (
        f'<pre style="display:block;margin:4px 0;padding:0;white-space:pre-wrap;'
        f'{_shell_style(mono=True)}color:{t.text_primary};">'
        f'{header}'
        f'<code style="display:block;padding:8px 10px;font-family:{t.chat_block_mono_font};'
        f'font-size:{t.font_size_caption};">{code}</code></pre>'
    )


def tool_shell_to_html(block: ToolShellBlock) -> str:
    t = TOKENS
    status = (block.status or "ok").strip().lower()
    is_ok = status in ("ok", "success", "done")
    border_color = t.chat_block_border if is_ok else t.error
    title = html.escape(block.title or "Shell")
    command = html.escape(block.command or "")
    output = html.escape(block.output or "")
    block_id = html.escape((block.block_id or "tool").strip() or "tool", quote=True)
    collapse_href = html.escape(collapse_anchor_for(block.block_id or "tool"), quote=True)
    chevron = "▶" if block.collapsed else "▼"
    body_display = "none" if block.collapsed else "block"
    header = (
        f'<a href="{collapse_href}" style="display:block;padding:6px 10px;font-weight:600;'
        f"text-decoration:none;color:{t.text_primary};"
        f'border-bottom:1px solid {t.chat_block_border};">'
        f'<span style="color:{t.text_accent};font-family:{t.chat_block_mono_font};'
        f'font-weight:700;">&gt;_</span> {title}'
        f'<span style="float:right;color:{t.text_muted};font-size:{t.font_size_micro};'
        f'font-weight:600;">{chevron}</span></a>'
    )
    command_block = (
        f'<code style="display:block;padding:6px 10px 4px 10px;font-family:{t.chat_block_mono_font};'
        f'font-size:{t.font_size_caption};color:{t.text_accent};">{command}</code>'
        if command
        else ""
    )
    output_block = (
        f'<code style="display:block;padding:0 10px 8px 10px;font-family:{t.chat_block_mono_font};'
        f'font-size:{t.font_size_caption};color:{t.text_secondary};white-space:pre-wrap;">'
        f"{output}</code>"
        if output
        else ""
    )
    body = (
        f'<span style="display:{body_display};" data-iris-tool-body="{block_id}">'
        f"{command_block}{output_block}</span>"
    )
    return (
        f'<pre style="display:block;margin:6px 0;padding:0;white-space:pre-wrap;'
        f"background-color:{t.chat_block_bg};"
        f"border:1px solid {border_color};"
        f"border-radius:{t.chat_block_radius}px;"
        f'color:{t.text_primary};">'
        f"{header}{body}</pre>"
    )


def marked_tool_shell_to_html(block: ToolShellBlock) -> str:
    start, end = tool_block_markers(block.block_id or "tool")
    return (
        f'<span style="{_IRIS_TOOL_MARKER_STYLE}">{start}</span>'
        f"{tool_shell_to_html(block)}"
        f'<span style="{_IRIS_TOOL_MARKER_STYLE}">{end}</span>'
    )


def replace_marked_tool_block(html_doc: str, block_id: str, block: ToolShellBlock) -> str:
    start, end = tool_block_markers(block_id)
    pattern = rf"{re.escape(start)}[\s\S]*?{re.escape(end)}"
    replacement = marked_tool_shell_to_html(block)
    if not re.search(pattern, html_doc):
        return html_doc
    return re.sub(pattern, replacement, html_doc, count=1)


def handle_tool_collapse_click(
    text_edit: "QTextEdit",
    blocks: dict[str, ToolShellBlock],
    anchor: str,
) -> bool:
    block_id = parse_collapse_block_id(anchor)
    if not block_id:
        return False
    block = blocks.get(block_id)
    if block is None:
        return False
    toggled = replace(block, collapsed=not block.collapsed)
    blocks[block_id] = toggled
    html_doc = text_edit.toHtml()
    updated = replace_marked_tool_block(html_doc, block_id, toggled)
    if updated == html_doc:
        return False
    bar = text_edit.verticalScrollBar()
    pos = bar.value()
    text_edit.setHtml(updated)
    bar.setValue(pos)
    return True


def tool_file_to_html(path: str, *, status: str = "ok", snippet: str = "") -> str:
    t = TOKENS
    status_norm = (status or "ok").strip().lower()
    status_color = t.success if status_norm in ("ok", "success", "done") else t.error
    path_esc = html.escape(path or "")
    snippet_esc = html.escape(snippet or "")
    snippet_block = (
        f'<code style="display:block;padding:0 10px 8px 10px;font-family:{t.chat_block_mono_font};'
        f'font-size:{t.font_size_caption};color:{t.text_secondary};">{snippet_esc}</code>'
        if snippet_esc
        else ""
    )
    return (
        f'<pre style="display:block;margin:6px 0;padding:0;white-space:pre-wrap;'
        f'{_shell_style()}color:{t.text_primary};">'
        f'<span style="display:block;padding:6px 10px;font-weight:600;'
        f'border-bottom:1px solid {t.chat_block_border};">'
        f'File'
        f'<span style="float:right;color:{status_color};font-size:{t.font_size_micro};'
        f'font-weight:600;">{html.escape(status_norm)}</span></span>'
        f'<code style="display:block;padding:6px 10px;font-family:{t.chat_block_mono_font};'
        f'font-size:{t.font_size_caption};">{path_esc}</code>'
        f'{snippet_block}</pre>'
    )


def error_block_to_html(text: str) -> str:
    t = TOKENS
    body = html.escape(text or "").replace("\n", "<br>")
    return (
        f'<span style="display:block;margin:4px 0;padding:8px 10px;'
        f'background-color:rgba(248,113,113,0.10);'
        f'border:1px solid rgba(248,113,113,0.35);'
        f'border-radius:{t.chat_block_radius}px;color:{t.error};">{body}</span>'
    )


def _host_label(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return "source"
    if host.startswith("www."):
        host = host[4:]
    return host or "source"


def citation_chip_to_html(n: int, url: str, title: str) -> str:
    tip = html.escape(title or _host_label(url), quote=True)
    href = html.escape((url or "").strip(), quote=True)
    return (
        f'<a href="{href}" title="{tip}" '
        f'style="display:inline;font-size:10px;font-weight:600;'
        f"padding:1px 6px;margin:0 2px;border-radius:9px;"
        f"background-color:rgba(56,189,248,0.14);color:#7dd3fc;"
        f'text-decoration:none;border:1px solid rgba(56,189,248,0.40);'
        f'">[{n}]</a>'
    )


if __name__ == "__main__":
    on = file_chip_to_html("iris/ui/chat/chat_blocks.py", enabled=True)
    off = file_chip_to_html("iris/ui/chat/chat_blocks.py", enabled=False)
    assert "iris-file://" in on and "<a " in on
    assert "iris-file://" not in off and "<span " in off
    assert parse_iris_file_anchor(file_anchor_for("a/b.py:2:3")) == "a/b.py:2:3"
    path, line, col = parse_file_chip_location("src/main.py:10:4")
    assert path == "src/main.py" and line == 10 and col == 4
    diff = diff_block_to_html("--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n")
    assert "#34d399" in diff and "#f87171" in diff
    print("chat_blocks file/diff ok")
