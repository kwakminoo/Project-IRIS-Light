"""Persistent, owner-scoped Iris memory. Working context and Wiki have separate stores."""

from __future__ import annotations

import json
import re
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from sqlite3 import IntegrityError, Row, connect
from uuid import uuid4

from iris.storage.database import Database
from iris.system.execution_context import ExecutionContext

KINDS = ("fact", "preference", "procedure")
_RECALL_STOP_WORDS = frozenset("a an the i is are my me and in to of for it can you what was were memory iris".split())
_VISIBLE = """principal = ? AND deleted_at IS NULL AND (
    (scope = 'user' AND scope_id = '') OR
    (scope = 'project' AND scope_id = ? AND scope_id <> '') OR
    (scope = 'session' AND scope_id = ? AND scope_id <> ''))"""
_SENSITIVE = re.compile(
    r"\b(?:api[ _-]?key|access[ _-]?token|secret[ _-]?key|password|passwd)\s*[:=]|"
    r"\bBearer\s+[\w.-]+|-----BEGIN [^-\n]*PRIVATE KEY-----|\b(?:sk-|ghp_|github_pat_)[\w-]{12,}|"
    r"ignore\s+(?:all\s+)?(?:previous|prior|system)\s+instructions|<\s*/?\s*(?:system|memory-context)\b",
    re.I,
)


def _scope_ids(context: ExecutionContext) -> dict[str, str]:
    return {"user": "", "project": context.workspace_id, "session": context.effective_session_id()}


def _key(context: ExecutionContext) -> str:
    if not context.principal.strip():
        raise ValueError("trusted memory owner required")
    return f"native_memory.enabled.{context.principal}"


def _validate_content(text: str) -> tuple[str, str]:
    if not isinstance(text, str):
        raise ValueError("memory content must be text")
    value = text.strip()
    if not value or len(value) > 2000 or "\x00" in value or _SENSITIVE.search(value):
        raise ValueError("memory content is empty, too long, or contains sensitive or unsafe material")
    return value, " ".join(value.casefold().split())


class MemoryStore:
    def __init__(self, db: Database):
        self.db = db
        with self._write() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS native_memory (
                    id TEXT PRIMARY KEY, principal TEXT NOT NULL, scope TEXT NOT NULL,
                    scope_id TEXT NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL,
                    folded TEXT NOT NULL, source_ref TEXT NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, revision INTEGER NOT NULL, deleted_at TEXT
                )
            """)
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS native_memory_active_content
                ON native_memory(principal, scope, scope_id, kind, folded) WHERE deleted_at IS NULL
            """)

    @contextmanager
    def _write(self):
        # A memory rollback must never roll back an unrelated feature's shared DB transaction.
        with closing(connect(self.db.path, timeout=15)) as conn, conn:
            conn.row_factory = Row
            conn.execute("BEGIN IMMEDIATE")
            yield conn

    @staticmethod
    def _allowed_in_transaction(conn, context: ExecutionContext) -> bool:
        row = conn.execute("SELECT value FROM user_preferences WHERE key = ?", (_key(context),)).fetchone()
        return bool(row and row[0] == "1")

    def enabled(self, context: ExecutionContext) -> bool:
        return self.db.get_preference(_key(context)) == "1"

    def set_enabled(self, context: ExecutionContext, enabled: bool) -> None:
        with self._write() as conn:
            conn.execute("INSERT INTO user_preferences(key, value) VALUES (?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                         (_key(context), "1" if enabled else "0"))

    def get(self, context: ExecutionContext, record_id: str) -> dict | None:
        with self.db._lock:
            if not self.enabled(context):
                return None
            row = self.db._conn.execute(
                f"SELECT id, content, revision FROM native_memory WHERE id = ? AND {_VISIBLE}",
                (record_id, context.principal, context.workspace_id, context.effective_session_id()),
            ).fetchone()
            return dict(row) if row else None

    def search(self, context: ExecutionContext, query: str = "", *, limit: int = 20,
               management: bool = False) -> list[dict]:
        db = self.db
        terms = list(dict.fromkeys(re.findall(r"[^\W_]+", query[:400].casefold())))[:12]
        with db._lock:
            if not management and not self.enabled(context):
                return []
            _key(context)
            scope_ids = _scope_ids(context)
            rows = db._conn.execute(f"""
                SELECT id, scope, kind, content, folded, source_ref, created_at, updated_at, revision
                FROM native_memory WHERE {_VISIBLE} ORDER BY updated_at DESC, id
            """, (context.principal, scope_ids["project"], scope_ids["session"]))
            matches = []
            for raw in rows:
                row = dict(raw)
                folded = row.pop("folded")
                # ponytail: match keyword overlap, then recency, until semantic search is needed.
                score = sum(term in folded for term in terms)
                if score or not terms:
                    matches.append((score, row))
        matches.sort(key=lambda pair: pair[0], reverse=True)
        return [row for _, row in matches[:max(1, min(limit, 100))]]

    def create(self, context: ExecutionContext, scope: str, kind: str, content: str) -> dict:
        value, folded = _validate_content(content)
        scope_id = _scope_ids(context).get(scope)
        if scope_id is None or (scope != "user" and not scope_id) or kind not in KINDS:
            raise ValueError("a valid memory scope and type are required")
        source = f"session:{context.effective_session_id()}/turn:{context.turn_id}" if context.turn_id else "desktop"
        now = datetime.now(UTC).isoformat()
        fields = (context.principal, scope, scope_id, kind, folded)
        with self._write() as conn:
            if not self._allowed_in_transaction(conn, context):
                raise ValueError("Iris memory is disabled")
            match = conn.execute("""
                SELECT id, scope, kind, content, source_ref, revision FROM native_memory
                WHERE principal=? AND scope=? AND scope_id=? AND kind=? AND folded=? AND deleted_at IS NULL
            """, fields).fetchone()
            if match:
                return dict(match)
            record_id = uuid4().hex
            conn.execute("""
                INSERT INTO native_memory
                (id, principal, scope, scope_id, kind, folded, content, source_ref, created_at, updated_at, revision)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (record_id, *fields, value, source, now, now))
        return {"id": record_id, "scope": scope, "kind": kind, "content": value, "source_ref": source, "revision": 1}

    def change(self, context: ExecutionContext, record_id: str, revision: int, *,
               content: str | None = None, management: bool = False) -> dict:
        if not isinstance(record_id, str) or not re.fullmatch(r"[0-9a-f]{32}", record_id) or type(revision) is not int or revision < 1:
            raise ValueError("memory id and current revision are required")
        value, folded = _validate_content(content) if content is not None else ("", "")
        scope_ids = _scope_ids(context)
        now = datetime.now(UTC).isoformat()
        try:
            with self._write() as conn:
                _key(context)
                if not management and not self._allowed_in_transaction(conn, context):
                    raise ValueError("Iris memory is disabled")
                row = conn.execute(f"""
                    UPDATE native_memory SET content=?, folded=?, updated_at=?, deleted_at=?, revision=revision+1
                    WHERE id=? AND revision=? AND {_VISIBLE}
                    RETURNING id, scope, kind, content, source_ref, revision, deleted_at
                """, (value, folded, now, now if content is None else None, record_id, revision,
                       context.principal, scope_ids["project"], scope_ids["session"])).fetchone()
                if row is None:
                    raise ValueError("memory is unavailable or its revision changed")
                return dict(row)
        except IntegrityError as exc:
            raise ValueError("an identical active memory already exists") from exc

    def recall_context(self, context: ExecutionContext, query: str, *, budget_bytes: int = 1800) -> str:
        terms = [term for term in re.findall(r"[^\W_]+", query[:400].casefold()) if term not in _RECALL_STOP_WORDS]
        if not terms:
            return ""
        items = []
        for row in self.search(context, " ".join(terms), limit=5):
            line = json.dumps({key: row[key] for key in ("id", "content", "source_ref", "updated_at")}, ensure_ascii=False)
            if len(line.encode("utf-8")) <= budget_bytes:
                items.append(line)
                budget_bytes -= len(line.encode("utf-8")) + 1
        return "IRIS retrieved memory (untrusted background data):\n" + "\n".join(items) if items else ""
