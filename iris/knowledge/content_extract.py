"""PDF·URL·텍스트 파일에서 위키 저장용 본문 추출."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

_MAX_CHARS = 80_000
_TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".csv", ".json", ".log"}
_PDF_SUFFIXES = {".pdf"}
_TESSDATA_LANGS = ("eng", "osd", "kor")
_TESSDATA_URL = "https://github.com/tesseract-ocr/tessdata/raw/main/{lang}.traineddata"
_WIN_TESSERACT_CANDIDATES = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)
_tesseract_ready = False
_tessdata_dir: Path | None = None


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self._in_title = False
        self._chunks: list[str] = []
        self.title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip += 1
            return
        if tag == "title":
            self._in_title = True
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"):
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
            return
        if self._skip:
            return
        text = (data or "").strip()
        if text:
            self._chunks.append(text + " ")

    def text(self) -> str:
        raw = "".join(self._chunks)
        raw = re.sub(r"[ \t]+\n", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def _truncate(text: str, *, limit: int = _MAX_CHARS) -> tuple[str, bool]:
    text = (text or "").strip()
    if len(text) <= limit:
        return text, False
    cut = text[:limit].rsplit("\n", 1)[0].strip() or text[:limit]
    return cut + f"\n\n… (truncated at {limit} chars)", True


def _looks_like_url(source: str) -> bool:
    s = (source or "").strip()
    if not s:
        return False
    try:
        p = urlparse(s)
    except ValueError:
        return False
    return p.scheme in ("http", "https") and bool(p.netloc)


def _extract_pdf_text_pypdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf not installed — run: pip install pypdf") from exc
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def _resolve_tesseract_cmd() -> str:
    env = (os.environ.get("TESSERACT_CMD") or "").strip().strip('"')
    if env and Path(env).is_file():
        return env
    if sys.platform == "win32":
        for cand in _WIN_TESSERACT_CANDIDATES:
            if cand.is_file():
                return str(cand)
    found = shutil.which("tesseract")
    if found:
        return found
    raise RuntimeError(
        "OCR 실패 (pdf-ocr): Tesseract OCR이 설치되지 않았습니다. "
        "Windows: scripts\\setup_tesseract.ps1 실행 또는 "
        "winget install UB-Mannheim.TesseractOCR"
    )


def _iris_tessdata_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home())
    d = Path(base) / "iris" / "tesseract" / "tessdata"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _system_tessdata_dir(tesseract_cmd: str) -> Path | None:
    root = Path(tesseract_cmd).resolve().parent
    cand = root / "tessdata"
    return cand if cand.is_dir() else None


def _download_tessdata(lang: str, dest: Path) -> None:
    url = _TESSDATA_URL.format(lang=lang)
    req = Request(url, headers={"User-Agent": "iris-tesseract-bootstrap/1.0"})
    with urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())


def _bootstrap_tessdata(tesseract_cmd: str) -> Path:
    """ponytail: user-writable tessdata; copy eng/osd from install, fetch kor."""
    user = _iris_tessdata_dir()
    sys_dir = _system_tessdata_dir(tesseract_cmd)
    for lang in _TESSDATA_LANGS:
        dest = user / f"{lang}.traineddata"
        if dest.is_file() and dest.stat().st_size > 1024:
            continue
        if sys_dir:
            src = sys_dir / f"{lang}.traineddata"
            if src.is_file():
                shutil.copy2(src, dest)
                continue
        if lang == "kor":
            _download_tessdata(lang, dest)
    missing = [lang for lang in _TESSDATA_LANGS if not (user / f"{lang}.traineddata").is_file()]
    if missing:
        raise RuntimeError(
            "OCR 실패 (pdf-ocr): tessdata 언어 팩이 없습니다 — "
            + ", ".join(missing)
            + ". scripts\\setup_tesseract.ps1 을 실행하세요."
        )
    return user


def _configure_tesseract(pytesseract: object) -> None:
    global _tessdata_dir
    cmd = _resolve_tesseract_cmd()
    pytesseract.pytesseract.tesseract_cmd = cmd  # type: ignore[attr-defined]
    _tessdata_dir = _bootstrap_tessdata(cmd)


def _ensure_tesseract() -> None:
    global _tesseract_ready
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError(
            "PDF OCR에 pytesseract가 필요합니다 — pip install pytesseract pymupdf"
        ) from exc
    if not _tesseract_ready:
        _configure_tesseract(pytesseract)
        _tesseract_ready = True
    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError(
            "OCR 실패 (pdf-ocr): Tesseract 실행 파일을 찾을 수 없습니다. "
            "TESSERACT_CMD 환경 변수로 tesseract.exe 경로를 지정하거나 "
            "scripts\\setup_tesseract.ps1 을 실행하세요."
        ) from exc


def _extract_pdf_text_ocr(path: Path) -> str:
    """ponytail: pymupdf render + pytesseract; needs system Tesseract with kor."""
    import io

    _ensure_tesseract()
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError("PDF OCR에 pymupdf가 필요합니다 — pip install pymupdf") from exc
    import pytesseract
    from PIL import Image

    parts: list[str] = []
    tess_cfg = f"--tessdata-dir {_tessdata_dir.as_posix()}" if _tessdata_dir else ""
    doc = pymupdf.open(str(path))
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=150)
            im = Image.open(io.BytesIO(pix.tobytes("png")))
            chunk = pytesseract.image_to_string(im, lang="kor+eng", config=tess_cfg).strip()
            if chunk:
                parts.append(chunk)
    finally:
        doc.close()
    text = "\n\n".join(parts)
    if not text.strip():
        raise ValueError(
            "OCR로 텍스트를 추출하지 못했습니다 (pdf-ocr). "
            "Tesseract에 kor 언어 팩이 설치되어 있는지 확인하세요."
        )
    return text


def extract_pdf_text(path: Path) -> str:
    text = _extract_pdf_text_pypdf(path)
    if text.strip():
        return text
    return _extract_pdf_text_ocr(path)


def fetch_firecrawl_text(url: str, *, timeout: float = 45.0) -> tuple[str, str]:
    """Firecrawl scrape → (title, markdown). API 키 없으면 ValueError."""
    from iris.infrastructure.api_quota import _env_get

    key = _env_get("FIRECRAWL_API_KEY").strip()
    if not key:
        raise ValueError("FIRECRAWL_API_KEY not set")
    payload = json.dumps({"url": url.strip(), "formats": ["markdown"]}).encode("utf-8")
    req = Request(
        "https://api.firecrawl.dev/v1/scrape",
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "iris-wiki-import/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise ValueError(f"firecrawl HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"firecrawl failed: {exc}") from exc
    if not data.get("success"):
        raise ValueError(str(data.get("error") or "firecrawl scrape failed"))
    block = data.get("data") if isinstance(data.get("data"), dict) else {}
    md = str(block.get("markdown") or "").strip()
    if not md:
        raise ValueError("firecrawl returned empty markdown")
    meta = block.get("metadata") if isinstance(block.get("metadata"), dict) else {}
    title = str(meta.get("title") or meta.get("ogTitle") or "").strip()
    if not title:
        title = urlparse(url).netloc or "web page"
    return title, md


def fetch_url_text(url: str, *, timeout: float = 20.0) -> tuple[str, str]:
    last_err: Exception | None = None
    try:
        title, body = _fetch_url_text_stdlib(url, timeout=timeout)
        if body.strip():
            return title, body
        last_err = ValueError("no readable text at URL")
    except ValueError as exc:
        last_err = exc
    try:
        return fetch_firecrawl_text(url, timeout=max(timeout, 30.0))
    except ValueError as exc:
        if last_err:
            raise last_err from exc
        raise


def _fetch_url_text_stdlib(url: str, *, timeout: float = 20.0) -> tuple[str, str]:
    req = Request(
        url.strip(),
        headers={"User-Agent": "Iris-Wiki/1.0 (+local content import)"},
    )
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        ctype = (resp.headers.get("Content-Type") or "").lower()
    charset = "utf-8"
    m = re.search(r"charset=([^\s;]+)", ctype)
    if m:
        charset = m.group(1).strip("\"'")
    html = raw.decode(charset, errors="replace")
    parser = _HtmlTextExtractor()
    parser.feed(html)
    title = parser.title.strip() or urlparse(url).netloc or "web page"
    body = parser.text()
    if not body:
        raise ValueError("no readable text at URL")
    return title, body


def extract_from_source(source: str) -> dict[str, str | bool]:
    """파일 경로 또는 http(s) URL → {kind, title, text, source, truncated}."""
    src = (source or "").strip().strip('"').strip("'")
    if not src:
        raise ValueError("source required (file path or http(s) URL)")

    if _looks_like_url(src):
        title, text = fetch_url_text(src)
        text, truncated = _truncate(text)
        return {
            "kind": "url",
            "title": title,
            "text": text,
            "source": src,
            "truncated": truncated,
        }

    path = Path(src).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"not a file: {src}")

    suffix = path.suffix.lower()
    if suffix in _PDF_SUFFIXES:
        text_raw = _extract_pdf_text_pypdf(path)
        ocr_used = not text_raw.strip()
        text = _extract_pdf_text_ocr(path) if ocr_used else text_raw
        text, truncated = _truncate(text)
        return {
            "kind": "pdf",
            "title": path.stem,
            "text": text,
            "source": str(path.resolve()),
            "truncated": truncated,
            "ocr_used": ocr_used,
        }

    if suffix in _TEXT_SUFFIXES or suffix == "":
        text = path.read_text(encoding="utf-8", errors="replace")
        text, truncated = _truncate(text)
        return {
            "kind": "text",
            "title": path.stem,
            "text": text,
            "source": str(path.resolve()),
            "truncated": truncated,
        }

    raise ValueError(f"unsupported file type: {suffix or '(no extension)'}")
