"""IRIS Light 슬림 SQLite — 프로필·알림·모니터 타깃."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def default_db_path() -> Path:
    base = Path.home() / ".iris-light"
    base.mkdir(parents=True, exist_ok=True)
    return base / "iris_light.db"


class Database:
    """UI용 최소 스키마."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_db_path()
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=15.0)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=15000")
            self._init_schema()

    def _execute(self, sql: str, params: Any = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def _commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def _init_schema(self) -> None:
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS user_preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                focus_hint TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS notification_prefs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id INTEGER,
                category TEXT NOT NULL DEFAULT '',
                pref_key TEXT NOT NULL,
                pref_value TEXT NOT NULL,
                UNIQUE(target_id, category, pref_key)
            )
            """
        )
        self._execute(
            """
            CREATE TABLE IF NOT EXISTS notification_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id INTEGER,
                event_id INTEGER,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                user_decision TEXT NOT NULL DEFAULT 'shown',
                created_at TEXT NOT NULL
            )
            """
        )
        self._commit()

    def get_preference(self, key: str, default: str = "") -> str:
        row = self._execute(
            "SELECT value FROM user_preferences WHERE key = ?", (key,)
        ).fetchone()
        return str(row["value"]) if row else default

    def set_preference(self, key: str, value: str) -> None:
        self._execute(
            "INSERT INTO user_preferences(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._commit()

    def list_targets(self, enabled_only: bool = True) -> list[sqlite3.Row]:
        if enabled_only:
            return list(
                self._execute(
                    "SELECT * FROM targets WHERE enabled = 1 ORDER BY id DESC"
                ).fetchall()
            )
        return list(self._execute("SELECT * FROM targets ORDER BY id DESC").fetchall())

    def set_target_enabled(self, target_id: int, enabled: bool) -> None:
        self._execute(
            "UPDATE targets SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, target_id),
        )
        self._commit()

    def set_notification_pref(
        self,
        pref_key: str,
        pref_value: str,
        *,
        target_id: int | None = None,
        category: str = "",
    ) -> None:
        self._execute(
            """
            INSERT INTO notification_prefs(target_id, category, pref_key, pref_value)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(target_id, category, pref_key)
            DO UPDATE SET pref_value = excluded.pref_value
            """,
            (target_id, category, pref_key, pref_value),
        )
        self._commit()

    def get_notification_pref(
        self, pref_key: str, *, target_id: int | None = None, category: str = ""
    ) -> Optional[str]:
        row = self._execute(
            """
            SELECT pref_value FROM notification_prefs
            WHERE pref_key = ? AND IFNULL(target_id, -1) = IFNULL(?, -1)
              AND category = ?
            """,
            (pref_key, target_id, category),
        ).fetchone()
        return str(row["pref_value"]) if row else None

    def is_target_notification_disabled(self, target_id: int) -> bool:
        return self.get_notification_pref("disabled", target_id=target_id, category="") == "1"

    def is_notification_ignored(self, target_id: int, category: str) -> bool:
        return self.get_notification_pref("ignore", target_id=target_id, category=category) == "1"

    def get_notification_snooze_until(self, target_id: int, category: str) -> str | None:
        return self.get_notification_pref("snooze_until", target_id=target_id, category=category)

    def get_notification_cooldown_seconds(
        self, target_id: int, category: str, default: float = 90.0
    ) -> float:
        raw = self.get_notification_pref("cooldown", target_id=target_id, category=category)
        if raw is None:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    def get_last_notification_shown_at(self, target_id: int, category: str) -> str | None:
        return self.get_notification_pref("last_shown_at", target_id=target_id, category=category)

    def set_last_notification_shown_at(self, target_id: int, category: str) -> None:
        self.set_notification_pref(
            "last_shown_at",
            datetime.utcnow().isoformat(),
            target_id=target_id,
            category=category,
        )

    def insert_notification_log(
        self,
        target_id: int | None,
        event_id: int | None,
        category: str,
        title: str,
        message: str,
        user_decision: str = "shown",
    ) -> int:
        cur = self._execute(
            """
            INSERT INTO notification_log(
                target_id, event_id, category, title, message, user_decision, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_id,
                event_id,
                category,
                title,
                message,
                user_decision,
                datetime.utcnow().isoformat(),
            ),
        )
        self._commit()
        return int(cur.lastrowid or 0)
