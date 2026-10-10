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
_TESSDATA_LANGS = ("eng", "osd", "kor")
_TESSDATA_URL = "https://github.com/tesseract-ocr/tessdata/raw/main/{lang}.traineddata"
_WIN_TESSERACT_CANDIDATES = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)
_tesseract_ready = False
_tessdata_dir: Path | None = None
_ocr_unavailable = ""

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


def _hide_tesseract_console(pytesseract: object) -> None:
    """tesseract.exe는 콘솔 프로그램이라 SW_HIDE만으로는 창이 깜빡인다."""
    module = pytesseract.pytesseract  # type: ignore[attr-defined]
    if getattr(module, "_iris_no_window", False):
        return
    original = module.subprocess_args

    def _args(include_stdout: bool = True) -> dict:
        kwargs = original(include_stdout)
        from iris.system.win_subprocess import no_window_kwargs

        kwargs.update(no_window_kwargs())
        return kwargs

    module.subprocess_args = _args
    module._iris_no_window = True


def _configure_tesseract(pytesseract: object) -> None:
    global _tessdata_dir
    _hide_tesseract_console(pytesseract)
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


def _page_png(page: object, *, dpi: int = 130) -> bytes:
    pix = page.get_pixmap(dpi=dpi)  # type: ignore[attr-defined]
    return pix.tobytes("png")


def _ocr_png_bytes(png: bytes) -> tuple[str, str]:
    """(text, error). Tesseract가 없어도 예외를 올리지 않는다."""
    global _ocr_unavailable
    if _ocr_unavailable:
        return "", _ocr_unavailable
    import io

    try:
        _ensure_tesseract()
        import pytesseract
        from PIL import Image
    except (RuntimeError, ImportError) as exc:
        _ocr_unavailable = str(exc)
        return "", _ocr_unavailable
    tess_cfg = f"--tessdata-dir {_tessdata_dir.as_posix()}" if _tessdata_dir else ""
    try:
        image = Image.open(io.BytesIO(png))
        text = pytesseract.image_to_string(image, lang="kor+eng", config=tess_cfg).strip()
    except Exception as exc:  # noqa: BLE001
        return "", str(exc)
    return text, ""


def read_pdf_pages(
    path: Path,
    *,
    page_limit: int | None = None,
    vision_reader=None,
    vision_all: bool = False,
) -> dict[str, str | bool]:
    """쪽마다 글자 층 → OCR → (있으면) 비전. 본문이 없으면 ValueError.

    vision_all 이면 글자 층·OCR이 비는 쪽을 세고, 한 장씩 순서대로 읽는다.
    끄면 채팅 발췌처럼 최대 VISION_PAGE_CAP 장을 한 번에 보낸다.
    """
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError("PDF에 pymupdf가 필요합니다 — pip install pymupdf") from exc

    page_texts: list[str] = []
    try:
        from pypdf import PdfReader

        page_texts = [(page.extract_text() or "") for page in PdfReader(str(path)).pages]
    except Exception as exc:
        low = str(exc).lower()
        if "password" in low or "encrypted" in low:
            raise ValueError("암호가 걸린 PDF는 읽지 못했습니다.") from exc
        page_texts = []

    doc = pymupdf.open(str(path))
    try:
        total = int(doc.page_count)
        limit = total if not page_limit else min(total, int(page_limit))
        parts: list[str] = []
        vision: list[bytes] = []
        vision_indexes: list[int] = []
        ocr_used = False
        ocr_error = ""
        vision_needed = 0
        short_layers: list[tuple[int, str]] = []
        for index in range(limit):
            raw = page_texts[index] if index < len(page_texts) else ""
            layer = raw.strip()
            if _letters(layer) >= _LAYER_MIN:
                parts.append(f"[쪽 {index + 1}]\n{layer}")
                continue
            png = _page_png(doc[index])
            ocr_text, err = _ocr_png_bytes(png)
            if err:
                ocr_error = ocr_error or err
            if _letters(ocr_text) >= _OCR_KEEP:
                ocr_used = True
                parts.append(f"[쪽 {index + 1}]\n{ocr_text.strip()}")
                continue
            if layer:
                short_layers.append((index + 1, layer))
            if vision_reader is None:
                if layer:
                    parts.append(f"[쪽 {index + 1}]\n{layer}")
                else:
                    vision_needed += 1
                continue
            vision_needed += 1
            if vision_all:
                one = ""
                try:
                    one = str(vision_reader([png]) or "").strip()
                except Exception as exc:  # noqa: BLE001
                    ocr_error = ocr_error or str(exc)
                if one:
                    parts.append(f"[쪽 {index + 1} 이미지]\n{one}")
                elif layer:
                    parts.append(f"[쪽 {index + 1}]\n{layer}")
                continue
            if len(vision) < VISION_PAGE_CAP:
                vision.append(png)
                vision_indexes.append(index + 1)
        vision_used = any(part.startswith("[쪽 ") and " 이미지]" in part.split("\n", 1)[0] for part in parts)
        if vision and vision_reader is not None:
            try:
                transcribed = str(vision_reader(vision) or "").strip()
            except Exception as exc:  # noqa: BLE001
                transcribed = ""
                ocr_error = ocr_error or str(exc)
            if transcribed:
                vision_used = True
                label = ", ".join(str(number) for number in vision_indexes)
                parts.append(f"[쪽 {label} 이미지]\n{transcribed}")
            else:
                for number, layer in short_layers:
                    parts.append(f"[쪽 {number}]\n{layer}")
        text = "\n\n".join(part for part in parts if part.strip()).strip()
        notes: list[str] = []
        if page_limit and total > limit:
            notes.append(f"앞 {limit}쪽만 읽었습니다. 전체 {total}쪽.")
        if vision_needed and not vision_used and vision_reader is None:
            notes.append(
                f"글자가 없는 이미지 쪽 {vision_needed}장은 OCR이 비어 있고, 비전 읽기가 없습니다."
            )
        if not text:
            reason = ocr_error or "이미지로만 된 PDF에서 글자를 읽지 못했습니다."
            if notes:
                reason = f"{reason} {' '.join(notes)}"
            raise ValueError(reason)
        return {
            "text": text,
            "ocr_used": ocr_used,
            "vision_used": vision_used,
            "note": " ".join(notes),
        }
    finally:
        doc.close()


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
    vision_reader=None,
    vision_all: bool = False,
) -> dict[str, str | bool]:
    """파일 경로 또는 http(s) URL → {kind, title, text, source, truncated}.

    char_limit 가 None 이면 위키 저장용으로 글자를 자르지 않는다.
    """
    src = (source or "").strip().strip('"').strip("'")
    if not src:
        raise ValueError("source required (file path or http(s) URL)")

    if _looks_like_url(src):
        title, text = fetch_url_text(src)
        text, truncated = _truncate(text, limit=char_limit)
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
    if suffix in _HWP_SUFFIXES:
        raise ValueError("한글(HWP) 파일은 아직 본문을 읽지 못합니다.")

    if suffix in _PDF_SUFFIXES:
        data = read_pdf_pages(
            path,
            page_limit=page_limit,
            vision_reader=vision_reader,
            vision_all=vision_all,
        )
        text, truncated = _truncate(str(data.get("text") or ""), limit=char_limit)
        note = str(data.get("note") or "").strip()
        if note:
            text = f"{note}\n\n{text}"
        return {
            "kind": "pdf",
            "title": source_display_title(path, meta=_pdf_metadata_title(path), text=text),
            "text": text,
            "source": str(path.resolve()),
            "truncated": truncated,
            "ocr_used": bool(data.get("ocr_used")),
            "vision_used": bool(data.get("vision_used")),
            "note": note,
        }

    if suffix in _OFFICE_SUFFIXES:
        text, truncated = _truncate(_extract_ooxml(path), limit=char_limit)
        return {
            "kind": "office",
            "title": source_display_title(path, text=text),
            "text": text,
            "source": str(path.resolve()),
            "truncated": truncated,
        }

    if suffix in _IMAGE_SUFFIXES:
        if vision_reader is None:
            raise ValueError("이미지 파일이라 글자 층이 없습니다. 비전 읽기가 연결되어 있지 않습니다.")
        try:
            png = _png_bytes(path.read_bytes())
            text = str(vision_reader([png]) or "").strip()
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"이미지에서 내용을 읽지 못했습니다: {exc}") from exc
        if len(text) < 8:
            raise ValueError("이미지에서 내용을 읽지 못했습니다.")
        text, truncated = _truncate(text, limit=char_limit)
        return {
            "kind": "image",
            "title": path.name,
            "text": text,
            "source": str(path.resolve()),
            "truncated": truncated,
            "vision_used": True,
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
        }

    # F5: Setup 다운로드 「허용되지 않는 파일 형식」과 혼동 금지 — 첨부/위키 추출 전용 코드.
    raise UnsupportedAttachmentTypeError(suffix)
