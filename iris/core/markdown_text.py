"""마크다운 ↔ 채팅 표시·음성용 plain text 변환."""

from __future__ import annotations

import html
import re
from urllib.parse import quote

_MARKDOWN_EXTENSIONS = ("nl2br", "fenced_code", "tables", "sane_lists")


_TRAILING_MD_TAIL = re.compile(r"(\*+|_+|`+)\s*$")
_INCOMPLETE_LINK = re.compile(r"\[[^\]]*$")
_IMG_TAG = re.compile(
    r"<img\b([^>]*?)(?:\s*/\s*>|>\s*</img\s*>|>)",
    re.IGNORECASE | re.DOTALL,
)
_IMG_SRC = re.compile(r"""\bsrc\s*=\s*(['"])(.*?)\1""", re.IGNORECASE)
_IMG_ALT = re.compile(r"""\balt\s*=\s*(['"])(.*?)\1""", re.IGNORECASE)

# 채팅 인라인 이미지 — 클릭 시 라이트박스 (iris-image:<urlencoded>)
IRIS_IMAGE_SCHEME = "iris-image:"


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
    # 이미지 먼저 (뒤에 일반 링크 치환이 ![alt]를 망가뜨리지 않게)
    t = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", t)
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


def extract_chat_image_srcs(html_body: str) -> list[str]:
    """채팅 HTML에서 img src 목록 (원격 로드용)."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _IMG_TAG.finditer(html_body or ""):
        sm = _IMG_SRC.search(m.group(1) or "")
        if not sm:
            continue
        src = (sm.group(2) or "").strip()
        if not src or src in seen:
            continue
        seen.add(src)
        out.append(src)
    return out


def iris_image_href(src: str) -> str:
    return f"{IRIS_IMAGE_SCHEME}{quote(src or '', safe='')}"


def parse_iris_image_href(href: str) -> str | None:
    if not (href or "").startswith(IRIS_IMAGE_SCHEME):
        return None
    from urllib.parse import unquote

    return unquote(href[len(IRIS_IMAGE_SCHEME) :]) or None


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


def _style_img_tag(attrs: str) -> str:
    sm = _IMG_SRC.search(attrs or "")
    src = (sm.group(2) if sm else "").strip()
    if not src:
        return ""
    am = _IMG_ALT.search(attrs or "")
    alt = html.escape((am.group(2) if am else "").strip(), quote=True)
    src_esc = html.escape(src, quote=True)
    href = html.escape(iris_image_href(src), quote=True)
    # GPT식: 본문 안 중간 크기 썸네일, 클릭하면 확대
    return (
        f'<a href="{href}" title="클릭하여 크게 보기">'
        f'<img src="{src_esc}" alt="{alt}" '
        f'style="max-width:420px;max-height:280px;border-radius:10px;'
        f'margin:8px 0;cursor:pointer;" /></a>'
    )


def _style_chat_html(html_body: str) -> str:
    """다크 채팅창에 맞게 QTextEdit 호환 스타일 적용."""
    # ponytail: QTextEdit HTML 기본 전경이 검정이면 다크 배경에서 가로획(ㅡ/─/hr)이 안 보임
    _body = "color:#e8f0fe;"
    t = html_body
    t = re.sub(
        r"<p>",
        f'<span style="display:block;margin:0 0 4px 0;{_body}">',
        t,
    )
    t = re.sub(r"</p>", "</span>", t)
    # --- / ___ 마크다운 구분선 — 투명/검정 hr 대신 보이는 선
    t = re.sub(
        r"<hr\s*/?>",
        '<hr style="border:none;border-top:1px solid #64748b;margin:8px 0;height:0;" />',
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"<pre>",
        f'<pre style="background-color:#1e293b;border-radius:6px;padding:8px;margin:4px 0;'
        f'white-space:pre-wrap;{_body}">',
        t,
    )
    t = re.sub(
        r"<code>",
        '<code style="color:#a5b4fc;">',
        t,
    )
    t = re.sub(
        r"<h([1-6])>",
        f'<span style="display:block;font-weight:700;margin:6px 0 4px 0;{_body}">',
        t,
    )
    t = re.sub(r"</h[1-6]>", "</span>", t)
    t = re.sub(
        r"<a ",
        '<a style="color:#60a5fa;" ',
        t,
    )
    # 이미지 래핑은 링크 스타일 적용 후에 — 썸네일 앵커에 파란 밑줄이 안 붙게
    t = _IMG_TAG.sub(lambda m: _style_img_tag(m.group(1)), t)
    return t


if __name__ == "__main__":
    html = markdown_to_chat_html("스나드에서 \u3161\n\n---\n\n다음")
    assert "\u3161" in html
    assert "color:#e8f0fe" in html
    assert "border-top:1px solid" in html
    print("markdown_text chat html ok")
