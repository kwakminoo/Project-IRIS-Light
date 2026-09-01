"""마크다운 ↔ 채팅 표시·음성용 plain text 변환."""

from __future__ import annotations

import re
from urllib.parse import quote

_TRAILING_MD_TAIL = re.compile(r"(\*+|_+|`+)\s*$")
_INCOMPLETE_LINK = re.compile(r"\[[^\]]*$")
_IMG_TAG = re.compile(
    r"<img\b([^>]*?)(?:\s*/\s*>|>\s*</img\s*>|>)",
    re.IGNORECASE | re.DOTALL,
)
_IMG_SRC = re.compile(r"""\bsrc\s*=\s*(['"])(.*?)\1""", re.IGNORECASE)

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
    from iris.ui.chat.chat_renderer import render_markdown_document

    return render_markdown_document(text, citations=False)


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


if __name__ == "__main__":
    html = markdown_to_chat_html("스나드에서 \u3161\n\n---\n\n다음")
    assert "\u3161" in html
    assert "color:#e8f0fe" in html
    assert "border-top:1px solid" in html
    print("markdown_text chat html ok")
