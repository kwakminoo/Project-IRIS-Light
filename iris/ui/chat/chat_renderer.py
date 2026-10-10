"""채팅 단일 렌더 API — prose / code / tool / error / citation."""

from __future__ import annotations

import html
import re

from iris.ui.chat.chat_blocks import (
    ToolShellBlock,
    diff_block_to_html,
    error_block_to_html,
    file_chip_to_html,
    marked_tool_shell_to_html,
    parse_file_chip_location,
    wrap_document_html,
)
from iris.ui.chat.typography import TOKENS, manager

_MARKDOWN_EXTENSIONS = ("nl2br", "fenced_code", "tables", "sane_lists")

_FENCED_PRE = re.compile(
    r"<pre(?:\s[^>]*)?>\s*<code(?:\s+class=\"language-([^\"]*)\")?[^>]*>([\s\S]*?)</code>\s*</pre>",
    re.IGNORECASE,
)

_IMG_TAG = re.compile(
    r"<img\b([^>]*?)(?:\s*/\s*>|>\s*</img\s*>|>)",
    re.IGNORECASE | re.DOTALL,
)
_IMG_SRC = re.compile(r"""\bsrc\s*=\s*(['"])(.*?)\1""", re.IGNORECASE)
_IMG_ALT = re.compile(r"""\balt\s*=\s*(['"])(.*?)\1""", re.IGNORECASE)

_FILE_EXT = (
    r"(?:py|ts|tsx|js|jsx|md|json|yaml|yml|toml|css|html|htm|rs|go|java|kt|"
    r"cpp|h|c|cs|sql|sh|ps1|bat|txt|ini|cfg|xml|vue|svelte|rb|php|swift|"
    r"gradle|kts|lock|env|ico|svg|png|jpg|jpeg|gif|webp|woff2?|ttf|spec)"
)
_BACKTICK_FILE_PATH = re.compile(
    rf"`((?:[\w.-]+/)+[\w.-]+\.{_FILE_EXT}(?:\:\d+(?:\:\d+)?)?)`",
    re.IGNORECASE,
)
_BARE_FILE_PATH = re.compile(
    rf"(?<![`#/\w])(?<!://)"
    rf"((?:[\w.-]+/)+[\w.-]+\.{_FILE_EXT}(?:\:\d+(?:\:\d+)?)?)"
    rf"(?![/\w.])",
    re.IGNORECASE,
)
_AT_PATH_REF = re.compile(
    r"(?<![`\w./-])@((?:[\w.-]+/)+[\w.-]+(?:\:\d+(?:\:\d+)?)?)\b",
    re.IGNORECASE,
)
_INLINE_CODE_TAG = re.compile(
    r"<code(?![^>]*style=)[^>]*>([^<]+)</code>",
    re.IGNORECASE,
)
_FENCE = "```"

_TABLE_CELL_OPEN = re.compile(r"<(th|td)(\s[^>]*)?>", re.IGNORECASE)
_STYLE_ATTR = re.compile(r'style\s*=\s*"([^"]*)"', re.IGNORECASE)
_BARE_INLINE_CODE = re.compile(r"<code>([^<]*)</code>")
# Qt Rich Text는 인라인 요소의 padding을 렌더링하지 않으므로(실측 확인) 배경이
# 글자에 바싹 붙어 보이지 않도록 얇은 공백(hair space)을 양옆에 넣는다.
_INLINE_CODE_PAD = " "


def render_markdown_document(text: str, *, citations: bool = True) -> str:
    """Markdown → QTextEdit용 HTML (Iris 답변은 citations=True)."""
    t = (text or "").strip()
    if not t:
        return ""

    sources: list[tuple[str, str]] = []
    if citations:
        from iris.core.chat_citations import collect_and_tokenize_citations

        t, sources = collect_and_tokenize_citations(t)

    rendered = _markdown_body_to_html(t)
    if citations and sources:
        from iris.core.chat_citations import tokens_to_chips_html

        rendered = tokens_to_chips_html(rendered, sources)
    return rendered


def render_iris_message(text: str) -> str:
    """Iris 답변 — citations + markdown + code cards."""
    return render_markdown_document(text, citations=True)


def render_wiki_document(text: str) -> str:
    """Wiki 노트 — citations + markdown + code cards (TTS·타이핑 제외)."""
    return render_markdown_document(text, citations=True)


_ATTACH_TOKEN = "\ue010{}\ue011"
_LOCAL_ATTACH = re.compile(
    r'@"([^"]+)"'
    r"|@'([^']+)'"
    r"|@([A-Za-z]:[\\/][^\s<>]+)"
    r"|`([A-Za-z]:[\\/][^`\n]+)`"
    r"|`(\\\\[^`\n]+)`"
)


def _swap_attachment_prose(text: str, chips: list[str]) -> str:
    from iris.ui.chat.composer_attachments import attachment_chip_html

    def repl(match: re.Match[str]) -> str:
        raw = next(group for group in match.groups() if group)
        chips.append(attachment_chip_html(raw))
        return _ATTACH_TOKEN.format(len(chips) - 1)

    return _LOCAL_ATTACH.sub(repl, text)


def _swap_local_attachments(text: str) -> tuple[str, list[str]]:
    """절대경로·백틱 경로는 칩 토큰으로. 코드 펜스 안은 그대로."""
    chips: list[str] = []
    parts: list[str] = []
    pos = 0
    source = text or ""
    while pos < len(source):
        fence = source.find(_FENCE, pos)
        if fence < 0:
            parts.append(_swap_attachment_prose(source[pos:], chips))
            break
        if fence > pos:
            parts.append(_swap_attachment_prose(source[pos:fence], chips))
        close = source.find(_FENCE, fence + 3)
        if close < 0:
            parts.append(source[fence:])
            break
        parts.append(source[fence : close + 3])
        pos = close + 3
    return "".join(parts), chips


def render_user_message(text: str) -> str:
    """사용자 메시지 — markdown. 이미지·영상은 미리보기, 그 외 첨부는 파일명 칩."""
    source, chips = _swap_local_attachments(text or "")
    rendered = render_markdown_document(source, citations=False)
    for index, chip in enumerate(chips):
        rendered = rendered.replace(_ATTACH_TOKEN.format(index), chip)
    # QTextDocument does not support rounded CSS bubbles. A quiet inset card
    # uses native paragraph margins instead of a dark, rectangular table.
    return (
        '<div style="margin-left:24px;margin-right:12px;">'
        f"{rendered}</div>"
    )


def render_error_inline(text: str) -> str:
    """짧은 오류 — 인라인 빨간 텍스트."""
    t = TOKENS
    body = html.escape(text or "").replace("\n", "<br>")
    return (
        f'<p style="color:{t.error};font-size:12px;margin:4px 0;">{body}</p>'
    )


def render_tool_shell(
    title: str,
    command: str,
    output: str,
    status: str,
    block_id: str = "",
    *,
    collapsed: bool = False,
) -> str:
    block = ToolShellBlock(
        title=title or "Shell",
        command=command or "",
        output=output or "",
        status=status or "ok",
        block_id=block_id or "tool",
        collapsed=collapsed,
    )
    return wrap_document_html(marked_tool_shell_to_html(block))


def render_error_message(text: str) -> str:
    return wrap_document_html(error_block_to_html(text or ""))


def render_file_chip(rel_path: str) -> str:
    """상대 경로 → iris-file:// 칩 (IDE 미연결 시 회색 비활성)."""
    return file_chip_to_html(rel_path or "", enabled=_ide_connected_for_file_chips())


def render_diff_block(diff_text: str) -> str:
    """git diff 텍스트 → green/red diff 카드."""
    return diff_block_to_html(diff_text or "")


def _ide_connected_for_file_chips() -> bool:
    try:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return False
        for widget in app.topLevelWidgets():
            getter = getattr(widget, "_get_bound_ide_session", None)
            if not callable(getter):
                continue
            session = getter(refresh=False)
            if session is None:
                continue
            if getattr(widget, "_ui_mode", "") != "ide_companion":
                continue
            if session.mode == "workspace" and (session.workspace_root or session.hwnd):
                return True
    except Exception:
        return False
    return False


def _looks_like_file_path(text: str) -> bool:
    raw = (text or "").strip()
    if not raw or "://" in raw:
        return False
    path_part, _, _ = parse_file_chip_location(raw.replace("\\", "/"))
    if "/" not in path_part:
        return False
    return bool(re.search(rf"\.{_FILE_EXT}(?:\:\d+(?:\:\d+)?)?$", path_part, re.IGNORECASE))


def _looks_like_git_diff(text: str) -> bool:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return False
    if lines[0].startswith("diff "):
        return True
    head = lines[:40]
    has_minus = any(ln.startswith("--- ") for ln in head)
    has_plus = any(ln.startswith("+++ ") for ln in head)
    has_hunk = any(ln.startswith("@@") for ln in head)
    has_delta = any(ln.startswith(("+", "-")) for ln in head)
    return has_minus and has_plus and has_hunk and has_delta


def _inject_file_chips_in_prose(prose: str) -> str:
    if not prose:
        return prose
    out = _AT_PATH_REF.sub(lambda m: render_file_chip(m.group(1)), prose)
    out = _BACKTICK_FILE_PATH.sub(lambda m: render_file_chip(m.group(1)), out)

    def _bare_repl(match: re.Match[str]) -> str:
        start = match.start()
        prefix = out[max(0, start - 16) : start]
        if re.search(r"://[^\s]*$", prefix):
            return match.group(0)
        return render_file_chip(match.group(1))

    return _BARE_FILE_PATH.sub(_bare_repl, out)


def _inject_file_chips_in_source(text: str) -> str:
    if not text:
        return text
    parts: list[str] = []
    pos = 0
    while pos < len(text):
        fence = text.find(_FENCE, pos)
        if fence < 0:
            parts.append(_inject_file_chips_in_prose(text[pos:]))
            break
        if fence > pos:
            parts.append(_inject_file_chips_in_prose(text[pos:fence]))
        close = text.find(_FENCE, fence + 3)
        if close < 0:
            parts.append(text[fence:])
            break
        parts.append(text[fence : close + 3])
        pos = close + 3
    return "".join(parts)


def _upgrade_inline_code_file_chips(html_body: str) -> str:
    def _repl(match: re.Match[str]) -> str:
        inner = html.unescape(match.group(1) or "")
        if not _looks_like_file_path(inner):
            return match.group(0)
        return render_file_chip(inner)

    return _INLINE_CODE_TAG.sub(_repl, html_body)


def _markdown_body_to_html(text: str) -> str:
    from iris.ui.chat.markdown_normalization import normalize_markdown_source
    from iris.ui.chat.math_latex import restore_chat_math, stash_chat_math

    # 수식은 기호 치환보다 먼저 걷어 낸다. 안 그러면 $\frac$가 평문으로 사라진다.
    source, formulas = stash_chat_math(normalize_markdown_source(text))
    source = _inject_file_chips_in_source(_normalize_prose_symbols(source))
    try:
        import markdown as md

        rendered = md.markdown(source, extensions=list(_MARKDOWN_EXTENSIONS))
    except ImportError:
        # Qt's built-in GitHub dialect also supports tables and fenced code.
        # A missing optional parser must not silently show Markdown as plain text.
        from PyQt6.QtGui import QTextDocument

        document = QTextDocument()
        document.setMarkdown(source, QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
        return restore_chat_math(document.toHtml(), formulas)

    rendered = _sanitize_chat_html(rendered)
    rendered = _upgrade_fenced_pre_to_cards(rendered)
    rendered = _upgrade_inline_code_file_chips(rendered)
    # 스타일 뒤에 넣어야 수식 이미지가 사진용 img 스타일로 바뀌지 않는다.
    return restore_chat_math(wrap_document_html(_style_chat_html(rendered)), formulas)


def _normalize_prose_symbols(text: str) -> str:
    """Show common math arrows in prose; preserve fenced and inline code."""
    symbols = {"rightarrow": "→", "leftarrow": "←", "leftrightarrow": "↔",
               "Rightarrow": "⇒", "Leftarrow": "⇐", "Leftrightarrow": "⇔",
               "times": "×", "cdot": "·", "leq": "≤", "geq": "≥", "neq": "≠"}
    chunks = re.split(r"(```[\s\S]*?(?:```|$)|~~~[\s\S]*?(?:~~~|$)|`[^`\n]*`)", text)
    for i in range(0, len(chunks), 2):
        chunks[i] = re.sub(r"\\(" + "|".join(symbols) + r")(?![A-Za-z])",
                           lambda m: symbols[m.group(1)], chunks[i])
        chunks[i] = re.sub(r"(?:\$|\\\()\s*([→←↔⇒⇐⇔])\s*(?:\$|\\\))", r"\1", chunks[i])
        def math_text(match: re.Match[str]) -> str:
            value = match[1]
            if not ("\\" in value or re.fullmatch(r"[\w=+*/().<>≤≥≠-]+", value)):
                return match[0]
            value = re.sub(r"\\text\{([^{}]+)\}", r"\1", value)
            return re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1) / (\2)", value)
        chunks[i] = re.sub(r"(?<!\\)\$([^$\n]+)(?<!\\)\$", math_text, chunks[i])
    return "".join(chunks)


def _upgrade_fenced_pre_to_cards(html_body: str) -> str:
    from iris.ui.chat.chat_blocks import FencedCodeBlock, fenced_code_to_html

    def _repl(match: re.Match[str]) -> str:
        lang = (match.group(1) or "").strip()
        code = html.unescape(match.group(2) or "")
        if lang.lower() == "diff" or _looks_like_git_diff(code):
            return diff_block_to_html(code)
        return fenced_code_to_html(FencedCodeBlock(code, language=lang))

    return _FENCED_PRE.sub(_repl, html_body)


def _plain_to_chat_html(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"^#{1,6}\s+(.+)$", r"<h3>\1</h3>", escaped, flags=re.MULTILINE)
    return "".join("<p>" + part.replace("\n", "<br>") + "</p>"
                   for part in escaped.split("\n\n") if part.strip())


_ALLOWED_CHAT_TAGS = frozenset(
    {
        "a", "b", "blockquote", "br", "code", "em", "h1", "h2", "h3", "h4", "h5", "h6",
        "hr", "i", "img", "li", "ol", "p", "pre", "span", "strong", "table", "tbody",
        "td", "th", "thead", "tr", "ul",
    }
)
_DROP_WITH_CONTENT = ("script", "style", "iframe", "object", "embed", "svg", "math", "form")
_ON_ATTR = re.compile(
    r"""\s+on[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""",
    re.IGNORECASE,
)
_URL_ATTR = re.compile(
    r"""(?P<name>href|src)\s*=\s*(?P<q>["'])(?P<val>.*?)(?P=q)""",
    re.IGNORECASE | re.DOTALL,
)
_STYLE_JS = re.compile(
    r"(?i)(?:url\s*\(\s*(['\"]?)\s*(?:javascript|vbscript|data|file):[^)]*\)|expression\s*\([^)]*\))"
)
_CHAT_TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>", re.DOTALL)
_ALLOWED_URL_PREFIXES = (
    "http://", "https://",
    "iris-file://", "iris-wiki://", "iris-copy://", "iris-collapse://",
    "iris-tts://", "iris-error://", "iris-update://", "iris-hermes-update://",
    "iris-stt://", "iris-diagram://", "iris-ollama-login://",
    "iris-image:",
)


def _chat_url_ok(value: str) -> bool:
    raw = html.unescape((value or "").strip())
    low = raw.lower()
    if low.startswith(("javascript:", "vbscript:", "data:", "file:")):
        return False
    if low.startswith(_ALLOWED_URL_PREFIXES):
        return True
    if re.match(r"^[a-z]:[\\/]", low):
        return True
    head = low.split("/", 1)[0]
    return ":" not in head


def _sanitize_chat_html(html_body: str) -> str:
    t = html_body or ""
    for name in _DROP_WITH_CONTENT:
        t = re.sub(rf"(?is)<{name}\b[\s\S]*?</{name}>", "", t)
        t = re.sub(rf"(?is)<{name}\b[^>]*?/?>", "", t)

    def _tag(match: re.Match[str]) -> str:
        closing, name, attrs = match.group(1), match.group(2).lower(), match.group(3) or ""
        if name not in _ALLOWED_CHAT_TAGS:
            return ""
        if closing:
            return f"</{name}>"
        attrs = _ON_ATTR.sub("", attrs)
        attrs = _STYLE_JS.sub("", attrs)

        def _url(url_match: re.Match[str]) -> str:
            if _chat_url_ok(url_match.group("val")):
                return url_match.group(0)
            return ""

        attrs = _URL_ATTR.sub(_url, attrs)
        return f"<{name}{attrs}>"

    return _CHAT_TAG.sub(_tag, t)


def _style_img_tag(attrs: str) -> str:
    from iris.core.markdown_text import iris_image_href

    sm = _IMG_SRC.search(attrs or "")
    src = (sm.group(2) if sm else "").strip()
    if not src or not _chat_url_ok(src):
        return ""
    am = _IMG_ALT.search(attrs or "")
    alt = html.escape((am.group(2) if am else "").strip(), quote=True)
    src_esc = html.escape(src, quote=True)
    href = html.escape(iris_image_href(src), quote=True)
    return (
        f'<a href="{href}" title="클릭하여 크게 보기">'
        f'<img src="{src_esc}" alt="{alt}" '
        f'style="max-width:420px;max-height:280px;border-radius:10px;'
        f'margin:8px 0;cursor:pointer;" /></a>'
    )


def _merge_cell_style(attrs: str, extra_style: str) -> str:
    """기존 style(정렬 등)을 보존하며 셀 스타일을 앞쪽에 병합 — 뒤 선언이 우선이므로
    markdown이 넣은 text-align 등은 그대로 유지된다."""
    attrs = attrs or ""
    m = _STYLE_ATTR.search(attrs)
    if m:
        existing = m.group(1).strip()
        if existing and not existing.endswith(";"):
            existing += ";"
        merged = f"{extra_style}{existing}"
        return _STYLE_ATTR.sub(f'style="{merged}"', attrs, count=1)
    return f' style="{extra_style}"{attrs}'


def _style_table_cell(match: re.Match[str]) -> str:
    t = TOKENS
    tag = match.group(1).lower()
    attrs = match.group(2) or ""
    if tag == "th":
        style = (
            f"background-color:{t.chat_table_header_bg};color:{t.text_primary};"
            f"font-weight:600;padding:8px 12px;border:none;"
            f"border-bottom:1px solid {t.chat_table_row_border};text-align:left;"
        )
    else:
        style = (
            f"color:{t.text_primary};padding:8px 12px;border:none;"
            f"border-bottom:1px solid {t.chat_table_row_border};text-align:left;"
        )
    style += f"font-family:{t.chat_ui_font};font-size:{t.chat_font_size};"
    return f"<{tag}{_merge_cell_style(attrs, style)}>"


def _style_tables(html_body: str) -> str:
    out = re.sub(
        r"<table>",
        '<table border="0" cellspacing="0" cellpadding="0" '
        'style="border-collapse:collapse;width:100%;margin:6px 0 10px 0;">',
        html_body,
        flags=re.IGNORECASE,
    )
    out = _TABLE_CELL_OPEN.sub(_style_table_cell, out)
    return out


def _style_chat_html(html_body: str) -> str:
    t = TOKENS
    body = f"color:{t.chat_body};line-height:{t.chat_line_height};font-size:{t.chat_font_size};font-family:{t.chat_ui_font};"
    shell = (
        f"background-color:{t.chat_block_bg};"
        f"border:1px solid {t.chat_block_border};"
        f"border-radius:{t.chat_block_radius}px;"
        f"padding:8px;margin:4px 0;white-space:pre-wrap;{body}"
    )
    out = html_body
    out = re.sub(
        r"<p>",
        f'<p style="margin-top:0;margin-bottom:14px;{body}">',
        out,
    )
    out = re.sub(
        r"<hr\s*/?>",
        f'<hr style="border:none;border-top:1px solid {t.text_muted};margin:8px 0;height:0;" />',
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(r"<pre>", f'<pre style="{shell}">', out)
    out = _BARE_INLINE_CODE.sub(
        lambda m: (
            f'<code style="display:inline;color:{t.chat_inline_code_color};'
            f"background-color:{t.chat_inline_code_bg};font-family:{t.chat_block_mono_font};"
            f"font-weight:{t.chat_block_code_weight};font-size:{t.font_size_caption};"
            f'border-radius:4px;">{_INLINE_CODE_PAD}{m.group(1)}{_INLINE_CODE_PAD}</code>'
        ),
        out,
    )
    out = _style_tables(out)
    out = re.sub(r"<h([1-6])>", lambda m: (
        f'<h{m[1]} style="color:{t.text_primary};font-family:{t.chat_ui_font};font-size:{manager.get().chat_font_size + (4,3,2,2,1,1)[int(m[1])-1]}px;'
        'font-weight:600;margin-top:20px;margin-bottom:10px;">'
        f'<span style="font-size:{manager.get().chat_font_size + (4,3,2,2,1,1)[int(m[1])-1]}px;">'), out)
    out = re.sub(r"</h([1-6])>", r"</span></h\1>", out)
    out = re.sub(r"<(ul|ol)>", r'<\1 style="margin-top:4px;margin-bottom:16px;margin-left:20px;">', out)
    out = out.replace("<li>", f'<li style="margin-bottom:8px;{body}">')
    out = out.replace("<blockquote>",
        f'<blockquote style="margin-left:18px;margin-right:12px;margin-top:12px;'
        f'margin-bottom:16px;color:{t.text_secondary};">')
    out = out.replace("<strong>", f'<strong style="font-weight:600;color:{t.text_primary};">')
    out = re.sub(
        r'<a(?![^>]*\bstyle=)(?=[^>]*href="(?!iris-(?!wiki://)))',
        '<a style="color:#60a5fa;" ',
        out,
    )
    out = _IMG_TAG.sub(lambda m: _style_img_tag(m.group(1)), out)
    return out


if __name__ == "__main__":
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])
    chip = render_file_chip("src/app/main.py")
    assert "src/app/main.py" in chip
    assert "iris-file://" in chip or "#475569" in chip
    diff = render_diff_block("--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n")
    assert "#34d399" in diff and "#f87171" in diff
    md = render_iris_message("edit `iris/ui/chat/chat_renderer.py` then see iris/ui/chat/chat_blocks.py")
    assert "iris-file://" in md or "#475569" in md
    fenced = render_iris_message(
        "```diff\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n```"
    )
    assert "#34d399" in fenced and "#f87171" in fenced
    dirty = render_iris_message(
        '안녕 <script>alert(1)</script> [x](javascript:alert(1))\n\n'
        '![a](javascript:alert(1))\n\n'
        "See [Docs](https://example.com/a)"
    )
    lowered = dirty.lower()
    assert "<script" not in lowered and "javascript:" not in lowered, dirty
    assert "https://example.com/a" in dirty
    print("chat_renderer file/diff ok")
