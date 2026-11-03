"""Lecture PDF → practice script files (no Hermes body stuffing)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from iris.knowledge.content_extract import read_pdf_pages
from iris.runtime.attachment_context import MAX_FILE_BYTES, MAX_PDF_PAGES
from iris.system.project_ops import write_project_file

VisionReader = Callable[[bytes], str]


def collapse_ocr_gaps(text: str) -> str:
    """Drop OCR letter-spacing between Hangul so '실 습' ranks as '실습'."""
    return re.sub(r"(?<=[가-힣])\s+(?=[가-힣])", "", text or "")

_LABEL_RE = re.compile(
    r"(?m)^[ \t]*(?:프로그램[ \t]+)?(\d+)\s*[-–]\s*(\d+)(?:\.py)?[ \t]*$"
)
_PAGE_HDR_RE = re.compile(r"^\[쪽\s+(\d+)(?:\s+이미지)?\]\s*\n?", re.MULTILINE)

_CREATE_CUES = (
    "만들",
    "작성",
    "파일로",
    "덤프",
    "dump",
    "write",
    "create",
    "생성",
    "뽑아",
    "추출",
)
_LAB_CUES = (
    "실습",
    "프로그램",
    "lab",
    "practice",
    "스크립트",
    "script",
)
_EVERY_CUES = ("전부", "모두", "모든", "every", "all", "다 ")
_EXCLUDE = (
    "위키",
    "wiki",
    "pdf로 저장",
    "pdf 저장",
    "note.export",
)


@dataclass(frozen=True)
class LabProgram:
    """One practice block carved from PDF page text."""

    label: str
    filename: str
    body: str
    pages: tuple[int, ...]


@dataclass(frozen=True)
class LabDumpResult:
    """In-process dump outcome. programs may hold bodies; strip before Hermes."""

    programs: tuple[LabProgram, ...]
    written: tuple[str, ...]
    errors: tuple[str, ...]
    truncated_pages: bool
    source_pdf: str = ""


@dataclass(frozen=True)
class LabDumpSummary:
    """Wire / Hermes-facing payload. Invariant: no bodies, no page text."""

    written: tuple[str, ...]
    labels: tuple[str, ...]
    count: int
    truncated_pages: bool
    errors: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "written": list(self.written),
            "labels": list(self.labels),
            "count": self.count,
            "truncated_pages": self.truncated_pages,
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class LabDumpReply:
    """Thin UI payload: path list only."""

    user_visible: str
    written_rel_paths: tuple[str, ...]
    had_errors: bool


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def is_lab_dump_intent(text: str, pdf_paths: Sequence[str] = ()) -> bool:
    """True when user asks to materialize lab/practice scripts from an attached PDF."""
    if not pdf_paths:
        return False
    t = _norm(text)
    if not t:
        return False
    if any(w in t for w in _EXCLUDE):
        return False
    lab = any(w in t for w in _LAB_CUES)
    create = any(w in t for w in _CREATE_CUES)
    every = any(w in t for w in _EVERY_CUES)
    if lab and create:
        return True
    if lab and every:
        return True
    return False


def pdf_paths_from(attachments: Sequence[str]) -> tuple[str, ...]:
    """Filter chip paths to existing .pdf files. Order preserved."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in attachments or ():
        key = str(raw or "").strip().strip('"').strip("'")
        if not key:
            continue
        path = Path(key).expanduser()
        if path.suffix.lower() != ".pdf" or not path.is_file():
            continue
        resolved = str(path.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(resolved)
    return tuple(out)


def filename_for_label(label: str) -> str:
    """Map PDF label → safe single-segment basename (e.g. '프로그램 7-7' → '7-7.py')."""
    s = (label or "").strip()
    m = re.search(r"(\d+)\s*[-–]\s*(\d+)", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}.py"
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s)
    base = re.sub(r"\s+", "_", base).strip("._") or "lab"
    if base.lower().endswith(".py"):
        return base
    return f"{base}.py"


def parse_lab_programs(page_texts: Sequence[str]) -> list[LabProgram]:
    """Split page texts into LabProgram list. Pure. No I/O."""
    pieces: list[tuple[int, str]] = []
    for index, raw in enumerate(page_texts or ()):
        text = collapse_ocr_gaps(raw or "")
        hdr = _PAGE_HDR_RE.match(text)
        if hdr:
            page = int(hdr.group(1))
            body = text[hdr.end() :]
        else:
            page = index + 1
            body = text
        pieces.append((page, body))

    parts: list[str] = []
    page_at: list[tuple[int, int]] = []
    offset = 0
    for page, body in pieces:
        page_at.append((offset, page))
        parts.append(body)
        offset += len(body) + 2
    blob = "\n\n".join(parts)

    def page_for(pos: int) -> int:
        cur = page_at[0][1] if page_at else 1
        for start, page in page_at:
            if start <= pos:
                cur = page
            else:
                break
        return cur

    matches = list(_LABEL_RE.finditer(blob))
    programs: list[LabProgram] = []
    for idx, match in enumerate(matches):
        num = f"{match.group(1)}-{match.group(2)}"
        raw_label = match.group(0).strip()
        label = raw_label if raw_label else num
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(blob)
        body = blob[start:end].strip()
        pages = sorted({page_for(match.start()), page_for(max(start, end - 1))})
        programs.append(
            LabProgram(
                label=label,
                filename=filename_for_label(label),
                body=body,
                pages=tuple(pages),
            )
        )
    return programs


def _as_list_vision(reader: VisionReader | None):
    if reader is None:
        return None

    def _wrap(pngs, _read=reader):
        parts: list[str] = []
        for png in pngs:
            try:
                parts.append(str(_read(png) or "").strip())
            except Exception:
                parts.append("")
        return "\n".join(part for part in parts if part)

    return _wrap


def extract_pdf_page_texts(
    pdf_path: Path | str,
    *,
    page_limit: int | None = None,
    vision_reader: VisionReader | None = None,
) -> tuple[list[str], bool]:
    """Page-by-page extract via read_pdf_pages. Honors MAX_PDF_PAGES."""
    path = Path(pdf_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {path}")
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(f"PDF exceeds MAX_FILE_BYTES ({MAX_FILE_BYTES})")
    limit = MAX_PDF_PAGES if page_limit is None else int(page_limit)
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError("PDF에 pymupdf가 필요합니다 — pip install pymupdf") from exc
    doc = pymupdf.open(str(path))
    try:
        total = int(doc.page_count)
    finally:
        doc.close()
    data = read_pdf_pages(
        path,
        page_limit=limit,
        vision_reader=_as_list_vision(vision_reader),
    )
    text = str(data.get("text") or "").strip()
    if not text:
        return [], total > limit
    chunks = re.split(r"(?=^\[쪽\s+\d+)", text, flags=re.MULTILINE)
    page_texts = [chunk.strip() for chunk in chunks if chunk.strip()]
    return page_texts, total > limit


def dump_lab_scripts(
    pdf_path: Path | str,
    project_root: Path | str,
    *,
    page_limit: int | None = None,
    out_subdir: str = "labs",
    vision_reader: VisionReader | None = None,
) -> LabDumpResult:
    """Extract → parse → write_project_file. Never returns bodies for model stuffing."""
    path = Path(pdf_path).expanduser()
    root = Path(project_root).expanduser()
    errors: list[str] = []
    try:
        page_texts, truncated = extract_pdf_page_texts(
            path,
            page_limit=page_limit,
            vision_reader=vision_reader,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        return LabDumpResult(
            programs=(),
            written=(),
            errors=(str(exc),),
            truncated_pages=False,
            source_pdf=str(path),
        )
    programs = parse_lab_programs(page_texts)
    if not programs:
        errors.append("PDF에서 실습 프로그램 라벨을 찾지 못했습니다.")
    written: list[str] = []
    sub = (out_subdir or "").strip().strip("/\\")
    by_name: dict[str, LabProgram] = {}
    for prog in programs:
        by_name[prog.filename] = prog
    for prog in by_name.values():
        if not (prog.body or "").strip():
            errors.append(f"{prog.filename}: 본문이 비어 저장하지 않았습니다.")
            continue
        rel = f"{sub}/{prog.filename}" if sub else prog.filename
        rel = rel.replace("\\", "/")
        try:
            out = write_project_file(root, rel, prog.body)
            if out.get("error"):
                errors.append(f"{rel}: {out['error']}")
                continue
            written.append(str(out.get("rel_path") or rel).replace("\\", "/"))
        except (OSError, ValueError) as exc:
            errors.append(f"{rel}: {exc}")
    return LabDumpResult(
        programs=tuple(programs),
        written=tuple(written),
        errors=tuple(errors),
        truncated_pages=truncated,
        source_pdf=str(path),
    )


def format_lab_dump_reply(result: LabDumpResult) -> LabDumpReply:
    """Short Iris reply: written path bullets + error lines. No code bodies."""
    lines: list[str] = []
    if result.written:
        lines.append("실습 스크립트를 저장했습니다.")
        lines.append("")
        for rel in result.written:
            lines.append(f"- `{rel}`")
    else:
        lines.append("저장한 실습 스크립트가 없습니다.")
    if result.truncated_pages:
        lines.append("")
        lines.append(f"(PDF 앞 {MAX_PDF_PAGES}쪽만 읽었습니다.)")
    if result.errors:
        lines.append("")
        lines.append("오류:")
        for err in result.errors:
            lines.append(f"- {err}")
    return LabDumpReply(
        user_visible="\n".join(lines).strip(),
        written_rel_paths=tuple(result.written),
        had_errors=bool(result.errors),
    )


def to_hermes_summary(result: LabDumpResult) -> LabDumpSummary:
    """Boundary strip: drop bodies before any tool result reaches the model."""
    labels = tuple(p.label for p in result.programs)
    return LabDumpSummary(
        written=tuple(result.written),
        labels=labels,
        count=len(result.written),
        truncated_pages=bool(result.truncated_pages),
        errors=tuple(result.errors),
    )


def try_handle_lab_dump(
    text: str,
    attachments: Sequence[str],
    project_root: str,
    *,
    vision_reader: VisionReader | None = None,
    out_subdir: str = "labs",
) -> LabDumpReply | None:
    """Facade for non-Qt callers/tests. None if not lab-dump intent or no PDF."""
    pdfs = pdf_paths_from(attachments)
    if not is_lab_dump_intent(text or "", pdfs):
        return None
    if not project_root:
        return LabDumpReply(
            user_visible="프로젝트를 연 뒤 다시 요청해 주세요.",
            written_rel_paths=(),
            had_errors=True,
        )
    result = dump_lab_scripts(
        pdfs[0],
        project_root,
        out_subdir=out_subdir,
        vision_reader=vision_reader,
    )
    return format_lab_dump_reply(result)
