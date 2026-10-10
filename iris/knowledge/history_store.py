"""Iris Wiki History — 대화·수행·생성물·입력 데이터의 단일 기록처.

같은 항목을 두 곳에 남긴다.

- 위키 마크다운 (`~/.iris-light/iris-wiki/history/`) — 사람이 읽고 고치는 면
- SQLite `wiki_history` — RAG가 검색하는 면 (`history_index` 가 색인)

마크다운이 원본이 아니라 **표현**이다. 검색·컨텍스트 복원은 항상 DB를 본다.
사용자가 위키 파일을 직접 고쳐도 DB 기록은 그대로 남는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from iris.knowledge.iris_wiki import IrisWiki, slugify_note_name
from iris.storage.database import Database

HISTORY_DIR = "history"
EPISODE_DIR = "history/episodes"

# 기록 종류 — 사용자가 "나누거나 만들거나 인풋 들어온" 모든 것
KIND_CHAT = "chat"  # 사용자·아이리스가 주고받은 말
KIND_ACTION = "action"  # 아이리스가 수행한 일 (툴 호출·학습된 업무·자동화)
KIND_ARTIFACT = "artifact"  # 만들어낸 것 (파일·코드·문서·일정)
KIND_INPUT = "input"  # 들어온 데이터 (첨부·붙여넣기·가져온 URL/PDF)
KIND_EPISODE = "episode"  # LLM이 묶어 요약한 대화 단위

KINDS: tuple[str, ...] = (KIND_CHAT, KIND_ACTION, KIND_ARTIFACT, KIND_INPUT, KIND_EPISODE)

_KIND_LABELS = {
    KIND_CHAT: "대화",
    KIND_ACTION: "수행",
    KIND_ARTIFACT: "생성물",
    KIND_INPUT: "입력",
    KIND_EPISODE: "요약",
}

_ROLE_LABELS = {"user": "사용자", "assistant": "아이리스", "system": "시스템"}

# 위키 일별 노트에 남길 본문 길이 상한. 원문 전체는 DB에 그대로 있다.
_MD_BODY_LIMIT = 4000


@dataclass(frozen=True)
class HistoryEntry:
    id: int
    kind: str
    conversation_id: int
    role: str
    title: str
    body: str
    source: str
    model: str
    tags: str
    rel_path: str
    created_at: str

    @property
    def kind_label(self) -> str:
        return _KIND_LABELS.get(self.kind, self.kind)

    @property
    def role_label(self) -> str:
        return _ROLE_LABELS.get(self.role, self.role)

    def as_context_line(self) -> str:
        """모델에게 넘길 한 줄 요약 — 어디서 온 기록인지 밝힌다."""
        head = f"[{self.created_at}] {self.kind_label}"
        if self.role:
            head += f"/{self.role_label}"
        if self.title:
            head += f" — {self.title}"
        return head


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_kind(kind: str) -> str:
    value = (kind or "").strip().lower()
    return value if value in KINDS else KIND_CHAT


def ensure_history_schema(db: Database) -> None:
    db._execute(
        """
        CREATE TABLE IF NOT EXISTS wiki_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            conversation_id INTEGER NOT NULL DEFAULT 0,
            role TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '',
            rel_path TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    db._execute(
        "CREATE INDEX IF NOT EXISTS idx_wiki_history_conv "
        "ON wiki_history(conversation_id, id)"
    )
    db._execute(
        "CREATE INDEX IF NOT EXISTS idx_wiki_history_kind "
        "ON wiki_history(kind, id DESC)"
    )
    db._commit()


def record_entry(
    db: Database,
    *,
    kind: str,
    body: str,
    title: str = "",
    conversation_id: int = 0,
    role: str = "",
    source: str = "",
    model: str = "",
    tags: str = "",
    wiki: IrisWiki | None = None,
    rel_path: str = "",
) -> HistoryEntry | None:
    """History 한 건 기록. 본문이 비면 아무것도 남기지 않고 None."""
    text = (body or "").strip()
    if not text:
        return None
    ensure_history_schema(db)
    kind_value = normalize_kind(kind)
    stamp = _now()
    rel_path = (rel_path or "").strip().lstrip("/") or _daily_rel_path(stamp)
    cur = db._execute(
        """
        INSERT INTO wiki_history(
            kind, conversation_id, role, title, body,
            source, model, tags, rel_path, created_at
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            kind_value,
            int(conversation_id or 0),
            str(role or ""),
            str(title or "").strip(),
            text,
            str(source or "").strip(),
            str(model or "").strip(),
            str(tags or "").strip(),
            rel_path,
            stamp,
        ),
    )
    db._commit()
    entry = HistoryEntry(
        id=int(cur.lastrowid or 0),
        kind=kind_value,
        conversation_id=int(conversation_id or 0),
        role=str(role or ""),
        title=str(title or "").strip(),
        body=text,
        source=str(source or "").strip(),
        model=str(model or "").strip(),
        tags=str(tags or "").strip(),
        rel_path=rel_path,
        created_at=stamp,
    )
    if wiki is not None:
        try:
            append_to_wiki(wiki, entry)
        except OSError:
            # 위키 파일 실패로 기록 자체를 잃지 않는다 — DB에는 이미 들어갔다.
            pass
    return entry


def record_turn(
    db: Database,
    conversation_id: int,
    role: str,
    content: str,
    *,
    model: str = "",
    wiki: IrisWiki | None = None,
) -> HistoryEntry | None:
    """채팅 한 턴 기록 — ChatSession.record 와 짝을 이룬다."""
    return record_entry(
        db,
        kind=KIND_CHAT,
        body=content,
        conversation_id=conversation_id,
        role=role,
        model=model,
        wiki=wiki,
    )


def _daily_rel_path(stamp: str) -> str:
    day = (stamp or _now())[:10] or datetime.now().strftime("%Y-%m-%d")
    return f"{HISTORY_DIR}/{day[:7]}/{day}.md"


def append_to_wiki(wiki: IrisWiki, entry: HistoryEntry) -> Path:
    """일별 History 노트에 한 항목을 덧붙인다."""
    path = (wiki.user_root / entry.rel_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if entry.rel_path.startswith("projects/") and path.is_file() and entry.title:
        retitle_project_chat(path, entry.title)
    if not path.exists():
        if entry.rel_path.startswith("projects/"):
            title = entry.title or "채팅"
            header = f"# {title}\n\n"
        else:
            day = entry.created_at[:10]
            header = f"# History {day}\n\n> 아이리스가 자동으로 남기는 기록의 보기용 사본입니다. 이 파일을 고치거나 지워도 검색에는 반영되지 않습니다 — 채팅을 지우면 그 대화의 기록이 여기서도 함께 지워집니다.\n"
        path.write_text(header, encoding="utf-8")
    with path.open("a", encoding="utf-8") as fp:
        fp.write("\n" + render_entry_markdown(entry))
    return path


def retitle_project_chat(path: Path, title: str) -> None:
    """프로젝트 채팅 노트의 첫 제목을 지금 채팅 제목으로 맞춘다."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    lines = text.splitlines()
    heading = f"# {title}"
    if lines and lines[0].startswith("# "):
        if lines[0] == heading:
            return
        lines[0] = heading
    else:
        lines.insert(0, heading)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def render_entry_markdown(entry: HistoryEntry) -> str:
    time_part = entry.created_at[11:19] or entry.created_at
    head = f"## {time_part} · {entry.kind_label}"
    if entry.role:
        head += f" · {entry.role_label}"
    if entry.title:
        head += f" — {entry.title}"
    lines = [head, ""]
    meta: list[str] = [f"id:{entry.id}"]
    if entry.conversation_id:
        meta.append(f"conv:{entry.conversation_id}")
    if entry.model:
        meta.append(f"model:`{entry.model}`")
    if entry.source:
        meta.append(f"source:{entry.source}")
    if entry.tags:
        meta.append(f"tags:{entry.tags}")
    lines.append("<!-- " + " ".join(meta) + " -->")
    lines.append("")
    body = entry.body
    if len(body) > _MD_BODY_LIMIT:
        body = body[:_MD_BODY_LIMIT] + f"\n\n_(...{len(entry.body) - _MD_BODY_LIMIT}자 생략 — 전문은 History 검색으로)_"
    lines.append(body)
    lines.append("")
    return "\n".join(lines)


def write_episode(
    db: Database,
    wiki: IrisWiki,
    *,
    title: str,
    summary: str,
    conversation_id: int = 0,
    model: str = "",
    covers: tuple[int, int] | None = None,
    folder: str = "",
) -> HistoryEntry | None:
    """대화 묶음 요약을 `history/episodes/<slug>.md` 로 남기고 색인 대상에 넣는다.

    프로젝트 채팅이면 folder 가 `projects/<slug>/episodes` 다.
    """
    text = (summary or "").strip()
    if not text:
        return None
    ensure_history_schema(db)
    stamp = _now()
    slug = slugify_note_name(title or f"episode-{stamp[:10]}")
    place = (folder or EPISODE_DIR).strip("/")
    rel = f"{place}/{slug}.md"
    cur = db._execute(
        """
        INSERT INTO wiki_history(
            kind, conversation_id, role, title, body,
            source, model, tags, rel_path, created_at
        ) VALUES(?, ?, '', ?, ?, '', ?, ?, ?, ?)
        """,
        (
            KIND_EPISODE,
            int(conversation_id or 0),
            str(title or "").strip(),
            text,
            str(model or "").strip(),
            f"covers:{covers[0]}-{covers[1]}" if covers else "",
            rel,
            stamp,
        ),
    )
    db._commit()
    entry = HistoryEntry(
        id=int(cur.lastrowid or 0),
        kind=KIND_EPISODE,
        conversation_id=int(conversation_id or 0),
        role="",
        title=str(title or "").strip(),
        body=text,
        source="",
        model=str(model or "").strip(),
        tags=f"covers:{covers[0]}-{covers[1]}" if covers else "",
        rel_path=rel,
        created_at=stamp,
    )
    lines = [f"# {entry.title or slug}", ""]
    if conversation_id:
        lines.append(f"- 대화: `conv:{conversation_id}`")
    if model:
        lines.append(f"- 요약 모델: `{model}`")
    if covers:
        lines.append(f"- 포함 기록: `#{covers[0]}` ~ `#{covers[1]}`")
    lines.extend(["", text, "", f"> updated: {stamp}", ""])
    try:
        wiki.write_user_note(rel, "\n".join(lines))
    except (OSError, ValueError):
        pass
    return entry


def _entry_from_row(row) -> HistoryEntry:
    return HistoryEntry(
        id=int(row["id"]),
        kind=str(row["kind"]),
        conversation_id=int(row["conversation_id"] or 0),
        role=str(row["role"] or ""),
        title=str(row["title"] or ""),
        body=str(row["body"] or ""),
        source=str(row["source"] or ""),
        model=str(row["model"] or ""),
        tags=str(row["tags"] or ""),
        rel_path=str(row["rel_path"] or ""),
        created_at=str(row["created_at"] or ""),
    )


def get_entry(db: Database, history_id: int) -> HistoryEntry | None:
    ensure_history_schema(db)
    row = db._execute(
        "SELECT * FROM wiki_history WHERE id = ?", (int(history_id),)
    ).fetchone()
    return _entry_from_row(row) if row else None


def list_entries(
    db: Database,
    *,
    conversation_id: int | None = None,
    kinds: tuple[str, ...] | None = None,
    limit: int = 200,
) -> list[HistoryEntry]:
    ensure_history_schema(db)
    where: list[str] = []
    params: list[object] = []
    if conversation_id is not None:
        where.append("conversation_id = ?")
        params.append(int(conversation_id))
    if kinds:
        marks = ",".join("?" for _ in kinds)
        where.append(f"kind IN ({marks})")
        params.extend(kinds)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    params.append(max(1, int(limit)))
    rows = db._execute(
        f"SELECT * FROM wiki_history {clause} ORDER BY id DESC LIMIT ?", tuple(params)
    ).fetchall()
    return [_entry_from_row(r) for r in rows]


def count_entries(db: Database) -> int:
    ensure_history_schema(db)
    row = db._execute("SELECT COUNT(*) AS n FROM wiki_history").fetchone()
    return int(row["n"] if row else 0)


def delete_entry(db: Database, history_id: int) -> None:
    ensure_history_schema(db)
    db._execute("DELETE FROM wiki_history WHERE id = ?", (int(history_id),))
    db._commit()


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = Database(root / "t.db")
        wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")

        e1 = record_turn(db, 7, "user", "설치 프로그램이 자꾸 죽어요", wiki=wiki)
        e2 = record_turn(db, 7, "assistant", "venv 재생성 권한 문제입니다", model="qwen3:8b", wiki=wiki)
        e3 = record_entry(
            db, kind=KIND_ACTION, body="setup.ps1 -Recreate 실행", title="설치 재시도",
            conversation_id=7, source="setup.ps1", wiki=wiki,
        )
        assert e1 and e2 and e3
        assert record_turn(db, 7, "user", "   ") is None
        assert count_entries(db) == 3

        assert normalize_kind("ACTION") == KIND_ACTION
        assert normalize_kind("없는종류") == KIND_CHAT

        got = get_entry(db, e2.id)
        assert got is not None and got.body == "venv 재생성 권한 문제입니다"
        assert got.role_label == "아이리스"
        assert "아이리스" in got.as_context_line()

        only_action = list_entries(db, kinds=(KIND_ACTION,))
        assert [x.id for x in only_action] == [e3.id]
        assert len(list_entries(db, conversation_id=7)) == 3
        assert list_entries(db, conversation_id=999) == []

        day_file = wiki.user_root / e1.rel_path
        assert day_file.is_file(), day_file
        text = day_file.read_text(encoding="utf-8")
        assert "# History" in text
        assert "설치 프로그램이 자꾸 죽어요" in text
        assert "venv 재생성 권한 문제입니다" in text
        assert f"id:{e3.id}" in text

        ep = write_episode(
            db, wiki, title="설치 프로그램 디버깅", summary="권한 문제로 결론",
            conversation_id=7, model="qwen3:8b", covers=(e1.id, e3.id),
        )
        assert ep is not None and ep.kind == KIND_EPISODE
        ep_text = (wiki.user_root / ep.rel_path).read_text(encoding="utf-8")
        assert "권한 문제로 결론" in ep_text
        assert f"`#{e1.id}`" in ep_text

        long_entry = record_entry(db, kind=KIND_INPUT, body="가" * (_MD_BODY_LIMIT + 500), wiki=wiki)
        assert long_entry is not None
        assert len(long_entry.body) == _MD_BODY_LIMIT + 500  # DB엔 전문
        assert "생략" in (wiki.user_root / long_entry.rel_path).read_text(encoding="utf-8")

        delete_entry(db, e3.id)
        assert get_entry(db, e3.id) is None
        db.close()

    print("history_store self-check ok")
