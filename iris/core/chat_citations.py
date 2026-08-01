"""채팅 답변 속 웹 근거 URL → GPT식 작은 인용 버튼."""

from __future__ import annotations

import html
import re
from urllib.parse import urlparse

# [title](https://...)
_MD_LINK = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
# bare URL (마크다운 링크 처리 후 남은 것)
_BARE_URL = re.compile(r"(?<![\w\"'=])(https?://[^\s<>\]\"']+)")
_CITE_TOKEN = re.compile(r"%%IRIS_CITE_(\d+)%%")


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
    tip = html.escape(title or _host_label(url), quote=True)
    href = html.escape(_clean_url(url), quote=True)
    return (
        f'<a href="{href}" title="{tip}" '
        f'style="display:inline;font-size:10px;font-weight:600;'
        f'padding:1px 6px;margin:0 2px;border-radius:9px;'
        f'background-color:rgba(56,189,248,0.14);color:#7dd3fc;'
        f'text-decoration:none;border:1px solid rgba(56,189,248,0.40);'
        f'">[{n}]</a>'
    )


def collect_and_tokenize_citations(text: str) -> tuple[str, list[tuple[str, str]]]:
    """마크다운/베어 URL을 %%IRIS_CITE_n%% 토큰으로 치환. sources=(title,url) 1-index 순."""
    sources: list[tuple[str, str]] = []
    url_to_n: dict[str, int] = {}

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

    out = _MD_LINK.sub(md_repl, text or "")

    def bare_repl(m: re.Match[str]) -> str:
        url = m.group(1)
        n = _num(_host_label(url), url)
        return f"%%IRIS_CITE_{n}%%" if n else m.group(0)

    out = _BARE_URL.sub(bare_repl, out)
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
    from iris.core.markdown_text import markdown_to_chat_html

    tokenized, sources = collect_and_tokenize_citations(text or "")
    rendered = markdown_to_chat_html(tokenized)
    return tokens_to_chips_html(rendered, sources)


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
    print("chat_citations ok", len(src), "sources")
