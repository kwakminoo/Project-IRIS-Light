"""저장된 위키 노트 검색. History 대화 색인과 테이블을 나누어 둔다."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import numpy as np

from iris.knowledge.history_index import Embedder, build_fts_query, chunk_text, like_terms
from iris.knowledge.iris_wiki import IrisWiki, markdown_heading
from iris.knowledge.wiki_places import (
    KNOWLEDGE_PREFIXES,
    TRAITS_REL,
    is_knowledge_rel,
    is_sensitive,
)
from iris.storage.database import Database

_RRF_K = 60
_POOL = 40
_TOP_K = 3

_HEADER = (
    "# Iris Wiki 노트 (저장된 자료)\n\n"
    "아래는 위키에 저장해 둔 노트 발췌다. 이전 대화 기록과 다른 출처다.\n"
)


@dataclass(frozen=True)
class NoteHit:
    rel_path: str
    title: str
    excerpt: str
    score: float
    similarity: float | None


def _unit(vec: list[float]) -> np.ndarray:
    arr = np.asarray(vec, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    if norm <= 0.0:
        return arr
    return arr / norm


def ensure_note_schema(db: Database) -> bool:
    db._execute(
        """
        CREATE TABLE IF NOT EXISTS wiki_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rel_path TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            folder TEXT NOT NULL,
            place_id TEXT NOT NULL DEFAULT '',
            sensitive INTEGER NOT NULL DEFAULT 0,
            mtime_ns INTEGER NOT NULL DEFAULT 0,
            size INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    db._execute(
        """
        CREATE TABLE IF NOT EXISTS wiki_note_vectors (
            note_id INTEGER NOT NULL,
            chunk_ix INTEGER NOT NULL,
            model TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL,
            PRIMARY KEY (note_id, chunk_ix)
        )
        """
    )
    db._execute(
        """
        CREATE TABLE IF NOT EXISTS wiki_proto_vectors (
            place_key TEXT NOT NULL,
            model TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL,
            PRIMARY KEY (place_key, model)
        )
        """
    )
    ok = True
    try:
        db._execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS wiki_notes_fts "
            "USING fts5(title, body, tokenize='trigram')"
        )
    except sqlite3.Error:
        ok = False
    db._commit()
    return ok


def _folder_of(rel: str) -> str:
    return rel.rsplit("/", 1)[0] if "/" in rel else ""


def iter_knowledge_files(wiki: IrisWiki) -> list:
    found = []
    root = wiki.user_root
    for prefix in KNOWLEDGE_PREFIXES:
        folder = root / prefix.strip("/")
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*.md")):
            if not path.name.startswith("."):
                found.append(path)
    traits = root / TRAITS_REL
    if traits.is_file():
        found.append(traits)
    return found


def _read_note_file(path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _upsert_note(
    db: Database,
    *,
    rel: str,
    title: str,
    body: str,
    place_id: str,
    mtime_ns: int,
    size: int,
    has_fts: bool,
) -> int:
    sensitive = 1 if is_sensitive(f"{title}\n{body}") else 0
    folder = _folder_of(rel)
    row = db._execute("SELECT id FROM wiki_notes WHERE rel_path = ?", (rel,)).fetchone()
    if row is None:
        cur = db._execute(
            """
            INSERT INTO wiki_notes(
                rel_path, title, body, folder, place_id, sensitive, mtime_ns, size
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (rel, title, body, folder, place_id, sensitive, mtime_ns, size),
        )
        note_id = int(cur.lastrowid or 0)
    else:
        note_id = int(row["id"])
        db._execute(
            """
            UPDATE wiki_notes
            SET title=?, body=?, folder=?, place_id=?, sensitive=?, mtime_ns=?, size=?
            WHERE id=?
            """,
            (title, body, folder, place_id, sensitive, mtime_ns, size, note_id),
        )
    db._execute("DELETE FROM wiki_note_vectors WHERE note_id = ?", (note_id,))
    if has_fts:
        db._execute("DELETE FROM wiki_notes_fts WHERE rowid = ?", (note_id,))
        if not sensitive:
            db._execute(
                "INSERT INTO wiki_notes_fts(rowid, title, body) VALUES(?, ?, ?)",
                (note_id, title, body),
            )
    db._commit()
    return note_id


def index_rel(
    db: Database,
    wiki: IrisWiki,
    rel: str,
    *,
    embedder: Embedder | None = None,
    place_id: str = "",
) -> int:
    rel = (rel or "").replace("\\", "/").lstrip("/")
    path = wiki.user_root / rel
    if not path.is_file():
        return 0
    has_fts = ensure_note_schema(db)
    text = _read_note_file(path)
    title = markdown_heading(text) or path.stem
    stat = path.stat()
    mtime_ns = int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9)))
    note_id = _upsert_note(
        db,
        rel=rel,
        title=title,
        body=text,
        place_id=place_id or _folder_of(rel),
        mtime_ns=mtime_ns,
        size=int(stat.st_size),
        has_fts=has_fts,
    )
    if embedder is not None and not is_sensitive(text):
        embed_note(db, note_id, title, text, embedder)
    return note_id


def embed_note(db: Database, note_id: int, title: str, body: str, embedder: Embedder) -> int:
    ensure_note_schema(db)
    chunks = chunk_text(f"{title}\n{body}" if title else body)
    if not chunks:
        return 0
    try:
        vectors = embedder.embed(chunks)
    except Exception:
        return 0
    if len(vectors) != len(chunks):
        return 0
    db._execute("DELETE FROM wiki_note_vectors WHERE note_id = ?", (int(note_id),))
    saved = 0
    for ix, vec in enumerate(vectors):
        arr = _unit(vec)
        if arr.size == 0:
            continue
        db._execute(
            """
            INSERT INTO wiki_note_vectors(note_id, chunk_ix, model, dim, vector)
            VALUES(?, ?, ?, ?, ?)
            """,
            (int(note_id), ix, embedder.model, int(arr.size), arr.tobytes()),
        )
        saved += 1
    db._commit()
    return saved


def sync_knowledge_notes(db: Database, wiki: IrisWiki) -> int:
    has_fts = ensure_note_schema(db)
    seen: set[str] = set()
    changed = 0
    for path in iter_knowledge_files(wiki):
        rel = path.relative_to(wiki.user_root).as_posix()
        seen.add(rel)
        try:
            stat = path.stat()
        except OSError:
            continue
        mtime_ns = int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9)))
        size = int(stat.st_size)
        row = db._execute(
            "SELECT mtime_ns, size FROM wiki_notes WHERE rel_path = ?", (rel,)
        ).fetchone()
        if row is not None and int(row["mtime_ns"]) == mtime_ns and int(row["size"]) == size:
            continue
        text = _read_note_file(path)
        _upsert_note(
            db,
            rel=rel,
            title=markdown_heading(text) or path.stem,
            body=text,
            place_id=_folder_of(rel),
            mtime_ns=mtime_ns,
            size=size,
            has_fts=has_fts,
        )
        changed += 1
    for row in db._execute("SELECT id, rel_path FROM wiki_notes").fetchall():
        rel = str(row["rel_path"])
        if rel in seen or not is_knowledge_rel(rel):
            continue
        if (wiki.user_root / rel).is_file():
            continue
        note_id = int(row["id"])
        db._execute("DELETE FROM wiki_note_vectors WHERE note_id = ?", (note_id,))
        if has_fts:
            db._execute("DELETE FROM wiki_notes_fts WHERE rowid = ?", (note_id,))
        db._execute("DELETE FROM wiki_notes WHERE id = ?", (note_id,))
        changed += 1
    db._commit()
    return changed


def embed_pending_notes(
    db: Database, wiki: IrisWiki, embedder: Embedder, *, limit: int = 8
) -> int:
    ensure_note_schema(db)
    try:
        sync_knowledge_notes(db, wiki)
    except OSError:
        pass
    rows = db._execute(
        """
        SELECT id, title, body FROM wiki_notes
        WHERE sensitive = 0 AND NOT EXISTS (
            SELECT 1 FROM wiki_note_vectors v
            WHERE v.note_id = wiki_notes.id AND v.model = ?
        )
        ORDER BY id DESC LIMIT ?
        """,
        (embedder.model, max(1, int(limit))),
    ).fetchall()
    done = 0
    for row in rows:
        if embed_note(db, int(row["id"]), str(row["title"]), str(row["body"]), embedder) > 0:
            done += 1
    return done


def load_proto_vector(db: Database, model: str, key: str) -> np.ndarray | None:
    ensure_note_schema(db)
    row = db._execute(
        "SELECT dim, vector FROM wiki_proto_vectors WHERE place_key = ? AND model = ?",
        (key, model),
    ).fetchone()
    if row is None:
        return None
    arr = np.frombuffer(row["vector"], dtype=np.float32).copy()
    if int(row["dim"]) != int(arr.size):
        return None
    return arr


def store_proto_vector(db: Database, model: str, key: str, arr: np.ndarray) -> None:
    ensure_note_schema(db)
    db._execute(
        """
        INSERT INTO wiki_proto_vectors(place_key, model, dim, vector)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(place_key, model) DO UPDATE SET dim=excluded.dim, vector=excluded.vector
        """,
        (key, model, int(arr.size), np.asarray(arr, dtype=np.float32).tobytes()),
    )
    db._commit()


def load_folder_vectors(db: Database, model: str) -> dict[str, list[np.ndarray]]:
    ensure_note_schema(db)
    rows = db._execute(
        """
        SELECT n.folder AS folder, v.dim AS dim, v.vector AS vector
        FROM wiki_note_vectors v
        JOIN wiki_notes n ON n.id = v.note_id
        WHERE v.model = ? AND n.sensitive = 0
        """,
        (model,),
    ).fetchall()
    grouped: dict[str, list[np.ndarray]] = {}
    for row in rows:
        arr = np.frombuffer(row["vector"], dtype=np.float32).copy()
        if int(row["dim"]) != int(arr.size) or arr.size == 0:
            continue
        grouped.setdefault(str(row["folder"]), []).append(arr)
    return grouped


def _keyword_ids(db: Database, query: str, limit: int, has_fts: bool) -> list[int]:
    ordered: list[int] = []
    seen: set[int] = set()

    def add(ids: list[int]) -> None:
        for note_id in ids:
            if note_id not in seen:
                seen.add(note_id)
                ordered.append(note_id)

    if has_fts:
        match = build_fts_query(query)
        if match:
            try:
                rows = db._execute(
                    """
                    SELECT rowid AS id FROM wiki_notes_fts
                    WHERE wiki_notes_fts MATCH ?
                    ORDER BY bm25(wiki_notes_fts, 2.0, 1.0)
                    LIMIT ?
                    """,
                    (match, int(limit)),
                ).fetchall()
                add([int(row["id"]) for row in rows])
            except sqlite3.Error:
                pass
    if len(ordered) < int(limit):
        terms = like_terms(query)
        if terms:
            clauses: list[str] = []
            params: list[object] = []
            for term in terms:
                esc = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                clauses.append(
                    "(CASE WHEN title LIKE '%'||?||'%' ESCAPE '\\' "
                    "OR body LIKE '%'||?||'%' ESCAPE '\\' THEN 1 ELSE 0 END)"
                )
                params.extend([esc, esc])
            params.append(int(limit))
            rows = db._execute(
                "SELECT id, (" + " + ".join(clauses) + ") AS hits FROM wiki_notes "
                "WHERE sensitive = 0 AND hits > 0 ORDER BY hits DESC, id DESC LIMIT ?",
                tuple(params),
            ).fetchall()
            add([int(row["id"]) for row in rows])
    return ordered[: int(limit)]


def _vector_ids(db: Database, query: str, embedder: Embedder, limit: int) -> list[tuple[int, float]]:
    try:
        vectors = embedder.embed([query])
    except Exception:
        return []
    if not vectors:
        return []
    query_vec = _unit(vectors[0])
    if query_vec.size == 0:
        return []
    rows = db._execute(
        """
        SELECT v.note_id AS note_id, v.dim AS dim, v.vector AS vector
        FROM wiki_note_vectors v
        JOIN wiki_notes n ON n.id = v.note_id
        WHERE v.model = ? AND n.sensitive = 0
        """,
        (embedder.model,),
    ).fetchall()
    best: dict[int, float] = {}
    for row in rows:
        if int(row["dim"]) != int(query_vec.size):
            continue
        arr = np.frombuffer(row["vector"], dtype=np.float32)
        if arr.size != query_vec.size:
            continue
        score = float(np.dot(query_vec, arr))
        note_id = int(row["note_id"])
        if score > best.get(note_id, -2.0):
            best[note_id] = score
    ordered = sorted(best.items(), key=lambda item: item[1], reverse=True)
    if not ordered:
        return []
    cut = max(0.45, ordered[0][1] - 0.10)
    return [(note_id, score) for note_id, score in ordered[: int(limit)] if score >= cut]


def search_notes(
    db: Database,
    query: str,
    *,
    embedder: Embedder | None = None,
    limit: int = _TOP_K,
) -> list[NoteHit]:
    text = (query or "").strip()
    if not text:
        return []
    has_fts = ensure_note_schema(db)
    keywords = _keyword_ids(db, text, _POOL, has_fts)
    vectors = _vector_ids(db, text, embedder, _POOL) if embedder is not None else []
    fused: dict[int, float] = {}
    similarity: dict[int, float] = {}
    for rank, note_id in enumerate(keywords):
        fused[note_id] = fused.get(note_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
    for rank, (note_id, score) in enumerate(vectors):
        similarity[note_id] = score
        fused[note_id] = fused.get(note_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
    hits: list[NoteHit] = []
    for note_id, score in sorted(fused.items(), key=lambda item: item[1], reverse=True):
        row = db._execute(
            "SELECT rel_path, title, body, sensitive FROM wiki_notes WHERE id = ?",
            (note_id,),
        ).fetchone()
        if row is None or int(row["sensitive"]):
            continue
        body = str(row["body"] or "")
        if is_sensitive(body):
            continue
        excerpt = body.strip()
        hits.append(
            NoteHit(
                rel_path=str(row["rel_path"]),
                title=str(row["title"] or ""),
                excerpt=excerpt,
                score=score,
                similarity=similarity.get(note_id),
            )
        )
        if len(hits) >= int(limit):
            break
    return hits


def empty_stored_block(query: str) -> str:
    q = " ".join((query or "").split())[:80] or "(빈 질문)"
    return (
        "# Iris Wiki 노트 (저장된 자료)\n\n"
        f"「{q}」로 저장 노트를 찾았고 0건이다.\n"
    )


def note_prompt_or_empty(block: str, query: str, on_empty: bool) -> str:
    if (block or "").strip():
        return block
    if on_empty:
        return empty_stored_block(query)
    return ""


def format_note_prompt(hits: list[NoteHit]) -> str:
    if not hits:
        return ""
    blocks = [_HEADER]
    for hit in hits:
        piece = hit.excerpt.strip()
        if not piece:
            continue
        title = hit.title or hit.rel_path
        blocks.append(f"### {title} (user/{hit.rel_path})\n{piece}\n")
    if len(blocks) == 1:
        return ""
    return "\n".join(blocks).strip() + "\n"


def wiki_prompt_for_query(
    db: Database,
    wiki: IrisWiki,
    query: str,
    embedder: Embedder | None = None,
    *,
    limit: int = _TOP_K,
    on_empty: bool = False,
) -> str:
    try:
        sync_knowledge_notes(db, wiki)
    except OSError:
        pass
    block = format_note_prompt(search_notes(db, query, embedder=embedder, limit=limit))
    return note_prompt_or_empty(block, query, on_empty)


if __name__ == "__main__":
    assert format_note_prompt([]) == ""
    assert note_prompt_or_empty("", "환율", False) == ""
    empty = note_prompt_or_empty("", "강화학습", True)
    assert "0건" in empty and "없다고만" not in empty
    assert note_prompt_or_empty("발췌 있음", "강화학습", True) == "발췌 있음"
    print("wiki_note_index empty-block ok")
