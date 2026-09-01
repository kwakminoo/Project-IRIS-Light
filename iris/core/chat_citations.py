"""채팅 답변 속 웹 근거 URL → GPT식 작은 인용 버튼."""

from __future__ import annotations

import html
import re
from urllib.parse import urlparse

# ![alt](url) — 인용 칩으로 바꾸지 않음 (채팅 인라인 이미지)
_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
# [title](https://...) — 이미지 마크다운(![...])은 제외
_MD_LINK = re.compile(r"(?<!!)\[([^\]]*)\]\((https?://[^)\s]+)\)")
# bare URL (마크다운 링크 처리 후 남은 것)
_BARE_URL = re.compile(r"(?<![\w\"'=])(https?://[^\s<>\]\"']+)")
_CITE_TOKEN = re.compile(r"%%IRIS_CITE_(\d+)%%")
_IMG_HOLD = re.compile(r"%%IRIS_IMG_(\d+)%%")


def _clean_url(url: str) -> str:
    return (url or "").strip().rstrip(").,;]}>\"'")


def _host_label(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return "source"
    if host.startswith("www."):
        host = host[4:]
    return host or "source"


def _chip_html(n: int, url: str, title: str) -> str:
    from iris.ui.chat.chat_blocks import citation_chip_to_html

    return citation_chip_to_html(n, _clean_url(url), title or _host_label(url))


def collect_and_tokenize_citations(text: str) -> tuple[str, list[tuple[str, str]]]:
    """마크다운/베어 URL을 %%IRIS_CITE_n%% 토큰으로 치환. sources=(title,url) 1-index 순."""
    sources: list[tuple[str, str]] = []
    url_to_n: dict[str, int] = {}
    held_images: list[str] = []

    def _hold_image(m: re.Match[str]) -> str:
        held_images.append(m.group(0))
        return f"%%IRIS_IMG_{len(held_images) - 1}%%"

    # 이미지 URL이 bare/citation에 먹히지 않도록 먼저 보관
    out = _MD_IMAGE.sub(_hold_image, text or "")

    def _num(title: str, url: str) -> int:
        u = _clean_url(url)
        if not u:
            return 0
        if u in url_to_n:
            return url_to_n[u]
        sources.append(((title or "").strip() or _host_label(u), u))
        n = len(sources)
        url_to_n[u] = n
        return n

    def md_repl(m: re.Match[str]) -> str:
        title, url = m.group(1), m.group(2)
        n = _num(title, url)
        if not n:
            return m.group(0)
        # 본문에 제목은 남기고 옆 칩만
        label = (title or "").strip()
        if label and not label.startswith("http"):
            return f"{label} %%IRIS_CITE_{n}%%"
        return f"%%IRIS_CITE_{n}%%"

    out = _MD_LINK.sub(md_repl, out)

    def bare_repl(m: re.Match[str]) -> str:
        url = m.group(1)
        n = _num(_host_label(url), url)
        return f"%%IRIS_CITE_{n}%%" if n else m.group(0)

    out = _BARE_URL.sub(bare_repl, out)

    def _restore_image(m: re.Match[str]) -> str:
        i = int(m.group(1))
        if 0 <= i < len(held_images):
            return held_images[i]
        return m.group(0)

    out = _IMG_HOLD.sub(_restore_image, out)
    return out, sources


def tokens_to_chips_html(html_body: str, sources: list[tuple[str, str]]) -> str:
    if not sources:
        return html_body

    def repl(m: re.Match[str]) -> str:
        n = int(m.group(1))
        if n < 1 or n > len(sources):
            return m.group(0)
        title, url = sources[n - 1]
        return _chip_html(n, url, title)

    body = _CITE_TOKEN.sub(repl, html_body)
    # 푸터: 같은 번호 칩 + 짧은 호스트
    bits = [
        '<span style="display:block;margin-top:8px;padding-top:6px;'
        'border-top:1px solid rgba(148,163,184,0.18);">'
        '<span style="color:#64748b;font-size:10px;letter-spacing:0.4px;">SOURCES</span> '
    ]
    for i, (title, url) in enumerate(sources, start=1):
        label = _host_label(url)
        bits.append(_chip_html(i, url, title or label))
        bits.append(
            f'<span style="color:#94a3b8;font-size:10px;margin-right:6px;">'
            f"{html.escape(label)}</span>"
        )
    bits.append("</span>")
    return body + "".join(bits)


def iris_message_to_chat_html(text: str) -> str:
    """Iris 답변: 마크다운 HTML + 인용 칩."""
    from iris.ui.chat.chat_renderer import render_iris_message

    return render_iris_message(text)


if __name__ == "__main__":
    sample = (
        "연구에 따르면 A입니다 [OpenAI](https://openai.com/research).\n"
        "자세한 내용은 https://example.com/docs 참고.\n"
        "다시 [OpenAI](https://openai.com/research) 인용."
    )
    tok, src = collect_and_tokenize_citations(sample)
    assert len(src) == 2, src
    assert "%%IRIS_CITE_1%%" in tok and "%%IRIS_CITE_2%%" in tok
    html_out = iris_message_to_chat_html(sample)
    assert "href=" in html_out and "SOURCES" in html_out
    assert html_out.count("openai.com") >= 1
    # 이미지 마크다운은 인용 칩으로 바꾸지 않음
    with_img = (
        "제품 예시입니다.\n"
        "![TILSBERK HUD](https://cdn.example.com/tilsberk.jpg)\n"
        "출처 [Maker](https://maker.example.com/)."
    )
    tok2, src2 = collect_and_tokenize_citations(with_img)
    assert "![TILSBERK HUD](https://cdn.example.com/tilsberk.jpg)" in tok2, tok2
    assert len(src2) == 1 and "maker.example.com" in src2[0][1]
    html_img = iris_message_to_chat_html(with_img)
    assert "iris-image:" in html_img and "<img " in html_img
    assert "cdn.example.com/tilsberk.jpg" in html_img
    print("chat_citations ok", len(src), "sources; images preserved")

