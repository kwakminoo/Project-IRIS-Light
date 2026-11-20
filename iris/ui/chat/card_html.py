"""Chat card painters. View models in, Qt rich-text HTML out."""

from __future__ import annotations

import base64
import html
from urllib.parse import quote

from iris.ui.chat.card_models import CodeCardModel, ShellCardModel
from iris.ui.chat.chat_syntax import highlight_code
from iris.ui.chat.typography import TOKENS


def _title_path(open_path: str, primary: str, end_line: int | None) -> str:
    shown = (open_path or primary or "").strip()
    if end_line is None or not shown:
        return shown
    path, sep, start = shown.rpartition(":")
    if not sep or not start.isdigit() or int(start) == end_line:
        return shown
    return f"{path}:{start}-{end_line}"


def _apply_footer(open_path: str, body: str = "") -> str:
    path = (open_path or "").strip().replace("\\", "/")
    if not path:
        return ""
    t = TOKENS
    href_raw = f"iris-apply://{quote(path, safe='')}"
    if body:
        payload = base64.urlsafe_b64encode(body.encode("utf-8")).decode("ascii")
        href_raw = f"{href_raw}?{payload}"
    href = html.escape(href_raw, quote=True)
    return (
        f'<tr><td colspan="2" style="padding:7px 16px;font-family:{t.chat_ui_font};'
        f'font-size:{t.font_size_micro};text-align:right;">'
        f'<a href="{href}" style="color:{t.text_muted};text-decoration:none;">Apply</a>'
        f"</td></tr>"
    )


def _pending_shell_footer(block_key: str) -> str:
    t = TOKENS
    bid = html.escape(block_key, quote=True)
    links = "".join(
        f'<a href="{scheme}{bid}" style="color:{t.text_muted};text-decoration:none;'
        f'font-size:{t.font_size_micro};font-weight:600;margin-right:8px;">{label}</a>'
        for scheme, label in (
            ("iris-run://", "Run"),
            ("iris-always://", "Always Run"),
            ("iris-skip://", "Skip"),
            ("iris-mode://", "▼"),
        )
    )
    return (
        f'<span style="display:block;padding:6px 10px;'
        f'border-top:1px solid {t.chat_block_border};">{links}</span>'
    )


def code_card_to_html(card: CodeCardModel) -> str:
    # Anchors stay in chat_blocks. Import here so that module can import this one.
    from iris.ui.chat.chat_blocks import copy_anchor_for, file_anchor_for

    t = TOKENS
    highlighted = highlight_code(card.body or "", card.lang_id or "")
    code = highlighted if highlighted is not None else html.escape(card.body or "")
    primary = (card.header_primary or "").strip()
    secondary = (card.header_secondary or "").strip()
    open_path = (card.open_path or "").strip().replace("\\", "/")

    if primary or open_path:
        visible = primary or open_path.rsplit("/", 1)[-1]
        title_attr = html.escape(
            _title_path(open_path, primary, card.end_line),
            quote=True,
        )
        name = html.escape(visible)
        if secondary:
            left_cell = (
                f'<span style="color:{t.text_primary};" title="{title_attr}">{name}</span>'
                f'<span style="color:{t.text_muted};letter-spacing:0.3px;">'
                f" · {html.escape(secondary)}</span>"
            )
        else:
            left_cell = (
                f'<span style="color:{t.text_primary};" title="{title_attr}">{name}</span>'
            )
        open_href = html.escape(file_anchor_for(open_path or primary), quote=True)
        open_link = (
            f'<a href="{open_href}" style="color:{t.text_muted};text-decoration:none;'
            f'margin-right:10px;">열기</a>'
        )
    else:
        left_cell = (
            f'<span style="color:{t.text_muted};letter-spacing:0.3px;">'
            f"{html.escape(secondary)}</span>"
            if secondary
            else "&nbsp;"
        )
        open_link = ""

    copy_href = html.escape(copy_anchor_for(card.copy_payload or ""), quote=True)
    apply_row = _apply_footer(open_path, card.body or "")
    # Qt rich text paints padding and border-bottom on table cells only.
    return (
        f'<table width="100%" cellspacing="0" cellpadding="0" '
        f'style="width:100%;background-color:{t.chat_block_bg};margin:6px 0;">'
        f"<tr>"
        f'<td style="padding:7px 16px;font-family:{t.chat_ui_font};'
        f'font-size:{t.font_size_micro};border-bottom:1px solid {t.chat_block_border_solid};">'
        f"{left_cell}</td>"
        f'<td width="1" style="padding:7px 16px;font-family:{t.chat_ui_font};'
        f"font-size:{t.font_size_micro};white-space:nowrap;text-align:right;"
        f'border-bottom:1px solid {t.chat_block_border_solid};">'
        f"{open_link}"
        f'<a href="{copy_href}" style="color:{t.text_muted};text-decoration:none;">복사</a>'
        f"</td>"
        f"</tr>"
        f'<tr><td colspan="2" style="padding:12px 16px;white-space:pre-wrap;">'
        f'<code style="font-family:{t.chat_block_mono_font};'
        f"font-weight:{t.chat_block_code_weight};font-size:{t.font_size_caption};"
        f'line-height:{t.chat_block_line_height};color:{t.text_primary};">{code}</code>'
        f"</td></tr>"
        f"{apply_row}"
        f"</table>"
    )


def shell_card_to_html(card: ShellCardModel) -> str:
    # Anchors stay in chat_blocks. Import here so that module can import this one.
    from iris.ui.chat.chat_blocks import collapse_anchor_for, copy_anchor_for

    t = TOKENS
    ok = card.status_kind == "ok"
    border_color = t.chat_block_border if ok else t.error
    status_color = t.success if ok else t.error
    title = html.escape(card.title or "Shell")
    command = html.escape(card.command or "")
    output = html.escape(card.output or "")
    block_key = (card.block_id or "tool").strip() or "tool"
    block_id = html.escape(block_key, quote=True)
    collapse_href = html.escape(collapse_anchor_for(block_key), quote=True)
    chevron = "▶" if card.collapsed else "▼"
    body_display = "none" if card.collapsed else "block"
    status_span = (
        f'<span style="color:{status_color};font-size:{t.font_size_micro};'
        f'font-weight:600;margin-right:8px;">{html.escape(card.status_label)}</span>'
    )
    copy_cmd = ""
    if card.show_command_copy:
        copy_href = html.escape(copy_anchor_for(card.copy_payload or ""), quote=True)
        copy_cmd = (
            f'<a href="{copy_href}" style="color:{t.text_muted};text-decoration:none;'
            f'font-size:{t.font_size_micro};font-weight:600;margin-right:8px;">명령 복사</a>'
        )
    header = (
        f'<span style="display:block;padding:6px 10px;font-weight:600;'
        f'border-bottom:1px solid {t.chat_block_border};">'
        f'<a href="{collapse_href}" style="text-decoration:none;color:{t.text_primary};">'
        f'<span style="color:{t.text_accent};font-family:{t.chat_block_mono_font};'
        f'font-weight:700;">&gt;_</span> {title}</a>'
        f'<span style="float:right;">'
        f"{status_span}{copy_cmd}"
        f'<a href="{collapse_href}" style="color:{t.text_muted};text-decoration:none;'
        f'font-size:{t.font_size_micro};font-weight:600;">{chevron}</a>'
        f"</span></span>"
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
    footer = _pending_shell_footer(block_key) if card.phase == "pending" else ""
    return (
        f'<pre style="display:block;margin:6px 0;padding:0;white-space:pre-wrap;'
        f"background-color:{t.chat_block_bg};"
        f"border:1px solid {border_color};"
        f"border-radius:{t.chat_block_radius}px;"
        f'color:{t.text_primary};">'
        f"{header}{body}{footer}</pre>"
    )
