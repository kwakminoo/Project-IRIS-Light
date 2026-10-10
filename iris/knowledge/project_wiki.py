"""채팅 프로젝트 폴더를 위키 `projects/<이름>/` 아래에 둔다."""

from __future__ import annotations

import shutil
from pathlib import Path

from iris.knowledge.iris_wiki import IrisWiki
from iris.storage.chat_projects import (
    ChatProject,
    commit_project_rename,
    get_project,
    unique_project_slug,
)
from iris.storage.database import Database

_MARKER = "<!-- iris-chat-project -->"
_RENAME_HEADING = "## 이름 변경"
_OURS = {"index.md", "chats", "episodes"}


def project_root_rel(slug: str) -> str:
    return f"projects/{slug}"


def project_index_rel(slug: str) -> str:
    return f"projects/{slug}/index.md"


def project_chat_rel(slug: str, conversation_id: int) -> str:
    return f"projects/{slug}/chats/{int(conversation_id)}.md"


def project_episode_dir(slug: str) -> str:
    return f"projects/{slug}/episodes"


def rename_line(old_name: str, new_name: str) -> str:
    return f"- [{old_name}] -> [{new_name}]"


def _note_text(name: str, *, history: list[str] | None = None) -> str:
    lines = [_MARKER, f"# {name}", "", _RENAME_HEADING, ""]
    for line in history or []:
        lines.append(line)
    return "\n".join(lines).rstrip() + "\n"


def _safe_dir(wiki: IrisWiki, slug: str) -> Path:
    folder = (wiki.user_root / "projects" / slug).resolve()
    root = wiki.user_root.resolve()
    if root not in folder.parents:
        raise ValueError("invalid project path")
    return folder


def create_project_wiki(wiki: IrisWiki, name: str, slug: str) -> str:
    rel = project_index_rel(slug)
    wiki.write_user_note(rel, _note_text(name))
    return rel


def _parse_note(text: str) -> tuple[str, list[str]]:
    title = ""
    history: list[str] = []
    in_history = False
    for line in (text or "").splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            in_history = False
            continue
        if line.strip() == _RENAME_HEADING:
            in_history = True
            continue
        if in_history and line.startswith("- ["):
            history.append(line.strip())
    return title, history


def _foreign_children(folder: Path) -> bool:
    if not folder.is_dir():
        return False
    for child in folder.iterdir():
        if child.name not in _OURS:
            return True
    return False


def _move_owned(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    index = src / "index.md"
    if index.is_file():
        index.replace(dst / "index.md")
    for name in ("chats", "episodes"):
        child = src / name
        target = dst / name
        if not child.exists():
            continue
        if target.exists():
            shutil.rmtree(target)
        child.replace(target)
    if src.is_dir() and not _foreign_children(src) and not any(src.iterdir()):
        src.rmdir()


def rename_project_wiki(
    wiki: IrisWiki,
    *,
    old_slug: str,
    new_slug: str,
    old_name: str,
    new_name: str,
) -> str:
    """폴더 이름을 바꾸고, 노트 안에 `[이전] -> [이후]` 를 한 줄 더 붙인다."""
    src = _safe_dir(wiki, old_slug)
    dst = _safe_dir(wiki, new_slug)
    history: list[str] = []
    note = src / "index.md"
    if note.is_file():
        _title, history = _parse_note(note.read_text(encoding="utf-8", errors="replace"))
    if src.is_dir() and src != dst:
        if _foreign_children(src):
            _move_owned(src, dst)
        elif dst.exists():
            _move_owned(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
    history.append(rename_line(old_name, new_name))
    rel = project_index_rel(new_slug)
    wiki.write_user_note(rel, _note_text(new_name, history=history))
    return rel


def remove_project_wiki(wiki: IrisWiki, slug: str) -> None:
    folder = _safe_dir(wiki, slug)
    if not folder.is_dir():
        return
    if _foreign_children(folder):
        index = folder / "index.md"
        if index.is_file():
            index.unlink()
        for name in ("chats", "episodes"):
            child = folder / name
            if child.is_dir():
                shutil.rmtree(child)
        return
    shutil.rmtree(folder)


def apply_project_rename(
    db: Database,
    wiki: IrisWiki,
    project_id: int,
    name: str,
    *,
    reserved_slugs: set[str] | None = None,
) -> ChatProject:
    from iris.storage.chat_projects import retarget_project_history

    old = get_project(db, project_id)
    if old is None:
        raise ValueError("project missing")
    shown = name.strip()
    if not shown:
        raise ValueError("name required")
    slug = unique_project_slug(
        db, shown, exclude_id=old.id, reserved=reserved_slugs,
    )
    if slug != old.wiki_slug or shown != old.name:
        rename_project_wiki(
            wiki,
            old_slug=old.wiki_slug,
            new_slug=slug,
            old_name=old.name,
            new_name=shown,
        )
        if slug != old.wiki_slug:
            retarget_project_history(db, old.wiki_slug, slug)
    return commit_project_rename(db, old.id, shown, slug)
