"""learned_workflows SQLite repository — Database를 비대하게 만들지 않음."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from iris.learning.models import LearnedWorkflow
from iris.storage.database import Database


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class LearnedWorkflowRepository:
    def __init__(self, db: Database) -> None:
        self._db = db
        self.ensure_schema()

    def ensure_schema(self) -> None:
        self._db._execute(
            """
            CREATE TABLE IF NOT EXISTS learned_workflows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'ready',
                source_session_id TEXT NOT NULL DEFAULT '',
                trace_path TEXT NOT NULL DEFAULT '',
                primary_apps TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_run_at TEXT NOT NULL DEFAULT '',
                run_count INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        self._db._execute(
            """
            CREATE TABLE IF NOT EXISTS learned_workflow_runs (
                run_id TEXT PRIMARY KEY,
                workflow_id INTEGER NOT NULL,
                trace_id TEXT NOT NULL,
                task TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self._db._commit()

    def _row_to_wf(self, row: Any) -> LearnedWorkflow:
        return LearnedWorkflow(
            id=int(row["id"]),
            trace_id=str(row["trace_id"]),
            name=str(row["name"]),
            summary=str(row["summary"] or ""),
            status=str(row["status"]),
            source_session_id=str(row["source_session_id"] or ""),
            trace_path=str(row["trace_path"] or ""),
            primary_apps=str(row["primary_apps"] or ""),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            last_run_at=str(row["last_run_at"] or ""),
            run_count=int(row["run_count"] or 0),
            enabled=int(row["enabled"] or 0),
        )

    def upsert(
        self,
        *,
        trace_id: str,
        name: str,
        summary: str,
        status: str,
        source_session_id: str,
        trace_path: str,
        primary_apps: str = "",
        enabled: int = 1,
    ) -> LearnedWorkflow:
        now = _utcnow()
        existing = self.get_by_trace_id(trace_id)
        if existing is None:
            self._db._execute(
                """
                INSERT INTO learned_workflows(
                    trace_id, name, summary, status, source_session_id,
                    trace_path, primary_apps, created_at, updated_at, enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    name,
                    summary,
                    status,
                    source_session_id,
                    trace_path,
                    primary_apps,
                    now,
                    now,
                    enabled,
                ),
            )
        else:
            self._db._execute(
                """
                UPDATE learned_workflows SET
                    name=?, summary=?, status=?, source_session_id=?,
                    trace_path=?, primary_apps=?, updated_at=?, enabled=?
                WHERE trace_id=?
                """,
                (
                    name,
                    summary,
                    status,
                    source_session_id,
                    trace_path,
                    primary_apps,
                    now,
                    enabled,
                    trace_id,
                ),
            )
        self._db._commit()
        wf = self.get_by_trace_id(trace_id)
        assert wf is not None
        return wf

    def get(self, workflow_id: int) -> LearnedWorkflow | None:
        row = self._db._execute(
            "SELECT * FROM learned_workflows WHERE id = ?", (workflow_id,)
        ).fetchone()
        return self._row_to_wf(row) if row else None

    def get_by_trace_id(self, trace_id: str) -> LearnedWorkflow | None:
        row = self._db._execute(
            "SELECT * FROM learned_workflows WHERE trace_id = ?", (trace_id,)
        ).fetchone()
        return self._row_to_wf(row) if row else None

    def list(self, *, enabled_only: bool = False) -> list[LearnedWorkflow]:
        if enabled_only:
            rows = self._db._execute(
                "SELECT * FROM learned_workflows WHERE enabled = 1 ORDER BY id DESC"
            ).fetchall()
        else:
            rows = self._db._execute(
                "SELECT * FROM learned_workflows ORDER BY id DESC"
            ).fetchall()
        return [self._row_to_wf(r) for r in rows]

    def mark_run(self, workflow_id: int) -> None:
        now = _utcnow()
        self._db._execute(
            """
            UPDATE learned_workflows
            SET run_count = run_count + 1, last_run_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, workflow_id),
        )
        self._db._commit()

    def save_run(
        self,
        *,
        run_id: str,
        workflow_id: int,
        trace_id: str,
        task: str,
        status: str,
        message: str = "",
        started_at: str = "",
        finished_at: str = "",
    ) -> None:
        started = started_at or _utcnow()
        self._db._execute(
            """
            INSERT INTO learned_workflow_runs(
                run_id, workflow_id, trace_id, task, status, message, started_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                status=excluded.status,
                message=excluded.message,
                finished_at=excluded.finished_at
            """,
            (run_id, workflow_id, trace_id, task, status, message, started, finished_at),
        )
        self._db._commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self._db._execute(
            "SELECT * FROM learned_workflow_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if not row:
            return None
        return {k: row[k] for k in row.keys()}
