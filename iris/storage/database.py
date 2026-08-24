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
                created_at TEXT NOT NULL,
                handle TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'UNKNOWN',
                last_event TEXT NOT NULL DEFAULT '',
                last_checked_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self._ensure_target_title_index()
        self._migrate_targets()
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

    def _ensure_target_title_index(self) -> None:
        """upsert_target 의 ON CONFLICT(title) 이 걸릴 유니크 인덱스.

        구버전 DB에 중복 제목이 남아 있으면 인덱스 생성이 실패할 수 있는데,
        그 경우에도 앱은 떠야 하므로 중복을 정리한 뒤 한 번 더 시도한다."""
        try:
            self._execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_targets_title ON targets(title)"
            )
            return
        except sqlite3.Error:
            pass
        try:
            # 같은 제목이 여러 건이면 가장 최근 것만 남긴다
            self._execute(
                "DELETE FROM targets WHERE id NOT IN "
                "(SELECT MAX(id) FROM targets GROUP BY title)"
            )
            self._execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_targets_title ON targets(title)"
            )
            self._commit()
        except sqlite3.Error:
            # 인덱스 없이도 조회는 되므로 앱 기동을 막지 않는다.
            # upsert_target 이 ON CONFLICT 실패를 스스로 처리한다.
            pass

    def _migrate_targets(self) -> None:
        """구버전 DB 보정.

        targets 는 원래 status/last_event/last_checked_at 없이 만들어졌는데
        UI(unified_monitor_panel)와 도메인 모델(MonitoredTarget)은 이 컬럼들이
        있다고 가정한다. 이미 만들어진 ~/.iris-light/iris_light.db 는
        CREATE TABLE IF NOT EXISTS 로는 갱신되지 않으므로 여기서 채운다."""
        try:
            existing = {
                str(row["name"])
                for row in self._execute("PRAGMA table_info(targets)").fetchall()
            }
        except sqlite3.Error:
            return
        if not existing:
            return
        added = False
        for column, ddl in (
            ("handle", "ALTER TABLE targets ADD COLUMN handle TEXT NOT NULL DEFAULT ''"),
            ("status", "ALTER TABLE targets ADD COLUMN status TEXT NOT NULL DEFAULT 'UNKNOWN'"),
            ("last_event", "ALTER TABLE targets ADD COLUMN last_event TEXT NOT NULL DEFAULT ''"),
            (
                "last_checked_at",
                "ALTER TABLE targets ADD COLUMN last_checked_at TEXT NOT NULL DEFAULT ''",
            ),
        ):
            if column in existing:
                continue
            try:
                self._execute(ddl)
                added = True
            except sqlite3.Error:
                # 다른 프로세스가 먼저 추가했을 수 있다 — 다음 조회에서 확인된다
                pass
        if added:
            self._commit()

    def upsert_target(
        self,
        title: str,
        *,
        kind: str = "desktop_window",
        focus_hint: str = "",
        handle: str = "",
        enabled: bool = True,
    ) -> Optional[int]:
        """모니터링 대상 등록/재활성화. 제목이 키다.

        hwnd 는 앱을 다시 켜면 달라지므로 PinStore 와 같은 기준(제목)을 쓴다."""
        name = (title or "").strip()
        if not name:
            return None
        try:
            self._insert_target_on_conflict(name, kind, focus_hint, handle, enabled)
        except sqlite3.OperationalError:
            # 유니크 인덱스가 없는 DB — ON CONFLICT 대상이 없어 실패한다.
            # 수동 upsert 로 폴백.
            self._upsert_target_fallback(name, kind, focus_hint, handle, enabled)
        self._commit()
        row = self._execute("SELECT id FROM targets WHERE title = ?", (name,)).fetchone()
        return int(row["id"]) if row else None

    def _insert_target_on_conflict(
        self, name: str, kind: str, focus_hint: str, handle: str, enabled: bool
    ) -> None:
        self._execute(
            """
            INSERT INTO targets(kind, title, focus_hint, enabled, created_at, handle)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(title) DO UPDATE SET
                kind = excluded.kind,
                enabled = excluded.enabled,
                handle = excluded.handle,
                focus_hint = CASE
                    WHEN excluded.focus_hint != '' THEN excluded.focus_hint
                    ELSE targets.focus_hint
                END
            """,
            (
                kind,
                name,
                focus_hint,
                1 if enabled else 0,
                datetime.now().isoformat(timespec="seconds"),
                handle,
            ),
        )

    def _upsert_target_fallback(
        self, name: str, kind: str, focus_hint: str, handle: str, enabled: bool
    ) -> None:
        cur = self._execute(
            "UPDATE targets SET kind = ?, enabled = ?, handle = ? WHERE title = ?",
            (kind, 1 if enabled else 0, handle, name),
        )
        if cur.rowcount:
            if focus_hint:
                self._execute(
                    "UPDATE targets SET focus_hint = ? WHERE title = ?",
                    (focus_hint, name),
                )
            return
        self._execute(
            """
            INSERT INTO targets(kind, title, focus_hint, enabled, created_at, handle)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                kind,
                name,
                focus_hint,
                1 if enabled else 0,
                datetime.now().isoformat(timespec="seconds"),
                handle,
            ),
        )

    def update_target_status(
        self,
        title: str,
        *,
        status: str,
        last_event: str = "",
        last_checked_at: str = "",
    ) -> None:
        """분석 결과 반영. 대상이 없으면 아무것도 하지 않는다."""
        name = (title or "").strip()
        if not name:
            return
        self._execute(
            """
            UPDATE targets
               SET status = ?, last_event = ?, last_checked_at = ?
             WHERE title = ?
            """,
            (
                status or "UNKNOWN",
                last_event,
                last_checked_at or datetime.now().isoformat(timespec="seconds"),
                name,
            ),
        )
        self._commit()

    def set_target_enabled_by_title(self, title: str, enabled: bool) -> None:
        """감시 해제 시 행을 지우지 않고 비활성화 — 마지막 상태를 남겨 둔다."""
        name = (title or "").strip()
        if not name:
            return
        self._execute(
            "UPDATE targets SET enabled = ? WHERE title = ?",
            (1 if enabled else 0, name),
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
