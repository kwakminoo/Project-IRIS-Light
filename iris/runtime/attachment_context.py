"""Read explicitly attached inputs in IRIS, never ask an agent to read host paths."""
from __future__ import annotations

import contextvars
import hashlib
import csv
import heapq
import json
import logging
import mimetypes
import os
import posixpath
import re
import uuid
import zipfile
from logging.handlers import RotatingFileHandler
from dataclasses import asdict, dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

log = logging.getLogger("iris.attachments")


def trace(stage: str, **fields) -> None:
    """Metadata/hash diagnostics only; never log document bodies or credentials."""
    if not log.handlers:
        try:
            directory = Path(os.environ.get("IRIS_ATTACHMENT_LOG_DIR", str(Path.home() / ".iris-light" / "logs")))
            directory.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(directory / "attachments.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            log.addHandler(handler)
            log.setLevel(logging.INFO)
        except OSError:
            pass
    log.info("stage=%s %s", stage, json.dumps(fields, ensure_ascii=False))


def trace_payload(backend: str, payload: dict) -> None:
    wire = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    trace("request", backend=backend, keys=list(payload), bytes=len(wire), sha256=hashlib.sha256(wire).hexdigest(),
          messages=[{"role": m.get("role"), "chars": len(str(m.get("content", ""))),
                     "attachment_data": "IRIS supplied attachment data" in str(m.get("content", ""))} for m in payload.get("messages", [])])


MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_EXPANDED_BYTES = 40 * 1024 * 1024
MAX_CONTEXT_CHARS = 24000
MAX_FILES = 50
MAX_FOLDER_ENTRIES = 2000
MAX_PDF_PAGES = 200
EXCLUDED = {"node_modules", ".git", "dist", "build", "out", "target", "venv", ".venv", "__pycache__", ".cache", "coverage", ".next", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
TEXT_EXTENSIONS = set("txt md markdown json csv tsv py pyw js jsx ts tsx html htm css scss xml yaml yml toml ini cfg conf log sql sh bash ps1 bat cmd c h cpp hpp cs java kt kts go rs rb php swift r vue svelte tex ipynb dockerfile gitignore env example".split())
TEXT_FILENAMES = {"dockerfile", "makefile", "license", ".gitignore", ".env"}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff"}
_image_reader: contextvars.ContextVar = contextvars.ContextVar("iris_chat_image_reader", default=None)
MIME_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf", "txt": "text/plain", "md": "text/markdown",
    "json": "application/json", "csv": "text/csv",
}


def _is_link(path: Path) -> bool:
    # pathlib.is_junction was added in 3.12; IRIS also supports Python 3.11.
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _compact_page_status(rows: list | None) -> list[dict]:
    """Model-facing page_status: page/kind/chars/has_images (+ short error)."""
    out: list[dict] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        entry = {
            "page": int(row.get("page") or 0),
            "kind": str(row.get("kind") or "unread"),
            "chars": int(row.get("chars") or 0),
            "has_images": bool(row.get("has_images")),
        }
        from iris.knowledge.content_extract import _DOCUMENT_ERRORS

        code = str(row.get("error_code") or "").strip()
        if code in _DOCUMENT_ERRORS:
            entry.update(error_code=code, error=_DOCUMENT_ERRORS[code])
        out.append(entry)
    return out


@dataclass
class Attachment:
    id: str
    path: str  # Host-only; never serialized into inference messages.
    filename: str
    mime_type: str
    size: int = 0
    text: str = ""
    error: str = ""
    truncated: bool = False
    relative_path: str = ""
    extension: str = ""
    modified_time: float = 0
    folder_root: str = ""
    attachment_id: str = ""
    extracted_text: bool = False
    total_pages: int = 0
    page_status: list = field(default_factory=list)
    incomplete: bool = False
    error_code: str = ""

    def payload(self) -> dict:
        result = asdict(self)
        result.pop("path")
        result.pop("folder_root")
        if result.get("page_status"):
            result["page_status"] = _compact_page_status(result.get("page_status"))
        return result


@dataclass
class PreparedAttachments:
    attachments: list[Attachment]

    @property
    def notices(self) -> list[str]:
        return [f"{a.filename}: {a.error}" for a in self.attachments if a.error]

    def model_content(self, question: str) -> str:
        blocks = []
        # Put the index before the evidence. Document bodies stay readable,
        # rather than becoming one long JSON string with escaped newlines.
        folders = [a for a in self.attachments if a.mime_type == "inode/directory"]
        files = [a for a in self.attachments if a.mime_type != "inode/directory"]
        # Retrieval returns strongest evidence first; place it closest to the
        # final question, after the index and less relevant supporting files.
        for item in folders + list(reversed(files)):
            metadata = item.payload()
            body = metadata.pop("text")
            source = item.relative_path or item.filename
            from iris.system.execution_policy import format_attachment_payload_for_model

            # U03: shared untrusted packer (cite markers preserved for grounding).
            packed = format_attachment_payload_for_model(source, body)
            blocks.append(
                "Attachment source: " + source + "\n"
                + "Attachment metadata: " + json.dumps(metadata, ensure_ascii=False)
                + "\n" + packed
            )
        return question + _ATTACHMENT_SECTION + "\n\n".join(blocks) \
            + "\n\nUse extracted file text as evidence and cite the relevant relative filenames. " \
            + "Do not guess file contents from the index alone. " \
            + "PDF metadata may include attachment_id, total_pages, page_status, incomplete. " \
            + "When incomplete or truncated, call content_extract with attachment_id and relative_path if inside a folder, " \
            + "and page_from/page_to; do not claim a full read.\nUser question:\n" + question


def bind_chat_image_reader(reader):
    """채팅 턴의 비전 읽기. 워커 스레드에서 set 하고 끝나면 reset."""
    return _image_reader.set(reader)


def reset_chat_image_reader(token) -> None:
    _image_reader.reset(token)


def _ocr_image(path: Path) -> str:
    """Try local extraction and OCR before asking a vision model."""
    from iris.knowledge.content_extract import DocumentExtractionError, _DOCUMENT_ERRORS, _ocr_png_bytes, _png_bytes
    from iris.knowledge.grid_extract import extract_binary_grid, format_grid_attachment_text

    try:
        structured = extract_binary_grid(path)
    except Exception:
        structured = None
    if structured and structured.get("grids"):
        return format_grid_attachment_text(structured)

    try:
        raw = path.read_bytes()
        png = _png_bytes(raw)
    except Exception as exc:
        raise DocumentExtractionError("OCR_FAILED") from exc
    text, err = _ocr_png_bytes(png)
    if text.strip():
        return text.strip()
    if err == "EXTRACTION_CANCELLED":
        raise DocumentExtractionError(err)
    reader = _image_reader.get()
    if reader is not None:
        try:
            seen = str(reader(png) or "").strip()
        except Exception:
            seen = ""
        if len(seen) >= 8:
            return seen
    raise DocumentExtractionError(err if err in _DOCUMENT_ERRORS else "OCR_NO_TEXT")


def collapse_ocr_gaps(text: str) -> str:
    """Drop OCR letter-spacing between Hangul so '실 습' ranks as '실습'."""
    return re.sub(r"(?<=[가-힣])\s+(?=[가-힣])", "", text or "")


def query_terms(query: str) -> set[str]:
    terms = {
        s.casefold()
        for s in re.findall(
            r"[A-Za-z_][A-Za-z0-9_.-]*|[가-힣]{2,}|\d+(?:-\d+)+|\d{2,}",
            query,
        )
    }
    if "로그인" in query:
        terms.update({"login", "signin", "authenticate"})
    return terms


def _pdf_list_vision(reader):
    """Chat `_image_reader` takes one PNG; `read_pdf_pages` passes a list."""
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


def _extract_pdf(path: Path, *, cancelled=lambda: False) -> tuple[str, dict]:
    """Deep-read PDF once; return body text + manifest for the model."""
    from iris.knowledge.content_extract import read_pdf_pages

    data = read_pdf_pages(
        path,
        page_limit=MAX_PDF_PAGES,
        vision_reader=_pdf_list_vision(_image_reader.get()),
        cancelled=cancelled,
    )
    text = str(data.get("text") or "").strip()
    meta = {
        "total_pages": int(data.get("total_pages") or 0),
        "page_status": list(data.get("page_status") or []),
        "incomplete": bool(data.get("incomplete")),
    }
    return text, meta


def _relevant_chunks(text: str, budget: int, query: str) -> str:
    """Bound large text with numbered chunks ranked by the user's query."""
    chunks = [text[i:i + 3000] for i in range(0, len(text), 3000)]
    terms = query_terms(query)
    ranked = sorted(range(len(chunks)), key=lambda i: (-sum(chunks[i].casefold().count(t) for t in terms), i))
    selected = []
    used = 0
    for index in ranked:
        part = f"[Chunk {index + 1}/{len(chunks)}]\n{chunks[index]}"
        if used + len(part) + 1 > budget:
            continue
        selected.append((index, part))
        used += len(part) + 1
    if not selected:
        return text[:budget]
    return "\n".join(part for _, part in sorted(selected))


def _office_parts(path: Path):
    with zipfile.ZipFile(path) as archive:
        if sum(i.file_size for i in archive.infolist()) > MAX_EXPANDED_BYTES:
            raise ValueError("압축 해제된 문서가 너무 큽니다 (최대 40 MB).")
        names = archive.namelist()
        if path.suffix.lower() == ".docx":
            names = [n for n in names if n == "word/document.xml" or re.fullmatch(r"word/(header|footer)\d+\.xml", n)]
            for name in sorted(names):
                root = ET.fromstring(archive.read(name))
                body = next((node for node in root if node.tag.endswith("}body")), root)
                for node in body:
                    if node.tag.endswith("}tbl"):
                        yield "Table:\n" + "\n".join(" | ".join(
                            " ".join(t.text or "" for t in cell.iter() if t.tag.endswith("}t"))
                            for cell in row if cell.tag.endswith("}tc"))
                            for row in node if row.tag.endswith("}tr"))
                    elif node.tag.endswith("}p"):
                        yield " ".join(t.text or "" for t in node.iter() if t.tag.endswith("}t"))
        elif path.suffix.lower() == ".pptx":
            # Use presentation relationships for slide order, not ZIP order.
            rels = ET.fromstring(archive.read("ppt/_rels/presentation.xml.rels"))
            targets = {r.attrib["Id"]: r.attrib["Target"] for r in rels}
            presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
            slides = [s for s in presentation.iter() if s.tag.endswith("}sldId")]
            for index, slide in enumerate(slides, 1):
                rid = next(v for k, v in slide.attrib.items() if k.endswith("}id"))
                target = targets[rid]
                name = target.lstrip("/") if target.startswith("/") else posixpath.normpath("ppt/" + target)
                root = ET.fromstring(archive.read(name))
                yield f"Slide {index}\n" + "\n".join(t.text or "" for t in root.iter() if t.tag.endswith("}t"))
        else:
            shared = []
            if "xl/sharedStrings.xml" in names:
                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                shared = ["".join(t.text or "" for t in s.iter() if t.tag.endswith("}t")) for s in root]
            rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {r.attrib["Id"]: r.attrib["Target"] for r in rels}
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            for sheet in (s for s in workbook.iter() if s.tag.endswith("}sheet")):
                rid = next(v for k, v in sheet.attrib.items() if k.endswith("}id"))
                target = targets[rid]
                name = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
                root = ET.fromstring(archive.read(name))
                yield "Sheet: " + sheet.attrib["name"]
                for row in (r for r in root.iter() if r.tag.endswith("}row")):
                    cells = []
                    for cell in row:
                        value = "".join(t.text or "" for t in cell if t.tag.endswith("}v"))
                        if cell.attrib.get("t") == "s":
                            value = shared[int(value)] if value else ""
                        elif cell.attrib.get("t") == "inlineStr":
                            value = "".join(t.text or "" for t in cell.iter() if t.tag.endswith("}t"))
                        formula = next((t.text for t in cell if t.tag.endswith("}f")), None)
                        cells.append(f"{cell.attrib.get('r', '')}: {value}" + (f" (formula: {formula})" if formula else ""))
                    yield "\t".join(cells)


def _parts(path: Path):
    extension = path.suffix.lower().lstrip(".")
    if extension in {"csv", "tsv"}:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = csv.reader(handle, delimiter="\t" if extension == "tsv" else ",")
            for index, row in enumerate(rows):
                yield ("Columns: " if index == 0 else f"Row {index}: ") + json.dumps(row, ensure_ascii=False)
        return
    if extension in TEXT_EXTENSIONS or path.name.lower() in TEXT_FILENAMES:
        with path.open("rb") as handle:
            prefix = handle.read(4)
        # Validate in a streaming pass before yielding (a failed UTF-8 decode
        # must not leave duplicate prefixes when falling back to CP949).
        encodings = ("utf-16",) if prefix.startswith((b"\xff\xfe", b"\xfe\xff")) else ("utf-8-sig", "cp949")
        for encoding in encodings:
            try:
                with path.open("r", encoding=encoding) as handle:
                    read = 0
                    while text := handle.read(3000):
                        read += len(text)
                        if read > MAX_FILE_BYTES:
                            raise ValueError("읽는 중 파일 크기가 한도를 초과했습니다.")
                        if "\x00" in text:
                            raise ValueError("텍스트 파일에 바이너리 데이터가 포함되어 있습니다.")
                with path.open("r", encoding=encoding) as handle:
                    read = 0
                    while text := handle.read(3000):
                        read += len(text)
                        if read > MAX_FILE_BYTES or "\x00" in text:
                            raise ValueError("파일이 읽는 중 변경되었거나 한도를 초과했습니다.")
                        yield text
                return
            except UnicodeDecodeError:
                pass
        raise ValueError("텍스트 인코딩을 읽을 수 없습니다 (UTF-8, UTF-16, CP949 지원).")
    elif extension == "pdf":
        text, _meta = _extract_pdf(path)
        yield text
    elif extension in {"docx", "pptx", "xlsx"}:
        yield from _office_parts(path)
    elif extension in IMAGE_EXTENSIONS:
        yield _ocr_image(path)
    else:
        raise ValueError(f"현재 이 파일 형식은 지원하지 않습니다 (.{extension or '확장자 없음'}).")


def _document_chunks(path: Path):
    pending = ""
    for part in _parts(path):
        # Small paragraphs/cells share a chunk; retain source page/slide labels.
        for offset in range(0, len(part), 3000):
            pending += part[offset:offset + 3000]
            while len(pending) >= 3000:
                yield pending[:3000]
                pending = pending[3000:]
        pending += "\n"
    if pending.strip():
        yield pending


def _budget_select_text(text: str, *, budget: int, query: str = "") -> tuple[str, bool]:
    """Query-aware char budget (same heap policy as multi-part documents)."""
    terms = query_terms(query)
    selected = []
    total = 0
    count = 0
    capacity = max(1, budget // 3100)
    pending = ""
    for offset in range(0, len(text), 3000):
        pending += text[offset : offset + 3000]
        while len(pending) >= 3000:
            chunk = pending[:3000]
            pending = pending[3000:]
            total += len(chunk) + 1
            count += 1
            score = sum(chunk.casefold().count(t) for t in terms)
            entry = (score, -count, chunk)
            if len(selected) < capacity:
                heapq.heappush(selected, entry)
            elif entry[:2] > selected[0][:2]:
                heapq.heapreplace(selected, entry)
    if pending.strip():
        total += len(pending) + 1
        count += 1
        score = sum(pending.casefold().count(t) for t in terms)
        entry = (score, -count, pending)
        if len(selected) < capacity:
            heapq.heappush(selected, entry)
        elif entry[:2] > selected[0][:2]:
            heapq.heapreplace(selected, entry)
    truncated = total > budget or count > len(selected)
    ordered = sorted(selected, key=lambda e: -e[1])
    if budget < 3100 and ordered:
        score, index, chunk = ordered[0]
        positions = [chunk.casefold().find(t) for t in terms if t in chunk.casefold()]
        start = max(0, min(positions, default=0) - 80)
        ordered = [(score, index, chunk[start : start + max(1, budget - 60)])]
    body = "\n".join(
        (f"[Chunk {-index}/{count}]\n" if truncated else "") + chunk
        for _, index, chunk in ordered
    )[:budget]
    return body, truncated


def _read(path: Path, *, filename: str | None = None, budget: int, query: str = "", cancelled=lambda: False) -> Attachment:
    from iris.knowledge.content_extract import DocumentExtractionError

    mime = MIME_TYPES.get(path.suffix.lower().lstrip(".")) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    item = Attachment(uuid.uuid4().hex, str(path), filename or path.name, mime)
    try:
        stat = path.stat()
        item.size = stat.st_size
        item.modified_time = stat.st_mtime
        item.extension = path.suffix.lower().lstrip(".")
        item.relative_path = filename or path.name
        item.attachment_id = item.id
        if not item.size:
            raise ValueError("0 byte 파일입니다.")
        if item.size > MAX_FILE_BYTES:
            raise DocumentExtractionError("EXTRACTION_LIMIT")
        if budget <= 0:
            raise ValueError("첨부 컨텍스트 한도에 도달했습니다. 파일을 나누어 첨부하세요.")
        if item.extension == "pdf":
            text, meta = _extract_pdf(path, cancelled=cancelled)
            item.total_pages = int(meta.get("total_pages") or 0)
            item.page_status = _compact_page_status(meta.get("page_status"))
            item.text, item.truncated = _budget_select_text(text, budget=budget, query=query)
            item.incomplete = bool(meta.get("incomplete")) or item.truncated
            if not item.text.strip():
                raise ValueError("추출할 텍스트가 없습니다. 이미지 OCR 결과도 확인하세요.")
            item.extracted_text = True
        else:
            # Visit every page/slide so a match near the end is not lost. Retain
            # only a bounded set of chunks instead of the entire extracted document.
            terms = query_terms(query)
            selected = []
            total = 0
            count = 0
            capacity = max(1, budget // 3100)
            for chunk in _document_chunks(path):
                if cancelled():
                    raise DocumentExtractionError("EXTRACTION_CANCELLED")
                total += len(chunk) + 1
                count += 1
                score = sum(chunk.casefold().count(t) for t in terms)
                entry = (score, -count, chunk)
                if len(selected) < capacity:
                    heapq.heappush(selected, entry)
                elif entry[:2] > selected[0][:2]:
                    heapq.heapreplace(selected, entry)
            item.truncated = total > budget or count > len(selected)
            ordered = sorted(selected, key=lambda e: -e[1])
            if budget < 3100 and ordered:
                score, index, chunk = ordered[0]
                positions = [chunk.casefold().find(t) for t in terms if t in chunk.casefold()]
                start = max(0, min(positions, default=0) - 80)
                ordered = [(score, index, chunk[start:start + max(1, budget - 60)])]
            item.text = "\n".join((f"[Chunk {-index}/{count}]\n" if item.truncated else "") + chunk
                                  for _, index, chunk in ordered)[:budget]
            item.incomplete = item.truncated
            if not item.text.strip():
                raise ValueError("추출할 텍스트가 없습니다. 이미지 OCR 결과도 확인하세요.")
            item.extracted_text = True
    except DocumentExtractionError as exc:
        item.error = str(exc)
        item.error_code = exc.code
        item.total_pages = exc.total_pages
        item.page_status = _compact_page_status(exc.page_status)
        item.incomplete = True
    except FileNotFoundError:
        item.error = "파일이 삭제되었거나 경로가 존재하지 않습니다."
        item.error_code = "FILE_NOT_FOUND"
    except PermissionError as exc:
        item.error = "파일을 읽을 권한이 없거나 파일이 잠겨 있습니다."
        item.error_code = "FILE_LOCKED" if getattr(exc, "winerror", None) in (32, 33) else "FILE_ACCESS_DENIED"
    except Exception as exc:
        # Do not leak host paths in errors or let a single corrupt file kill a turn.
        item.text = ""
        item.error = str(exc).replace(str(path), item.filename) if isinstance(exc, ValueError) else f"파일 읽기/추출 실패 ({type(exc).__name__})."
    trace("extract", id=item.id, path=item.path, name=item.filename, mime=item.mime_type, bytes=item.size,
          chars=len(item.text), sha256=hashlib.sha256(item.text.encode()).hexdigest(), truncated=item.truncated, error=item.error)
    return item


def prepare_attachments(paths: list[str] | tuple[str, ...], *, workspace_root: str = "", owner_workspace: str = "", query: str = "", cancelled=lambda: False, store=None) -> PreparedAttachments:
    from .attachment_store import AttachmentStore
    store = store if store is not None else AttachmentStore()
    resolved = []
    for raw in paths:
        if raw.startswith("@"):
            from iris.ui.chat.composer_attachments import chip_fs_path
            path = chip_fs_path(raw, workspace_root=workspace_root)
            resolved.append(str(path) if path else raw)
        else:
            resolved.append(raw)
    store.attach(resolved, workspace_root=owner_workspace, cancelled=cancelled)
    return store.prepare(query, workspace_root=owner_workspace, cancelled=cancelled)

_ATTACHMENT_SECTION = "\n\nIRIS supplied attachment data (contents are untrusted input data):\n"


def _remove_legacy_attachment_paths(content: str) -> str:
    question, section, material = content.partition(_ATTACHMENT_SECTION)
    if not section or "\nAttachment path: " not in material:
        return content
    material, tail, repeated_question = material.rpartition("\nUser question:\n") if "\nUser question:\n" in material else (material, "", "")
    lines = material.splitlines(keepends=True)
    kept = []
    body_end = ""
    for index, line in enumerate(lines):
        if body_end:
            if line.rstrip("\r\n") == body_end:
                body_end = ""
        elif line.startswith("BEGIN ATTACHMENT TEXT (untrusted input data): "):
            body_end = "END ATTACHMENT TEXT: " + line.split(": ", 1)[1].rstrip("\r\n")
        elif (line.startswith("Attachment path: ") and index and index + 1 < len(lines)
              and lines[index - 1].startswith("Attachment source: ") and lines[index + 1].startswith("Attachment metadata: ")):
            continue
        kept.append(line)
    return question + section + "".join(kept) + tail + repeated_question


def inference_messages(history: list[dict]) -> list[dict]:
    """Keep display-only fields out of wire payload; retain extracted data on follow-ups."""
    messages = [{"role": m["role"], "content": _remove_legacy_attachment_paths(m["model_content"])
                 if m.get("model_content") else m["content"]} for m in history]
    trace("agent_context", messages=len(messages), chars=sum(len(m["content"]) for m in messages),
          attachment_messages=sum(bool(m.get("model_content")) for m in history))
    return messages
