"""채팅 슬롯이 같은 대상을 동시에 고치지 않게 하는 표식.

프로젝트·IDE·터미널은 창에 하나. 위키 노트는 상대 경로마다 하나.
읽기와 검색은 여기 오지 않는다.
"""

from __future__ import annotations

import posixpath
import threading
from typing import Any

_PROJECT = frozenset(
    {
        "project.write_file",
        "project.write_image_code",
        "project.rename_file",
        "project.run",
        "ide.edit",
        "ide.save",
        "ide.task",
        "ide.debug",
        "note.export_pdf",
        "ide.open_folder",
        "ide.pick_open_folder",
        "project.open_similar",
        "project.create_scaffold",
    }
)
_WIKI = frozenset(
    {
        "wiki.write_user_note",
        "wiki.import_content",
        "wiki.import_pages",
        "wiki.reprocess_note",
        "wiki.delete_note",
        "wiki.move_notes",
    }
)


def wiki_rel_key(raw: object) -> str:
    """위키 잠금 키. 파일시스템은 보지 않고 posix 상대 경로로 맞춘다."""
    text = str(raw or "").replace("\\", "/").strip()
    if not text:
        return "*"
    norm = posixpath.normpath(text)
    if norm in ("", "."):
        return "*"
    return norm


def write_lock_target(
    action: str, args: dict[str, Any] | None
) -> tuple[str, tuple[str, ...]] | None:
    name = (action or "").strip()
    payload = args or {}
    if name in _PROJECT:
        return ("project", ("",))
    if name not in _WIKI:
        return None
    if name == "wiki.move_notes":
        raw = payload.get("sources")
        if raw is None:
            raw = payload.get("from") or payload.get("rel_path") or payload.get("path") or ""
        if isinstance(raw, (list, tuple)):
            paths = [str(item) for item in raw if str(item).strip()]
        else:
            paths = [str(raw)] if str(raw).strip() else []
        dest = payload.get("dest_folder")
        if dest is None:
            dest = payload.get("folder") or ""
        paths.append(str(dest))
        return ("wiki", tuple(wiki_rel_key(item) for item in paths) or ("*",))
    rel = payload.get("rel_path") or payload.get("path") or payload.get("from") or ""
    return ("wiki", (wiki_rel_key(rel),))


def write_holder(args: dict[str, Any] | None) -> int:
    """대화 id가 없으면 요청 스레드를 음수 키로 쓴다. 대화 id(양수)와 안 겹친다."""
    payload = args or {}
    raw = payload.get("conversation_id")
    if raw is not None and str(raw).strip() != "":
        return int(raw)
    return -int(threading.get_ident())


class SessionWriteLock:
    def __init__(self) -> None:
        self._cv = threading.Condition()
        self.project_holder: int | None = None
        self._project_depth = 0
        self.wiki_holder: dict[str, int] = {}
        self._wiki_depth: dict[str, int] = {}

    def try_acquire_project(self, conversation_id: int) -> bool:
        with self._cv:
            if self.project_holder not in (None, conversation_id):
                return False
            self.project_holder = conversation_id
            self._project_depth += 1
            return True

    def acquire_project(self, conversation_id: int) -> None:
        with self._cv:
            while self.project_holder not in (None, conversation_id):
                self._cv.wait()
            self.project_holder = conversation_id
            self._project_depth += 1

    def release_project(self, conversation_id: int) -> None:
        with self._cv:
            if self.project_holder != conversation_id:
                return
            self._project_depth -= 1
            if self._project_depth <= 0:
                self.project_holder = None
                self._project_depth = 0
                self._cv.notify_all()

    def try_acquire_wiki(self, conversation_id: int, rel: str) -> bool:
        key = wiki_rel_key(rel)
        with self._cv:
            holder = self.wiki_holder.get(key)
            if holder not in (None, conversation_id):
                return False
            self.wiki_holder[key] = conversation_id
            self._wiki_depth[key] = self._wiki_depth.get(key, 0) + 1
            return True

    def acquire_wiki(self, conversation_id: int, rel: str) -> None:
        key = wiki_rel_key(rel)
        with self._cv:
            while self.wiki_holder.get(key) not in (None, conversation_id):
                self._cv.wait()
            self.wiki_holder[key] = conversation_id
            self._wiki_depth[key] = self._wiki_depth.get(key, 0) + 1

    def release_wiki(self, conversation_id: int, rel: str) -> None:
        key = wiki_rel_key(rel)
        with self._cv:
            if self.wiki_holder.get(key) != conversation_id:
                return
            depth = self._wiki_depth.get(key, 0) - 1
            if depth <= 0:
                self.wiki_holder.pop(key, None)
                self._wiki_depth.pop(key, None)
                self._cv.notify_all()
            else:
                self._wiki_depth[key] = depth


_LOCK = SessionWriteLock()


def shared_write_lock() -> SessionWriteLock:
    return _LOCK


def _check() -> None:
    lock = SessionWriteLock()
    assert lock.try_acquire_project(1)
    assert not lock.try_acquire_project(2)
    assert lock.try_acquire_project(1)
    lock.release_project(1)
    lock.release_project(1)
    assert lock.try_acquire_project(2)
    lock.release_project(2)

    assert lock.try_acquire_wiki(1, "notes/a.md")
    assert lock.try_acquire_wiki(2, "notes/b.md")
    assert not lock.try_acquire_wiki(2, "notes/a.md")
    lock.release_wiki(1, "notes/a.md")
    assert lock.try_acquire_wiki(2, "notes/a.md")
    lock.release_wiki(2, "notes/a.md")
    lock.release_wiki(2, "notes/b.md")

    assert write_lock_target("wiki.read_note", {"rel_path": "a.md"}) is None
    assert write_lock_target("wiki.search", {"query": "a"}) is None
    assert write_lock_target("project.write_file", {}) == ("project", ("",))
    assert write_lock_target("note.export_pdf", {}) == ("project", ("",))
    assert write_lock_target("wiki.write_user_note", {"rel_path": "notes\\a.md"}) == (
        "wiki",
        ("notes/a.md",),
    )
    assert wiki_rel_key("notes/../notes/a.md") == wiki_rel_key("notes/a.md")
    assert lock.try_acquire_wiki(1, "notes/../notes/a.md")
    assert not lock.try_acquire_wiki(2, "notes/a.md")
    lock.release_wiki(1, "notes/a.md")

    assert lock.try_acquire_wiki(1, "notes/a.md")
    moved = write_lock_target(
        "wiki.move_notes",
        {"sources": ["notes/../notes/a.md"], "dest_folder": "inbox"},
    )
    assert moved is not None and moved[0] == "wiki"
    assert "notes/a.md" in moved[1]
    assert not any(lock.try_acquire_wiki(2, key) for key in moved[1] if key == "notes/a.md")
    lock.release_wiki(1, "notes/a.md")

    held = lock.try_acquire_project(1)
    assert held
    assert not lock.try_acquire_project(2)
    lock.release_project(1)
    for name in (
        "ide.open_folder",
        "ide.pick_open_folder",
        "project.open_similar",
        "project.create_scaffold",
    ):
        assert write_lock_target(name, {}) == ("project", ("",))
    print("session write lock ok")


if __name__ == "__main__":
    _check()
