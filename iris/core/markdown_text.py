"""마크다운 ↔ 채팅 표시·음성용 plain text 변환."""

from __future__ import annotations

import html
import re

_MARKDOWN_EXTENSIONS = ("nl2br", "fenced_code", "tables", "sane_lists")


_TRAILING_MD_TAIL = re.compile(r"(\*+|_+|`+)\s*$")
_INCOMPLETE_LINK = re.compile(r"\[[^\]]*$")


def markdown_to_plain_partial(text: str) -> str:
    """타이핑 중 불완전 마크다운 토큰을 정리한 평문."""
    plain = markdown_to_plain(text)
    # 닫히지 않은 강조·코드·링크 꼬리 제거
    plain = re.sub(r"\*\*[^*]+$", "", plain)
    plain = re.sub(r"(?<!\*)\*[^*]+$", "", plain)
    plain = re.sub(r"`[^`]+$", "", plain)
    plain = _TRAILING_MD_TAIL.sub("", plain)
    plain = _INCOMPLETE_LINK.sub("", plain)
    return plain.rstrip()


def markdown_to_plain(text: str) -> str:
    """마크다운을 TTS·타이핑 동기화용 일반 텍스트로 변환."""
    t = (text or "").strip()
    if not t:
        return ""

    t = re.sub(r"```[\s\S]*?```", " ", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    t = re.sub(r"__([^_]+)__", r"\1", t)
    t = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", t)
    t = re.sub(r"^#{1,6}\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*\d+\.\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def markdown_to_chat_html(text: str) -> str:
    """Markdown → QTextEdit용 안전 HTML."""
    t = (text or "").strip()
    if not t:
        return ""

    try:
        import markdown as md

        rendered = md.markdown(t, extensions=list(_MARKDOWN_EXTENSIONS))
    except Exception:
        return _plain_to_chat_html(t)

    return _style_chat_html(_sanitize_chat_html(rendered))


def _plain_to_chat_html(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped.replace("\n", "<br>")


def _sanitize_chat_html(html_body: str) -> str:
    """QTextEdit에 넣기 전 위험 태그 제거."""
    t = html_body
    t = re.sub(r"(?is)<script[\s\S]*?</script>", "", t)
    t = re.sub(r"(?is)<style[\s\S]*?</style>", "", t)
    t = re.sub(r"(?is)<iframe[\s\S]*?</iframe>", "", t)
    return t


def _style_chat_html(html_body: str) -> str:
    """다크 채팅창에 맞게 QTextEdit 호환 스타일 적용."""
    t = html_body
    t = re.sub(
        r"<p>",
        '<span style="display:block;margin:0 0 4px 0;">',
        t,
    )
    t = re.sub(r"</p>", "</span>", t)
    t = re.sub(
        r"<pre>",
        '<pre style="background-color:#1e293b;border-radius:6px;padding:8px;margin:4px 0;white-space:pre-wrap;">',
        t,
    )
    t = re.sub(
        r"<code>",
        '<code style="color:#a5b4fc;">',
        t,
    )
    t = re.sub(
        r"<h([1-6])>",
        r'<span style="display:block;font-weight:700;margin:6px 0 4px 0;">',
        t,
    )
    t = re.sub(r"</h[1-6]>", "</span>", t)
    t = re.sub(
        r"<a ",
        '<a style="color:#60a5fa;" ',
        t,
    )
    return t
