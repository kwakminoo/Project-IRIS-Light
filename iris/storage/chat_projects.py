"""채팅 프로젝트 폴더 — 일반 채팅과 분리된 묶음."""

from __future__ import annotations

from dataclasses import dataclass

from iris.knowledge.iris_wiki import slugify_note_name
from iris.storage.conversations import (
    delete_conversation,
    ensure_chat_schema,
)
from iris.storage.database import Database

_NAME_LIMIT = 48


@dataclass(frozen=True)
class ChatProject:
    id: int
    name: str
    wiki_slug: str
    created_at: str
    updated_at: str


def _now() -> str:
    from iris.storage.conversations import _now as conv_now

    return conv_now()


def normalize_project_name(name: str) -> str:
    text = " ".join((name or "").split())
    if len(text) > _NAME_LIMIT:
        text = text[:_NAME_LIMIT]
    return text


def ensure_project_schema(db: Database) -> None:
    ensure_chat_schema(db)
    db._execute(
        """
        CREATE TABLE IF NOT EXISTS chat_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            wiki_slug TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    db._commit()


def _project_from_row(row) -> ChatProject:
    return ChatProject(
        id=int(row["id"]),
        name=str(row["name"] or ""),
        wiki_slug=str(row["wiki_slug"] or ""),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
    )


def list_projects(db: Database) -> list[ChatProject]:
    """만든 순서. 목록에서는 이 순서가 일반 채팅보다 위다."""
    ensure_project_schema(db)
    rows = db._execute(
        """
        SELECT id, name, wiki_slug, created_at, updated_at
          FROM chat_projects
         ORDER BY created_at ASC, id ASC
        """
    ).fetchall()
    return [_project_from_row(row) for row in rows]


def get_project(db: Database, project_id: int) -> ChatProject | None:
    ensure_project_schema(db)
    row = db._execute(
        """
        SELECT id, name, wiki_slug, created_at, updated_at
          FROM chat_projects WHERE id = ?
        """,
        (int(project_id),),
    ).fetchone()
    if row is None:
        return None
    return _project_from_row(row)


def project_for_conversation(db: Database, conversation_id: int) -> ChatProject | None:
    ensure_project_schema(db)
    row = db._execute(
        "SELECT project_id FROM chat_conversations WHERE id = ?",
        (int(conversation_id),),
    ).fetchone()
    if row is None:
        return None
    project_id = int(row["project_id"] or 0)
    if project_id <= 0:
        return None
    return get_project(db, project_id)


def _taken_slugs(db: Database, *, exclude_id: int = 0) -> set[str]:
    rows = db._execute("SELECT id, wiki_slug FROM chat_projects").fetchall()
    return {
        str(row["wiki_slug"])
        for row in rows
        if int(row["id"]) != int(exclude_id) and str(row["wiki_slug"] or "")
    }


def unique_project_slug(
    db: Database,
    name: str,
    *,
    exclude_id: int = 0,
    reserved: set[str] | None = None,
) -> str:
    ensure_project_schema(db)
    base = slugify_note_name(name) or "project"
    taken = _taken_slugs(db, exclude_id=exclude_id) | set(reserved or ())
    slug = base
    n = 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    return slug


def create_project(db: Database, name: str, *, reserved_slugs: set[str] | None = None) -> ChatProject:
    ensure_project_schema(db)
    shown = normalize_project_name(name)
    if not shown:
        raise ValueError("name required")
    slug = unique_project_slug(db, shown, reserved=reserved_slugs)
    stamp = _now()
    cur = db._execute(
        """
        INSERT INTO chat_projects(name, wiki_slug, created_at, updated_at)
        VALUES(?, ?, ?, ?)
        """,
        (shown, slug, stamp, stamp),
    )
    db._commit()
    return ChatProject(
        id=int(cur.lastrowid or 0),
        name=shown,
        wiki_slug=slug,
        created_at=stamp,
        updated_at=stamp,
    )


def commit_project_rename(db: Database, project_id: int, name: str, wiki_slug: str) -> ChatProject:
    ensure_project_schema(db)
    shown = normalize_project_name(name)
    if not shown:
        raise ValueError("name required")
    stamp = _now()
    db._execute(
        """
        UPDATE chat_projects
           SET name = ?, wiki_slug = ?, updated_at = ?
         WHERE id = ?
        """,
        (shown, wiki_slug, stamp, int(project_id)),
    )
    db._commit()
    project = get_project(db, project_id)
    if project is None:
        raise ValueError("project missing")
    return project


def conversation_ids_in_project(db: Database, project_id: int) -> list[int]:
    ensure_project_schema(db)
    rows = db._execute(
        "SELECT id FROM chat_conversations WHERE project_id = ?",
        (int(project_id),),
    ).fetchall()
    return [int(row["id"]) for row in rows]


def delete_project(db: Database, project_id: int) -> list[int]:
    """폴더와 그 안의 채팅을 지운다. 지운 채팅 id 를 돌려준다."""
    ids = conversation_ids_in_project(db, project_id)
    for cid in ids:
        delete_conversation(db, cid)
    ensure_project_schema(db)
    db._execute("DELETE FROM chat_projects WHERE id = ?", (int(project_id),))
    db._commit()
    return ids


def retarget_project_history(db: Database, old_slug: str, new_slug: str) -> None:
    """위키 폴더를 옮긴 뒤 History 가 가리키는 경로를 같이 바꾼다."""
    old_prefix = f"projects/{old_slug}/"
    new_prefix = f"projects/{new_slug}/"
    if old_prefix == new_prefix:
        return
    try:
        rows = db._execute("SELECT id, rel_path FROM wiki_history").fetchall()
    except Exception:
        return
    for row in rows:
        rel = str(row["rel_path"] or "")
        if not rel.startswith(old_prefix):
            continue
        db._execute(
            "UPDATE wiki_history SET rel_path = ? WHERE id = ?",
            (new_prefix + rel[len(old_prefix) :], int(row["id"])),
        )
    db._commit()
