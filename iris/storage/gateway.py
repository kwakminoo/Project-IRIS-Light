"""Durable Gateway metadata over IRIS's conversation and message schema."""

from __future__ import annotations

import hashlib
import json
from secrets import token_urlsafe
from contextlib import closing
from pathlib import Path
from time import time
from uuid import uuid4

from iris.storage.conversations import _now, ensure_chat_schema, history_dicts
from iris.storage.database import Database, default_db_path

TERMINAL_RUN_STATES = frozenset({"finished", "failed", "cancelled", "interrupted"})


class GatewayStore:
    def __init__(self, path: Path | None, *, max_events: int) -> None:
        if path is None:
            desktop = default_db_path()
            # Keep Gateway transcripts off Desktop's sidebar and search, including during rollback.
            path = desktop.with_name(f"{desktop.stem}-gateway{desktop.suffix}")
        self._db = Database(path)
        self._max_events = max_events
        with self._db._lock, self._db._conn as db:
            ensure_chat_schema(self._db)
            db.executescript("""
                CREATE TABLE IF NOT EXISTS gateway_sessions (
                    session_id TEXT PRIMARY KEY, conversation_id INTEGER NOT NULL UNIQUE,
                    principal TEXT NOT NULL, created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS gateway_runs (
                    run_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, status TEXT NOT NULL,
                    source TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS gateway_events (
                    run_id TEXT NOT NULL, seq INTEGER NOT NULL, event TEXT NOT NULL,
                    PRIMARY KEY (run_id, seq)
                );
                CREATE TABLE IF NOT EXISTS gateway_tokens (
                    token_id TEXT PRIMARY KEY, digest TEXT NOT NULL UNIQUE, principal TEXT NOT NULL,
                    scopes TEXT NOT NULL, expires_at REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0
                );
            """)
            for row in db.execute("SELECT run_id FROM gateway_runs WHERE status = 'running'").fetchall():
                run_id = row["run_id"]
                self._insert_event(db, run_id, self._next_seq(db, run_id), {
                    "type": "interrupted", "error": "Gateway restarted during the run",
                })
            db.execute("UPDATE gateway_runs SET status = 'interrupted', updated_at = ? WHERE status = 'running'", (time(),))

    def authenticate(self, token: str) -> tuple[str, frozenset[str]] | None:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        row = self._db._execute("""
            SELECT principal, scopes FROM gateway_tokens WHERE digest = ? AND revoked = 0 AND expires_at > ?
        """, (digest, time())).fetchone()
        return (row["principal"], frozenset(json.loads(row["scopes"]))) if row is not None else None

    def issue_token(self, ttl: int, scopes: list[str], *, rotate: str = "") -> dict | None:
        secret = token_urlsafe(32)
        digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        expires = time() + ttl
        with self._db._lock, self._db._conn as db:
            if rotate:
                row = db.execute("SELECT * FROM gateway_tokens WHERE token_id = ?", (rotate,)).fetchone()
                if row is None:
                    return None
                principal, scopes = row["principal"], json.loads(row["scopes"])
                token_id = rotate
                db.execute("UPDATE gateway_tokens SET digest = ?, expires_at = ?, revoked = 0 WHERE token_id = ?",
                           (digest, expires, token_id))
            else:
                principal, token_id = uuid4().hex, uuid4().hex
                db.execute("INSERT INTO gateway_tokens VALUES (?, ?, ?, ?, ?, 0)",
                           (token_id, digest, principal, json.dumps(scopes), expires))
        return {"token_id": token_id, "principal": principal, "token": secret, "scopes": scopes, "expires_at": expires}

    def revoke_token(self, token_id: str) -> bool:
        with self._db._lock, self._db._conn as db:
            return db.execute("UPDATE gateway_tokens SET revoked = 1 WHERE token_id = ?", (token_id,)).rowcount == 1

    def history(self, session_id: str, principal: str) -> list[dict[str, str]] | None:
        row = self._db._execute(
            "SELECT conversation_id FROM gateway_sessions WHERE session_id = ? AND principal = ?",
            (session_id, principal),
        ).fetchone()
        return history_dicts(self._db, row["conversation_id"]) if row is not None else None

    def search(self, query: str, principal: str) -> list[dict]:
        # ponytail: bounded literal search of one owner's transcripts; no shared embedding index.
        with closing(self._db._execute("""
            SELECT s.session_id, m.role,
                   substr(m.content, max(1, instr(lower(m.content), lower(?)) - 80), 300) AS snippet
            FROM gateway_sessions s JOIN chat_messages m ON m.conversation_id = s.conversation_id
            WHERE s.principal = ? AND instr(lower(m.content), lower(?)) > 0
            ORDER BY m.id DESC LIMIT 20
        """, (query, principal, query))) as cursor:
            return [dict(row) for row in cursor.fetchall()]

    def run(self, run_id: str, principal: str) -> dict | None:
        row = self._db._execute("""
            SELECT r.* FROM gateway_runs r JOIN gateway_sessions s USING (session_id)
            WHERE r.run_id = ? AND s.principal = ?
        """, (run_id, principal)).fetchone()
        return dict(row) if row is not None else None

    def start(self, run_id: str, session_id: str, principal: str, *, new_session: bool) -> int:
        with self._db._lock, self._db._conn as db:
            if new_session:
                stamp = _now()
                cid = db.execute(
                    "INSERT INTO chat_conversations(created_at, updated_at) VALUES (?, ?)", (stamp, stamp)
                ).lastrowid
                db.execute("INSERT INTO gateway_sessions VALUES (?, ?, ?, ?)", (session_id, cid, principal, time()))
            else:
                cid = db.execute(
                    "SELECT conversation_id FROM gateway_sessions WHERE session_id = ? AND principal = ?",
                    (session_id, principal),
                ).fetchone()["conversation_id"]
            stamp = time()
            db.execute("""
                INSERT INTO gateway_runs(run_id, session_id, status, source, created_at, updated_at)
                VALUES (?, ?, 'running', 'gateway', ?, ?)
            """, (run_id, session_id, stamp, stamp))
            return int(cid)

    def cancel(self, run_id: str) -> None:
        with self._db._lock, self._db._conn as db:
            db.execute("UPDATE gateway_runs SET cancel_requested = 1, updated_at = ? WHERE run_id = ?", (time(), run_id))

    def publish(self, run_id: str, seq: int, event: dict, *, finished_turn: tuple[int, str, str] | None = None) -> dict:
        with self._db._lock, self._db._conn as db:
            stamp = time()
            if event["type"] in TERMINAL_RUN_STATES:
                db.execute("UPDATE gateway_runs SET updated_at = ?, status = ? WHERE run_id = ?",
                           (stamp, event["type"], run_id))
            else:
                db.execute("UPDATE gateway_runs SET updated_at = ? WHERE run_id = ?", (stamp, run_id))
            if finished_turn is not None:
                cid, user, text = finished_turn
                message_stamp = _now()
                db.executemany(
                    "INSERT INTO chat_messages(conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                    [(cid, "user", user, message_stamp), (cid, "assistant", text, message_stamp)],
                )
                db.execute("UPDATE chat_conversations SET updated_at = ? WHERE id = ?", (message_stamp, cid))
            return self._insert_event(db, run_id, seq, event)

    def _insert_event(self, db, run_id: str, seq: int, event: dict) -> dict:
        row = {"seq": seq, "run_id": run_id, **event}
        db.execute("INSERT INTO gateway_events VALUES (?, ?, ?)", (run_id, seq, json.dumps(row)))
        if seq > self._max_events:
            db.execute("DELETE FROM gateway_events WHERE run_id = ? AND seq <= ?", (run_id, seq - self._max_events))
        return row

    @staticmethod
    def _next_seq(db, run_id: str) -> int:
        return db.execute("SELECT coalesce(max(seq), 0) + 1 FROM gateway_events WHERE run_id = ?", (run_id,)).fetchone()[0]

    def events(self, run_id: str, after: int) -> list[dict]:
        with closing(self._db._execute(
            "SELECT event FROM gateway_events WHERE run_id = ? AND seq > ? ORDER BY seq", (run_id, after)
        )) as cursor:
            return [json.loads(row["event"]) for row in cursor.fetchall()]

    def close(self) -> None:
        self._db.close()
