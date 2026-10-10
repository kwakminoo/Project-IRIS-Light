"""채팅 턴에 붙이는 자료 본문. 글자 수로 자르지 않는다."""

from __future__ import annotations

import re
from pathlib import Path

from iris.knowledge.content_extract import (
    _IMAGE_SUFFIXES,
    _looks_like_url,
    extract_from_source,
    readable_suffix,
)
from iris.knowledge.pdf_export import is_pdf_save_intent
from iris.ui.chat.at_path_refs import extract_at_path_refs, normalize_at_path

MAX_SOURCES = 6
MAX_URLS = 3
FOLDER_LIST_CAP = 40
FOLDER_READ_CAP = 3

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")


def extract_http_urls(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in _URL_RE.finditer(text or ""):
        url = match.group(0).rstrip(".,;:!?")
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def _classify(path: Path) -> dict:
    try:
        if path.is_file():
            return {"kind": "file", "path": str(path.resolve())}
        if path.is_dir():
            return {"kind": "folder", "path": str(path.resolve())}
    except OSError:
        return {"kind": "missing"}
    parent = path.parent
    prefix = path.name
    if not prefix:
        return {"kind": "missing"}
    try:
        if not parent.is_dir():
            return {"kind": "missing"}
        matches = [
            child
            for child in parent.iterdir()
            if child.is_file() and child.name.casefold().startswith(prefix.casefold())
        ]
    except OSError:
        return {"kind": "missing"}
    if len(matches) == 1:
        return {"kind": "file", "path": str(matches[0].resolve())}
    if len(matches) > 1:
        return {"kind": "many", "names": [child.name for child in sorted(matches, key=lambda p: p.name.casefold())]}
    return {"kind": "missing"}


def _resolve_raw(raw: str, bases: list[str]) -> dict:
    if _looks_like_url(raw):
        return {"kind": "url", "source": raw.strip()}
    text = normalize_at_path(raw.strip().strip('"').strip("'"))
    candidates: list[Path] = []
    drive = bool(re.match(r"^[A-Za-z]:[\\/]", text))
    if drive or Path(text).is_absolute():
        candidates.append(Path(text))
    else:
        candidates.append(Path(text))
        for base in bases:
            if base:
                candidates.append(Path(base).expanduser() / text)
    for cand in candidates:
        hit = _classify(cand.expanduser())
        if hit["kind"] != "missing":
            return hit
    return {"kind": "missing", "label": text or raw}


def collect_sources(
    text: str,
    attachments: list[str] | tuple[str, ...],
    *,
    bases: list[str] | tuple[str, ...] = (),
    skip_image_files: bool = False,
) -> list[dict]:
    raws: list[str] = []
    seen: set[str] = set()

    def add(item: str) -> None:
        key = (item or "").strip()
        if not key or len(raws) >= MAX_SOURCES:
            return
        fold = key.casefold()
        if fold in seen:
            return
        seen.add(fold)
        raws.append(key)

    for path in attachments or []:
        if skip_image_files and Path(str(path)).suffix.lower() in _IMAGE_SUFFIXES:
            continue
        add(str(path))
    for ref in extract_at_path_refs(text or ""):
        add(ref)
    url_n = 0
    for url in extract_http_urls(text or ""):
        if url_n >= MAX_URLS:
            break
        before = len(raws)
        add(url)
        if len(raws) > before:
            url_n += 1
    base_list = [str(b) for b in bases if str(b).strip()]
    hits: list[dict] = []
    seen_hit: set[str] = set()
    for raw in raws:
        hit = _resolve_raw(raw, base_list)
        names = "|".join(str(name) for name in (hit.get("names") or []))
        token = "|".join(
            [
                str(hit.get("kind") or ""),
                str(hit.get("path") or hit.get("source") or hit.get("label") or "").casefold(),
                names.casefold(),
            ]
        )
        if token in seen_hit:
            continue
        seen_hit.add(token)
        hits.append(hit)
    return hits


def turn_should_read_materials(
    text: str,
    attachments: list[str] | tuple[str, ...],
    *,
    bases: list[str] | tuple[str, ...] = (),
    skip_image_files: bool = False,
) -> bool:
    if is_pdf_save_intent(text or ""):
        return False
    return bool(
        collect_sources(
            text,
            attachments,
            bases=bases,
            skip_image_files=skip_image_files,
        )
    )


def _section_file(path: str, *, vision_reader) -> str:
    data = extract_from_source(
        path,
        char_limit=None,
        vision_reader=vision_reader,
    )
    lines = [f"### {data.get('title') or Path(path).name}", str(data.get("source") or path)]
    if data.get("vision_used"):
        lines.append("읽기: 이미지에서 비전으로 옮김")
    elif data.get("ocr_used"):
        lines.append("읽기: 글자 층이 부족해 OCR")
    note = str(data.get("note") or "").strip()
    if note:
        lines.append(note)
    lines.append(str(data.get("text") or "").strip())
    return "\n".join(lines)


def _section_folder(path: str, *, vision_reader) -> str:
    folder = Path(path)
    try:
        children = sorted(folder.iterdir(), key=lambda p: p.name.casefold())
    except OSError as exc:
        return f"### {folder.name}\n{path}\n(읽지 못함) {exc}"
    listed = []
    for child in children[:FOLDER_LIST_CAP]:
        name = child.name + ("/" if child.is_dir() else "")
        listed.append(f"- {name}")
    hidden = len(children) - len(listed)
    lines = [f"### {folder.name}", str(folder.resolve()), "바로 아래:", *listed]
    if hidden > 0:
        lines.append(f"- … 외 {hidden}개")
    readable = [
        child
        for child in children
        if child.is_file() and readable_suffix(child.suffix.lower())
    ][:FOLDER_READ_CAP]
    for child in readable:
        try:
            block = _section_file(str(child), vision_reader=vision_reader)
        except (OSError, ValueError, RuntimeError) as exc:
            block = f"### {child.name}\n(읽지 못함) {exc}"
        lines.append(block)
    return "\n".join(lines)


def _one_section(hit: dict, *, vision_reader) -> str:
    kind = hit.get("kind")
    if kind == "many":
        names = "\n".join(f"- {name}" for name in hit.get("names") or [])
        return (
            "### 같은 이름으로 시작하는 파일이 여러 개라 본문은 넣지 않았습니다.\n" + names
        )
    if kind == "missing":
        label = hit.get("label") or hit.get("path") or ""
        return f"### {label}\n(읽지 못함) 파일을 찾지 못했습니다."
    if kind == "url":
        try:
            return _section_file(str(hit.get("source") or ""), vision_reader=None)
        except (OSError, ValueError, RuntimeError) as exc:
            return f"### {hit.get('source')}\n(읽지 못함) {exc}"
    if kind == "folder":
        return _section_folder(str(hit.get("path") or ""), vision_reader=vision_reader)
    if kind == "file":
        try:
            return _section_file(str(hit.get("path") or ""), vision_reader=vision_reader)
        except (OSError, ValueError, RuntimeError) as exc:
            return f"### {hit.get('path')}\n(읽지 못함) {exc}"
    return "(읽지 못함) 자료를 해석하지 못했습니다."


def build_material_block(
    text: str,
    attachments: list[str] | tuple[str, ...] = (),
    *,
    bases: list[str] | tuple[str, ...] = (),
    skip_image_files: bool = False,
    vision_reader=None,
) -> str:
    """읽을 자료가 없으면 빈 문자열. 있으면 [자료 본문]으로 시작한다."""
    if is_pdf_save_intent(text or ""):
        return ""
    hits = collect_sources(
        text,
        attachments,
        bases=bases,
        skip_image_files=skip_image_files,
    )
    if not hits:
        return ""
    parts = [_one_section(hit, vision_reader=vision_reader) for hit in hits]
    body = "\n\n".join(part for part in parts if part.strip())
    return "[자료 본문]\n" + body


def compose_model_user_text(display: str, block: str) -> str:
    shown = (display or "").strip()
    extra = (block or "").strip()
    if shown and extra:
        return f"{shown}\n\n{extra}"
    return shown or extra
