"""위키 「아이리스 IDE」 — 연 프로젝트의 기획·진행·예정·문제."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from iris.knowledge.iris_wiki import IrisWiki
from iris.knowledge.wiki_places import is_sensitive, project_slug

FOLDER = "아이리스 IDE"
_SECTIONS = ("기획", "진행", "예정", "문제")


def _is_worktree_copy(root: str) -> bool:
    """작업 폴더 사본은 위키 노트로 만들지 않는다."""
    return any(part.endswith(".iris-worktrees") for part in Path(root).parts)


def note_rel(root: str) -> str:
    slug = project_slug(root) or "project"
    return f"{FOLDER}/{slug}.md"


def note_opened(wiki: IrisWiki, root: str) -> str:
    """노트가 없으면 만들고, 진행에 연 사실을 한 줄 남긴다."""
    if _is_worktree_copy(root):
        return ""
    path = _ensure(wiki, root)
    _append_section(path, "진행", f"{date.today().isoformat()} 프로젝트를 열었습니다.")
    return note_rel(root)


def note_file_written(window: Any, root: str, rel: str) -> None:
    if _is_worktree_copy(root):
        return
    if getattr(window, "_ui_mode", "") != "ide_companion":
        return
    wiki = getattr(window, "_iris_wiki", None)
    if wiki is None:
        return
    line = f"{date.today().isoformat()} 파일을 썼습니다: {(rel or '').replace(chr(92), '/')}"
    if is_sensitive(line):
        return
    try:
        path = _ensure(wiki, root)
        _append_section(path, "진행", line)
    except Exception:
        return


def note_update(
    wiki: IrisWiki,
    root: str,
    *,
    plan: str = "",
    decision: str = "",
    issue: str = "",
    progress: str = "",
) -> str:
    path = _ensure(wiki, root)
    stamp = date.today().isoformat()
    if decision.strip() and not is_sensitive(decision):
        _append_section(path, "기획", f"{stamp} {decision.strip()}")
    if progress.strip() and not is_sensitive(progress):
        _append_section(path, "진행", f"{stamp} {progress.strip()}")
    if plan.strip() and not is_sensitive(plan):
        _replace_section(path, "예정", plan.strip())
    if issue.strip() and not is_sensitive(issue):
        _append_section(path, "문제", f"{stamp} {issue.strip()}")
    return note_rel(root)


def _ensure(wiki: IrisWiki, root: str) -> Path:
    rel = note_rel(root)
    folder = Path(root).name or rel
    try:
        text = wiki.read_note(rel)
    except FileNotFoundError:
        text = ""
    except OSError:
        text = ""
    if not text.strip():
        body = (
            f"# {folder}\n\n"
            f"- root: `{Path(root).expanduser()}`\n\n"
            "## 기획\n\n"
            "## 진행\n\n"
            "## 예정\n\n"
            "## 문제\n"
        )
        wiki.write_user_note(rel, body)
    return (wiki.user_root / rel).resolve()


def _append_section(path: Path, section: str, line: str) -> None:
    text = path.read_text(encoding="utf-8")
    if line in text:
        return
    sections = _split(text)
    block = sections.get(section, "")
    sections[section] = (block.rstrip() + f"\n- {line}\n").strip() + "\n"
    path.write_text(_join(text, sections), encoding="utf-8")


def _replace_section(path: Path, section: str, body: str) -> None:
    text = path.read_text(encoding="utf-8")
    sections = _split(text)
    sections[section] = body.strip() + "\n"
    path.write_text(_join(text, sections), encoding="utf-8")


def _split(text: str) -> dict[str, str]:
    current = ""
    buf: dict[str, list[str]] = {name: [] for name in _SECTIONS}
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            continue
        if current in buf:
            buf[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in buf.items()}


def _join(original: str, sections: dict[str, str]) -> str:
    head: list[str] = []
    for line in original.splitlines():
        if line.startswith("## "):
            break
        head.append(line)
    while head and not head[-1].strip():
        head.pop()
    parts = ["\n".join(head).rstrip(), ""]
    for name in _SECTIONS:
        parts.append(f"## {name}")
        parts.append("")
        body = (sections.get(name) or "").strip()
        if body:
            parts.append(body)
            parts.append("")
    return "\n".join(parts).rstrip() + "\n"
