"""PDF·URL·텍스트 파일에서 위키 저장용 본문 추출."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from contextvars import ContextVar
from threading import Lock
from time import monotonic
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

_MAX_CHARS = 80_000
_TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".csv", ".json", ".log"}
_CODE_SUFFIXES = {
    ".py", ".pyw", ".html", ".htm", ".css", ".js", ".mjs", ".cjs",
    ".ts", ".tsx", ".jsx", ".xml", ".yaml", ".yml", ".toml", ".ini",
    ".cfg", ".java", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".go",
    ".rs", ".rb", ".php", ".sql", ".sh", ".ps1", ".bat", ".vue", ".svelte",
    ".mdx",
}
_PDF_SUFFIXES = {".pdf"}
_OFFICE_SUFFIXES = {".docx", ".pptx", ".xlsx"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_HWP_SUFFIXES = {".hwp", ".hwpx"}
_LAYER_MIN = 40
_OCR_KEEP = 8
VISION_PAGE_CAP = 4
_TESSDATA_LANGS = ("kor", "eng")
_WIN_TESSERACT_CANDIDATES = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)
_tesseract_runtime: tuple[str, Path | None, frozenset[str]] | None = None
_ocr_setup_lock = Lock()
_ocr_cancelled = ContextVar("iris_ocr_cancelled", default=lambda: False)

# 웹 Setup 다운로드 오류와 분리 — 도움말: https://iris-light-site.vercel.app/#install
_SETUP_HELP = "https://iris-light-site.vercel.app/#install"
_SUPPORTED_ATTACH = (
    "PDF, Markdown, TXT, CSV, JSON, LOG, 소스코드, HTML, DOCX, PPTX, XLSX, "
    "PNG/JPG 등 이미지, http(s) URL"
)


class UnsupportedAttachmentTypeError(ValueError):
    """채팅/위키 첨부 본문 추출이 거부된 경우 (Windows Setup 다운로드와 무관)."""

    code = "ATTACHMENT_UNSUPPORTED_TYPE"

    def __init__(self, suffix: str) -> None:
        label = suffix or "(확장자 없음)"
        super().__init__(
            f"[{self.code}] 이 파일 형식은 위키·본문 첨부로 읽을 수 없습니다: {label}. "
            f"지원: {_SUPPORTED_ATTACH}. "
            "Windows용 IRIS Setup(.exe) 다운로드·설치 문제와는 무관합니다. "
            f"설치 파일은 {_SETUP_HELP} 또는 GitHub Releases에서 받으세요."
        )
        self.suffix = suffix


_DOCUMENT_ERRORS = {
    "PDF_EMPTY": "PDF에 읽을 내용이 없습니다.",
    "PDF_ENCRYPTED": "암호화된 PDF입니다. 암호를 해제한 파일을 첨부하세요.",
    "PDF_CORRUPTED": "PDF 파일이 손상됐거나 올바른 PDF가 아닙니다.",
    "PDF_PAGE_LIMIT": "PDF 페이지가 너무 많습니다. 페이지 범위를 나누어 읽으세요.",
    "PDF_PAGE_RANGE_INVALID": "PDF 페이지 범위가 문서에 없습니다.",
    "PDF_RENDER_FAILED": "PDF 페이지를 렌더링하지 못했습니다.",
    "OCR_ENGINE_MISSING": "OCR 실행 파일을 찾을 수 없습니다. IRIS의 Tesseract 설치 안내를 확인하세요.",
    "OCR_LANGUAGE_MISSING": "OCR 언어팩이 없습니다. IRIS의 Tesseract 설치 안내를 확인하세요.",
    "OCR_TESSDATA_INVALID": "OCR 언어팩을 읽을 수 없습니다. Tesseract 언어팩을 다시 설치하세요.",
    "OCR_TIMEOUT": "OCR 처리 시간이 초과됐습니다.",
    "OCR_NO_TEXT": "스캔 PDF 또는 이미지에서 글자를 읽지 못했습니다.",
    "OCR_FAILED": "OCR 중 오류가 발생했습니다.",
    "VISION_FAILED": "비전 모델에서 내용을 읽지 못했습니다.",
    "EXTRACTION_CANCELLED": "문서 읽기가 취소되었습니다.",
    "FILE_NOT_FOUND": "파일이 삭제되었거나 경로가 존재하지 않습니다.",
    "FILE_ACCESS_DENIED": "파일을 읽을 권한이 없습니다.",
    "FILE_LOCKED": "파일이 다른 프로그램에서 잠겨 있습니다.",
    "EXTRACTION_LIMIT": "첨부 파일 크기 한도를 초과했습니다.",
}


class DocumentExtractionError(ValueError):
    def __init__(self, code: str, *, total_pages: int = 0, page_status: list[dict] | None = None) -> None:
        super().__init__(_DOCUMENT_ERRORS[code])
        self.code = code
        self.total_pages = total_pages
        self.page_status = page_status or []
        self.stage = "ocr" if code.startswith("OCR_") else "vision" if code.startswith("VISION_") else "extraction"
        self.recoverable = code not in {"PDF_CORRUPTED", "PDF_EMPTY"}


_SKIP_HTML = {"script", "style", "noscript", "nav", "header", "footer", "aside"}


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self._in_title = False
        self._chunks: list[str] = []
        self.title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_HTML:
            self._skip += 1
            return
        if tag == "title":
            self._in_title = True
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"):
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_HTML and self._skip:
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


def _truncate(text: str, *, limit: int | None = _MAX_CHARS) -> tuple[str, bool]:
    text = (text or "").strip()
    if limit is None or len(text) <= limit:
        return text, False
    cut = text[:limit].rsplit("\n", 1)[0].strip() or text[:limit]
    return cut + f"\n\n… (truncated at {limit} chars)", True


def readable_suffix(suffix: str) -> bool:
    """폴더 발췌에 넣을 글자 파일. 이미지는 쪽이 아니라 첨부일 때만."""
    low = (suffix or "").lower()
    return low in _TEXT_SUFFIXES or low in _CODE_SUFFIXES or low in _PDF_SUFFIXES or low in _OFFICE_SUFFIXES


def _letters(text: str) -> int:
    return len(re.findall(r"[0-9A-Za-z가-힣]", text or ""))


def _looks_like_url(source: str) -> bool:
    s = (source or "").strip()
    if not s:
        return False
    try:
        p = urlparse(s)
    except ValueError:
        return False
    return p.scheme in ("http", "https") and bool(p.netloc)


def _open_pypdf(path: Path):
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(str(path))
    except FileNotFoundError as exc:
        raise DocumentExtractionError("FILE_NOT_FOUND") from exc
    except (PdfReadError, ValueError, OSError) as exc:
        raise DocumentExtractionError("PDF_CORRUPTED") from exc
    if reader.is_encrypted:
        raise DocumentExtractionError("PDF_ENCRYPTED")
    return reader


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
    raise DocumentExtractionError("OCR_ENGINE_MISSING")


def _iris_tessdata_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home())
    return Path(base) / "iris" / "tesseract" / "tessdata"


def _system_tessdata_dir(tesseract_cmd: str) -> Path | None:
    root = Path(tesseract_cmd).resolve().parent
    cand = root / "tessdata"
    return cand if cand.is_dir() else None


def _installed_tessdata(tesseract_cmd: str) -> Path | None:
    prefix = os.environ.get("TESSDATA_PREFIX", "").strip()
    if prefix:
        directory = Path(prefix)
        if not directory.is_dir():
            raise DocumentExtractionError("OCR_TESSDATA_INVALID")
        return directory
    for directory in (_iris_tessdata_dir(), _system_tessdata_dir(tesseract_cmd)):
        if directory and all((directory / f"{lang}.traineddata").is_file() for lang in _TESSDATA_LANGS):
            return directory
    # The system installation can locate its compiled-in tessdata path on Linux.
    return None


def _ensure_tesseract() -> tuple[str, Path | None, frozenset[str]]:
    from subprocess import DEVNULL, PIPE, TimeoutExpired, run
    from iris.system.win_subprocess import no_window_kwargs

    global _tesseract_runtime
    with _ocr_setup_lock:
        if _tesseract_runtime is not None:
            return _tesseract_runtime
        cmd = _resolve_tesseract_cmd()
        tessdata = _installed_tessdata(cmd)
        command = [cmd, "--list-langs"]
        if tessdata is not None:
            command.extend(["--tessdata-dir", str(tessdata)])
        try:
            result = run(command, stdout=PIPE, stderr=DEVNULL, timeout=5, **no_window_kwargs())
        except TimeoutExpired as exc:
            raise DocumentExtractionError("OCR_TIMEOUT") from exc
        except OSError as exc:
            raise DocumentExtractionError("OCR_ENGINE_MISSING") from exc
        available = frozenset(result.stdout.decode("utf-8", errors="replace").splitlines())
        if not available.intersection(_TESSDATA_LANGS):
            raise DocumentExtractionError("OCR_LANGUAGE_MISSING")
        _tesseract_runtime = cmd, tessdata, available
        return _tesseract_runtime


def _page_png(page: object, *, dpi: int = 130) -> bytes:
    import pymupdf

    longest = max(float(page.rect.width), float(page.rect.height), 1.0)  # type: ignore[attr-defined]
    scale = min(dpi / 72, 4096 / longest)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale))  # type: ignore[attr-defined]
    return pix.tobytes("png")


def _ocr_png_bytes(png: bytes, *, language: str = "kor+eng") -> tuple[str, str]:
    """Bound the lifetime of the external OCR process."""
    from subprocess import PIPE, Popen, TimeoutExpired
    from tempfile import TemporaryFile
    from iris.system.win_subprocess import no_window_kwargs

    cancelled = _ocr_cancelled.get()
    if cancelled():
        return "", "EXTRACTION_CANCELLED"
    try:
        cmd, tessdata, available = _ensure_tesseract()
    except DocumentExtractionError as exc:
        return "", exc.code
    if not set(language.split("+")).issubset(available):
        return "", "OCR_LANGUAGE_MISSING"
    command = [cmd, "stdin", "stdout", "-l", language]
    if tessdata is not None:
        command.extend(["--tessdata-dir", str(tessdata)])
    deadline = monotonic() + 12
    with TemporaryFile() as source:
        source.write(png)
        for layout in ([], ["--psm", "6"]):
            if cancelled():
                return "", "EXTRACTION_CANCELLED"
            if monotonic() >= deadline:
                return "", "OCR_TIMEOUT"
            source.seek(0)
            try:
                proc = Popen(command + layout, stdin=source, stdout=PIPE, stderr=PIPE, **no_window_kwargs())
            except OSError:
                return "", "OCR_ENGINE_MISSING"
            with proc:
                while True:
                    try:
                        stdout, stderr = proc.communicate(timeout=0.15)
                        break
                    except TimeoutExpired:
                        error = "EXTRACTION_CANCELLED" if cancelled() else "OCR_TIMEOUT" if monotonic() >= deadline else ""
                        if error:
                            proc.kill()
                            proc.communicate()
                            return "", error
            if b"Failed loading language" in stderr:
                return "", "OCR_TESSDATA_INVALID"
            if proc.returncode:
                return "", "OCR_FAILED"
            text = stdout.decode("utf-8", errors="replace").strip()
            if text or b"Empty page!!" not in stderr:
                return text, ""
    return "", ""


def _ocr_for_document(png: bytes, language: str, cancelled) -> tuple[str, str]:
    token = _ocr_cancelled.set(cancelled)
    try:
        return _ocr_png_bytes(png) if language == "kor+eng" else _ocr_png_bytes(png, language=language)
    finally:
        _ocr_cancelled.reset(token)


def _page_window(
    total: int,
    *,
    page_from: int | None,
    page_to: int | None,
    page_limit: int | None,
) -> tuple[int, int]:
    """1-based inclusive deep-read window."""
    if page_from is not None or page_to is not None:
        start = max(1, int(page_from if page_from is not None else 1))
        end = min(total, int(page_to if page_to is not None else total))
        if start > end:
            start, end = end, start
        return start, min(end, total)
    end = total if not page_limit else min(total, max(0, int(page_limit)))
    return (1, end) if end >= 1 else (1, 0)


def _page_status(
    page: int,
    *,
    kind: str,
    chars: int = 0,
    has_images: bool = False,
    error: str = "",
) -> dict[str, object]:
    row = {
        "page": int(page),
        "kind": str(kind),
        "chars": int(chars),
        "has_images": bool(has_images),
        "error": _DOCUMENT_ERRORS.get(error, ""),
    }
    if error:
        row["error_code"] = error
    return row


def _incomplete_from_status(page_status: list[dict[str, object]], *, truncated: bool = False) -> bool:
    if truncated:
        return True
    bad = {"empty", "failed", "unread"}
    return any(str(row.get("kind") or "") in bad or row.get("error_code") for row in page_status)


def _read_pypdf_pages(path: Path, *, page_from, page_to, page_limit, cancelled) -> dict[str, object]:
    reader = _open_pypdf(path)
    total = len(reader.pages)
    if not total:
        raise DocumentExtractionError("PDF_EMPTY")
    if total > 4000:
        raise DocumentExtractionError("PDF_PAGE_LIMIT", total_pages=total)
    start, end = _page_window(total, page_from=page_from, page_to=page_to, page_limit=page_limit)
    if not 1 <= start <= end <= total:
        raise DocumentExtractionError("PDF_PAGE_RANGE_INVALID", total_pages=total)
    status = [_page_status(number, kind="unread") for number in range(1, total + 1)]
    parts = []
    for number in range(start, end + 1):
        if cancelled():
            raise DocumentExtractionError("EXTRACTION_CANCELLED", total_pages=total, page_status=status)
        from pypdf.errors import PdfReadError

        try:
            page = reader.pages[number - 1]
            text = str(page.extract_text() or "").strip()
            has_images = bool(page.images)
            error = "PDF_RENDER_FAILED" if has_images else "" if text else "PDF_EMPTY"
        except (PdfReadError, OSError, ValueError):
            text, has_images, error = "", False, "PDF_RENDER_FAILED"
        status[number - 1] = _page_status(number, kind="text" if text else "empty", chars=len(text),
                                          has_images=has_images, error=error)
        if text:
            parts.append(f"[쪽 {number}]\n{text}")
    if not parts:
        code = "PDF_RENDER_FAILED" if any(row.get("error_code") == "PDF_RENDER_FAILED" for row in status) else "PDF_EMPTY"
        raise DocumentExtractionError(code, total_pages=total, page_status=status)
    return {"text": "\n\n".join(parts), "total_pages": total, "page_status": status,
            "ocr_used": False, "vision_used": False, "incomplete": _incomplete_from_status(status)}


def read_pdf_pages(
    path: Path,
    *,
    page_limit: int | None = None,
    page_from: int | None = None,
    page_to: int | None = None,
    vision_reader=None,
    vision_all: bool = False,
    cancelled=lambda: False,
    ocr_language: str = "kor+eng",
) -> dict[str, object]:
    """Extract selected pages in order and keep failures with their own page."""
    fallback = {"page_from": page_from, "page_to": page_to, "page_limit": page_limit, "cancelled": cancelled}
    try:
        import pymupdf
    except ImportError:
        return _read_pypdf_pages(path, **fallback)

    if cancelled():
        raise DocumentExtractionError("EXTRACTION_CANCELLED")
    try:
        doc = pymupdf.open(str(path))
    except (FileNotFoundError, pymupdf.FileNotFoundError) as exc:
        raise DocumentExtractionError("FILE_NOT_FOUND") from exc
    except pymupdf.EmptyFileError as exc:
        raise DocumentExtractionError("PDF_EMPTY") from exc
    except PermissionError as exc:
        code = "FILE_LOCKED" if getattr(exc, "winerror", None) in (32, 33) else "FILE_ACCESS_DENIED"
        raise DocumentExtractionError(code) from exc
    except (pymupdf.FileDataError, RuntimeError):
        return _read_pypdf_pages(path, **fallback)

    with doc:
        if doc.needs_pass or doc.is_encrypted:
            raise DocumentExtractionError("PDF_ENCRYPTED")
        total = int(doc.page_count)
        if not total:
            raise DocumentExtractionError("PDF_EMPTY")
        start, end = _page_window(total, page_from=page_from, page_to=page_to, page_limit=page_limit)
        if not 1 <= start <= end <= total:
            raise DocumentExtractionError("PDF_PAGE_RANGE_INVALID", total_pages=total)
        # A bounded manifest keeps malformed or exceptionally long documents out of the model payload.
        if total > 4000:
            raise DocumentExtractionError("PDF_PAGE_LIMIT", total_pages=total)
        status = [_page_status(number, kind="unread") for number in range(1, total + 1)]
        parts: list[str] = []
        ocr_used = vision_used = False
        vision_calls = 0
        pypdf_fallback = None
        tried_pypdf = False
        for index in range(start - 1, end):
            if cancelled():
                raise DocumentExtractionError("EXTRACTION_CANCELLED", total_pages=total, page_status=status)
            page = doc[index]
            number = index + 1
            error = ""
            has_images = False
            layer = ""
            kind = "empty"
            body = ""
            try:
                layer = page.get_text().strip()
                has_images = bool(page.get_images())
                marks = page.get_bboxlog()
                if not layer and not has_images:
                    if not tried_pypdf:
                        tried_pypdf = True
                        try:
                            pypdf_fallback = _open_pypdf(path)
                        except DocumentExtractionError:
                            pass
                    if pypdf_fallback is not None:
                        layer = str(pypdf_fallback.pages[index].extract_text() or "").strip()
                if not layer and not has_images and not marks:
                    error = "PDF_EMPTY"
                elif layer and not has_images and (_letters(layer) >= _LAYER_MIN or all("text" in mark[0] for mark in marks)):
                    kind, body = "text", layer
                else:
                    png = _page_png(page)
                    ocr, error = _ocr_for_document(png, ocr_language, cancelled)
                    if cancelled():
                        raise DocumentExtractionError("EXTRACTION_CANCELLED", total_pages=total, page_status=status)
                    if _letters(ocr) >= _OCR_KEEP:
                        ocr_used = True
                        kind = "hybrid" if layer else "ocr"
                        body = layer + "\n\n" + ocr.strip() if layer else ocr.strip()
                    else:
                        error = (error if error in _DOCUMENT_ERRORS else "OCR_FAILED") if error else "OCR_NO_TEXT"
                        kind, body = ("text", layer) if layer else ("failed", "")
                        if vision_reader is not None and (vision_all or vision_calls < VISION_PAGE_CAP):
                            vision_calls += 1
                            try:
                                vision = str(vision_reader([png]) or "").strip()
                            except Exception:
                                error = "VISION_FAILED"
                            else:
                                if vision:
                                    kind, vision_used, error = "vision", True, ""
                                    body = layer + "\n\n[이미지]\n" + vision if layer else vision
            except DocumentExtractionError:
                raise
            except (RuntimeError, ValueError, OSError):
                kind, body, error = "failed", layer, "PDF_RENDER_FAILED"
            status[index] = _page_status(number, kind=kind, chars=len(body), has_images=has_images, error=error)
            if body:
                suffix = " 이미지" if kind == "vision" and not layer else ""
                parts.append(f"[쪽 {number}{suffix}]\n{body}")
        if cancelled():
            raise DocumentExtractionError("EXTRACTION_CANCELLED", total_pages=total, page_status=status)
        text = "\n\n".join(parts).strip()
        notes = []
        if page_from is not None or page_to is not None:
            notes.append(f"{start}–{end}쪽만 읽었습니다. 전체 {total}쪽.")
        elif end < total:
            notes.append(f"앞 {end}쪽만 읽었습니다. 전체 {total}쪽.")
        if not text:
            errors = [str(row["error_code"]) for row in status if row.get("error_code")]
            code = next((code for code in errors if code != "PDF_EMPTY"), "PDF_EMPTY")
            raise DocumentExtractionError(code, total_pages=total, page_status=status)
        return {
            "text": text,
            "ocr_used": ocr_used,
            "vision_used": vision_used,
            "note": " ".join(notes),
            "total_pages": total,
            "page_status": status,
            "incomplete": _incomplete_from_status(status),
        }


def extract_pdf_text(path: Path) -> str:
    data = read_pdf_pages(path)
    text = str(data.get("text") or "").strip()
    if not text:
        raise ValueError("OCR로 텍스트를 추출하지 못했습니다 (pdf-ocr).")
    return text


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


def html_to_article(html: str, *, url: str = "") -> tuple[str, str]:
    """본문 추출. trafilatura 가 글을 주면 그걸 쓰고, 아니면 메뉴를 뺀 표준 파서."""
    title, body = _trafilatura_article(html, url)
    if body.strip():
        if not title.strip():
            title = _stdlib_title(html)
        if not title.strip() and url:
            title = urlparse(url).netloc
        return title.strip() or "web page", body.strip()
    return _stdlib_article(html, url)


def _trafilatura_article(html: str, url: str) -> tuple[str, str]:
    try:
        import trafilatura
    except ImportError:
        return "", ""
    try:
        body = trafilatura.extract(
            html or "",
            url=url or None,
            include_comments=False,
            include_tables=True,
            favor_precision=True,
        ) or ""
        meta = trafilatura.extract_metadata(html or "")
        title = (getattr(meta, "title", None) or "") if meta is not None else ""
    except Exception:
        return "", ""
    return str(title or "").strip(), str(body or "").strip()


def _stdlib_title(html: str) -> str:
    parser = _HtmlTextExtractor()
    parser.feed(html or "")
    return parser.title.strip()


def _stdlib_article(html: str, url: str) -> tuple[str, str]:
    parser = _HtmlTextExtractor()
    parser.feed(html or "")
    title = parser.title.strip() or (urlparse(url).netloc if url else "") or "web page"
    return title, parser.text()


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
    title, body = html_to_article(html, url=url)
    if not body:
        raise ValueError("no readable text at URL")
    return title, body


def explicit_document_title(meta: str) -> str:
    """PDF/HTML 등 문서 안 제목. 한 글자·드라이브 문자 찌꺼기는 제목이 아니다."""
    text = " ".join((meta or "").replace("\x00", " ").split())
    if len(text) < 2 or text.casefold() in {"c", "c:"}:
        return ""
    return text


def _pdf_metadata_title(path: Path) -> str:
    try:
        from pypdf import PdfReader

        info = PdfReader(str(path)).metadata
        raw = str(getattr(info, "title", "") or "") if info is not None else ""
    except Exception:
        return ""
    return explicit_document_title(raw)


def source_display_title(path: Path, *, meta: str = "", text: str = "") -> str:
    """1) 문서 제목  2) 파일명  3) untitled."""
    title = explicit_document_title(meta)
    if not title and path.suffix.lower() in {".md", ".markdown"}:
        for line in (text or "").splitlines()[:12]:
            stripped = line.strip()
            if stripped.startswith("#"):
                title = explicit_document_title(stripped.lstrip("#").strip())
                if title:
                    break
    if title:
        return title
    return path.name or path.stem or "untitled"


def _png_bytes(raw: bytes) -> bytes:
    import io

    from PIL import Image

    image = Image.open(io.BytesIO(raw))
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _extract_ooxml(path: Path) -> str:
    import zipfile
    from xml.etree import ElementTree as ET

    suffix = path.suffix.lower()
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if suffix == ".docx":
            wanted = [name for name in names if name == "word/document.xml"]
        elif suffix == ".pptx":
            wanted = sorted(
                name for name in names if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            )
        elif suffix == ".xlsx":
            wanted = [name for name in names if name == "xl/sharedStrings.xml"]
        else:
            wanted = []
        chunks: list[str] = []
        for name in wanted:
            root = ET.fromstring(archive.read(name))
            bits: list[str] = []
            for el in root.iter():
                if not isinstance(el.tag, str):
                    continue
                if el.tag == "t" or el.tag.endswith("}t"):
                    value = (el.text or "").strip()
                    if value:
                        bits.append(value)
            if bits:
                chunks.append("\n".join(bits))
    text = "\n\n".join(chunks).strip()
    if not text:
        raise ValueError(f"{suffix} 파일에서 글자를 찾지 못했습니다.")
    return text


def extract_from_source(
    source: str,
    *,
    char_limit: int | None = _MAX_CHARS,
    page_limit: int | None = None,
    page_from: int | None = None,
    page_to: int | None = None,
    vision_reader=None,
    vision_all: bool = False,
    cancelled=lambda: False,
    ocr_language: str = "kor+eng",
) -> dict[str, object]:
    """파일 경로 또는 http(s) URL → {kind, title, text, source, truncated, …}.

    PDF는 total_pages / page_status / incomplete 를 함께 반환한다.
    char_limit 가 None 이면 위키 저장용으로 글자를 자르지 않는다.
    """
    src = (source or "").strip().strip('"').strip("'")
    if not src:
        raise ValueError("source required (file path or http(s) URL)")
    if cancelled():
        raise DocumentExtractionError("EXTRACTION_CANCELLED")

    if _looks_like_url(src):
        title, text = fetch_url_text(src)
        text, truncated = _truncate(text, limit=char_limit)
        return {
            "kind": "url",
            "title": title,
            "text": text,
            "source": src,
            "truncated": truncated,
            "incomplete": truncated,
        }

    path = Path(src).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"not a file: {src}")

    suffix = path.suffix.lower()
    if suffix in _HWP_SUFFIXES:
        raise ValueError("한글(HWP) 파일은 아직 본문을 읽지 못합니다.")

    if suffix in _PDF_SUFFIXES:
        data = read_pdf_pages(
            path,
            page_limit=page_limit,
            page_from=page_from,
            page_to=page_to,
            vision_reader=vision_reader,
            vision_all=vision_all,
            cancelled=cancelled,
            ocr_language=ocr_language,
        )
        text, truncated = _truncate(str(data.get("text") or ""), limit=char_limit)
        note = str(data.get("note") or "").strip()
        if note:
            text = f"{note}\n\n{text}"
        page_status = list(data.get("page_status") or [])
        incomplete = _incomplete_from_status(page_status, truncated=truncated)
        return {
            "kind": "pdf",
            "title": source_display_title(path, meta=_pdf_metadata_title(path), text=text),
            "text": text,
            "source": str(path.resolve()),
            "truncated": truncated,
            "ocr_used": bool(data.get("ocr_used")),
            "vision_used": bool(data.get("vision_used")),
            "note": note,
            "total_pages": int(data.get("total_pages") or 0),
            "page_status": page_status,
            "incomplete": incomplete,
        }

    if suffix in _OFFICE_SUFFIXES:
        text, truncated = _truncate(_extract_ooxml(path), limit=char_limit)
        return {
            "kind": "office",
            "title": source_display_title(path, text=text),
            "text": text,
            "source": str(path.resolve()),
            "truncated": truncated,
            "incomplete": truncated,
        }

    if suffix in _IMAGE_SUFFIXES:
        vision_used = False
        try:
            png = _png_bytes(path.read_bytes())
        except (OSError, ValueError) as exc:
            raise DocumentExtractionError("OCR_FAILED") from exc
        text, error = _ocr_for_document(png, ocr_language, cancelled)
        if cancelled():
            raise DocumentExtractionError("EXTRACTION_CANCELLED")
        if not text and vision_reader is not None:
            try:
                text = str(vision_reader([png]) or "").strip()
            except Exception as exc:
                raise DocumentExtractionError("VISION_FAILED") from exc
            vision_used = bool(text)
        if not text:
            raise DocumentExtractionError(error if error in _DOCUMENT_ERRORS else "OCR_NO_TEXT")
        text, truncated = _truncate(text, limit=char_limit)
        return {
            "kind": "image",
            "title": path.name,
            "text": text,
            "source": str(path.resolve()),
            "truncated": truncated,
            "vision_used": vision_used,
            "ocr_used": not vision_used,
            "incomplete": truncated,
        }

    if suffix in _TEXT_SUFFIXES or suffix in _CODE_SUFFIXES or suffix == "":
        text = path.read_text(encoding="utf-8", errors="replace")
        text, truncated = _truncate(text, limit=char_limit)
        return {
            "kind": "text",
            "title": source_display_title(path, text=text),
            "text": text,
            "source": str(path.resolve()),
            "truncated": truncated,
            "incomplete": truncated,
        }

    # F5: Setup 다운로드 「허용되지 않는 파일 형식」과 혼동 금지 — 첨부/위키 추출 전용 코드.
    raise UnsupportedAttachmentTypeError(suffix)
