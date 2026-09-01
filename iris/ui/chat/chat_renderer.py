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
from iris.ui.shared.theme_tokens import TOKENS

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
    rf"(?<![`#/\\w])(?<!://)"
    rf"((?:[\w.-]+/)+[\w.-]+\.{_FILE_EXT}(?:\:\d+(?:\:\d+)?)?)"
    rf"(?![/\w.])",
    re.IGNORECASE,
)
_INLINE_CODE_TAG = re.compile(
    r"<code(?![^>]*style=)[^>]*>([^<]+)</code>",
    re.IGNORECASE,
)
_FENCE = "```"


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


def render_user_message(text: str) -> str:
    """사용자 메시지 — markdown (인용 칩 제외)."""
    return render_markdown_document(text, citations=False)


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
    out = _BACKTICK_FILE_PATH.sub(lambda m: render_file_chip(m.group(1)), prose)

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
    source = _inject_file_chips_in_source(text)
    try:
        import markdown as md

        rendered = md.markdown(source, extensions=list(_MARKDOWN_EXTENSIONS))
    except Exception:
        return wrap_document_html(_plain_to_chat_html(source))

    rendered = _sanitize_chat_html(rendered)
    rendered = _upgrade_fenced_pre_to_cards(rendered)
    rendered = _upgrade_inline_code_file_chips(rendered)
    return wrap_document_html(_style_chat_html(rendered))


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
    return escaped.replace("\n", "<br>")


def _sanitize_chat_html(html_body: str) -> str:
    t = html_body
    t = re.sub(r"(?is)<script[\s\S]*?</script>", "", t)
    t = re.sub(r"(?is)<style[\s\S]*?</style>", "", t)
    t = re.sub(r"(?is)<iframe[\s\S]*?</iframe>", "", t)
    return t


def _style_img_tag(attrs: str) -> str:
    from iris.core.markdown_text import iris_image_href

    sm = _IMG_SRC.search(attrs or "")
    src = (sm.group(2) if sm else "").strip()
    if not src:
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


def _style_chat_html(html_body: str) -> str:
    t = TOKENS
    body = f"color:{t.text_primary};"
    shell = (
        f"background-color:{t.chat_block_bg};"
        f"border:1px solid {t.chat_block_border};"
        f"border-radius:{t.chat_block_radius}px;"
        f"padding:8px;margin:4px 0;white-space:pre-wrap;{body}"
    )
    out = html_body
    out = re.sub(
        r"<p>",
        f'<span style="display:block;margin:0 0 4px 0;{body}">',
        out,
    )
    out = re.sub(r"</p>", "</span>", out)
    out = re.sub(
        r"<hr\s*/?>",
        f'<hr style="border:none;border-top:1px solid {t.text_muted};margin:8px 0;height:0;" />',
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(r"<pre>", f'<pre style="{shell}">', out)
    out = re.sub(
        r"<code>",
        f'<code style="color:#a5b4fc;font-family:{t.chat_block_mono_font};">',
        out,
    )
    out = re.sub(
        r"<h([1-6])>",
        f'<span style="display:block;font-weight:700;margin:6px 0 4px 0;{body}">',
        out,
    )
    out = re.sub(r"</h[1-6]>", "</span>", out)
    out = re.sub(
        r'<a(?![^>]*\bstyle=)(?=[^>]*href="(?!iris-))',
        '<a style="color:#60a5fa;" ',
        out,
    )
    out = _IMG_TAG.sub(lambda m: _style_img_tag(m.group(1)), out)
    return out


if __name__ == "__main__":
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
    print("chat_renderer file/diff ok")
