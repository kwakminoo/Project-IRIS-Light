"""위키 노트 위는 요약, 아래는 원본. PDF는 파일, 웹은 단일 HTML."""

from __future__ import annotations

import base64
import mimetypes
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

_MARKER = re.compile(r"(?m)^- iris-original:\s*(\S+)\s*$")
_EMPTY = "(요약에 쓸 모델이 없습니다.)"
# ponytail: 문서 전체가 아니라 리소스 하나. 이보다 큰 그림·글꼴은 URL을 남긴다.
_ASSET_BYTES = 15_000_000
_SKIP_TAGS = {"script", "noscript"}


def split_summary_sections(summary: str) -> tuple[str, str]:
    text = (summary or "").strip()
    if "## 핵심 개념" in text:
        head, concepts = text.split("## 핵심 개념", 1)
        head = head.replace("## 전체 요약", "").strip()
        concepts = concepts.strip()
        return head, concepts
    head = text.replace("## 전체 요약", "").strip()
    return head, ""


def compose_wiki_body(*, summary: str, original: str) -> str:
    whole, concepts = split_summary_sections(summary)
    lines = [
        "## 전체 요약",
        "",
        whole or _EMPTY,
        "",
        "## 핵심 개념",
        "",
        concepts or _EMPTY,
        "",
        "## 원본",
        "",
        (original or "").strip(),
    ]
    return "\n".join(lines).strip() + "\n"


def split_note_view(markdown: str) -> tuple[str, str]:
    """미리보기 위쪽 글, 노트 옆 원본 상대 경로."""
    text = markdown or ""
    match = _MARKER.search(text)
    asset = match.group(1) if match else ""
    if "## 원본" in text and asset:
        text = text.split("## 원본", 1)[0]
    if match and not asset:
        text = _MARKER.sub("", text)
    return text.strip(), asset


def insert_original_marker(path: Path, asset_rel: str) -> None:
    line = f"- iris-original: {asset_rel}"
    text = path.read_text(encoding="utf-8")
    if line in text:
        return
    stamp = "\n> updated:"
    if stamp in text:
        text = text.replace(stamp, f"\n{line}\n{stamp}", 1)
    else:
        text = text.rstrip() + "\n\n" + line + "\n"
    path.write_text(text, encoding="utf-8")


def store_original(note_path: Path, *, kind: str, source: str) -> str:
    """노트 옆에 원본을 둔다. 마커에 쓸 상대 경로. 없으면 빈 문자열."""
    folder = note_path.with_name(note_path.stem + ".assets")
    try:
        if kind == "pdf":
            src = Path(source)
            if not src.is_file():
                return ""
            folder.mkdir(parents=True, exist_ok=True)
            dest = folder / "original.pdf"
            shutil.copyfile(src, dest)
            return f"{folder.name}/original.pdf"
        if kind == "image":
            src = Path(source)
            if not src.is_file():
                return ""
            folder.mkdir(parents=True, exist_ok=True)
            ext = src.suffix.lower() if src.suffix else ".png"
            dest = folder / f"original{ext}"
            shutil.copyfile(src, dest)
            return f"{folder.name}/{dest.name}"
        if kind == "url":
            html = snapshot_html(source)
            if not html.strip():
                return ""
            folder.mkdir(parents=True, exist_ok=True)
            dest = folder / "original.html"
            dest.write_text(html, encoding="utf-8")
            return f"{folder.name}/original.html"
        if kind == "text" and Path(source).suffix.lower() in {".html", ".htm"}:
            src = Path(source)
            if not src.is_file():
                return ""
            raw = src.read_text(encoding="utf-8", errors="replace")
            html = inline_html(raw, src.resolve().as_uri())
            folder.mkdir(parents=True, exist_ok=True)
            dest = folder / "original.html"
            dest.write_text(html, encoding="utf-8")
            return f"{folder.name}/original.html"
    except (OSError, ValueError, TimeoutError):
        return ""
    return ""


class _StripScripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in _SKIP_TAGS:
            self._skip += 1
            return
        if self._skip:
            return
        self.parts.append(self.get_starttag_text() or "")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _SKIP_TAGS:
            if self._skip:
                self._skip -= 1
            return
        if self._skip:
            return
        self.parts.append(f"</{tag}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in _SKIP_TAGS or self._skip:
            return
        self.parts.append(self.get_starttag_text() or "")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if not self._skip:
            self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self._skip:
            self.parts.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        if not self._skip:
            self.parts.append(f"<!--{data}-->")


def _strip_scripts(html: str) -> str:
    parser = _StripScripts()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        return html or ""
    return "".join(parser.parts)


def _fetch(url: str, *, timeout: float) -> bytes | None:
    if not url or url.startswith(("data:", "javascript:", "mailto:", "#")):
        return None
    try:
        req = Request(url, headers={"User-Agent": "Iris-Wiki/1.0 (+local content import)"})
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read(_ASSET_BYTES + 1)
    except (OSError, ValueError, TimeoutError):
        return None
    if len(data) > _ASSET_BYTES:
        return None
    return data


def _data_uri(url: str, data: bytes) -> str:
    mime = mimetypes.guess_type(urlparse(url).path)[0] or "application/octet-stream"
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


_LINK = re.compile(r"<link\b([^>]*?)>", re.I)
_ATTR = re.compile(r"""([:\w-]+)\s*=\s*(['"])(.*?)\2""", re.I)
_CSS_URL = re.compile(r"""url\(\s*['"]?([^'")]+)['"]?\s*\)""", re.I)
_IMG = re.compile(
    r"""(<img\b[^>]*?\bsrc\s*=\s*)(['"])([^'"]+)\2""",
    re.I,
)


def _attrs(blob: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for match in _ATTR.finditer(blob or ""):
        found[match.group(1).lower()] = match.group(3)
    return found


def _inline_css(css: str, base: str, *, timeout: float, fetch) -> str:
    def repl(match: re.Match[str]) -> str:
        raw = (match.group(1) or "").strip()
        if not raw or raw.startswith("data:"):
            return match.group(0)
        target = urljoin(base, raw)
        data = fetch(target, timeout=timeout)
        if not data:
            return match.group(0)
        return f"url({_data_uri(target, data)})"

    return _CSS_URL.sub(repl, css or "")


def inline_html(html: str, base_url: str, *, timeout: float = 20.0, fetch=None) -> str:
    """CSS·이미지를 문서 안에 넣고 스크립트는 뺀다. 위키 창 너비에 맞춰 다시 배치된다."""
    getter = fetch or _fetch
    text = _strip_scripts(html or "")

    def link_repl(match: re.Match[str]) -> str:
        attrs = _attrs(match.group(1))
        rel = attrs.get("rel", "").lower()
        href = attrs.get("href", "").strip()
        if "stylesheet" not in rel or not href:
            return match.group(0)
        target = urljoin(base_url, href)
        data = getter(target, timeout=timeout)
        if not data:
            return match.group(0)
        css = data.decode("utf-8", errors="replace")
        css = _inline_css(css, target, timeout=timeout, fetch=getter)
        return f"<style>{css}</style>"

    text = _LINK.sub(link_repl, text)

    def img_repl(match: re.Match[str]) -> str:
        src = match.group(3).strip()
        if not src or src.startswith("data:"):
            return match.group(0)
        target = urljoin(base_url, src)
        data = getter(target, timeout=timeout)
        if not data:
            return match.group(0)
        return f"{match.group(1)}{match.group(2)}{_data_uri(target, data)}{match.group(2)}"

    return _IMG.sub(img_repl, text)


def snapshot_html(url: str, *, timeout: float = 20.0) -> str:
    req = Request(
        url.strip(),
        headers={"User-Agent": "Iris-Wiki/1.0 (+local content import)"},
    )
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        final = resp.geturl() or url
        ctype = (resp.headers.get("Content-Type") or "").lower()
    charset = "utf-8"
    found = re.search(r"charset=([^\s;]+)", ctype)
    if found:
        charset = found.group(1).strip("\"'")
    html = raw.decode(charset, errors="replace")
    return inline_html(html, final, timeout=timeout)


def _check() -> None:
    whole, concepts = split_summary_sections(
        "## 전체 요약\n\n한 줄.\n\n## 핵심 개념\n\n- 가\n- 나\n"
    )
    assert whole == "한 줄."
    assert concepts.startswith("- 가")
    body = compose_wiki_body(summary="", original="원문 전체")
    assert body.startswith("## 전체 요약")
    assert "## 핵심 개념" in body and "## 원본" in body
    assert "원문 전체" in body
    top, asset = split_note_view(body + "\n- iris-original: note.assets/original.pdf\n")
    assert asset.endswith("original.pdf")
    assert "## 원본" not in top
    assert "## 전체 요약" in top

    html = inline_html(
        """<html><head>
        <link rel="stylesheet" href="app.css">
        <script>alert(1)</script>
        </head><body><img src="a.png" alt="pic">본문</body></html>""",
        "https://example.com/post",
        fetch=lambda url, timeout=20.0: b"body{color:red}" if url.endswith(".css") else b"\x89PNG",
    )
    assert "<script" not in html.lower()
    assert "data:text/css" in html or "data:" in html
    assert "본문" in html
    assert 'src="https://example.com/a.png"' not in html
    print("wiki_original ok")


if __name__ == "__main__":
    _check()
