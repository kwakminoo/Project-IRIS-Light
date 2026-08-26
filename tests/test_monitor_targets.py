"""모니터링 상태 영속화 — targets 테이블과 PinStore·패널 연동.

이 경로가 통째로 죽어 있어서 "상태: …" 블록이 한 번도 표시되지 않았다.
원인이 두 개였다:
  1) targets 스키마에 status/last_event/last_checked_at 컬럼이 없었다
  2) targets 에 행을 넣는 코드가 아예 없었다
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest import TestCase

from iris.monitoring.models import StatusCategory
from iris.monitoring.pin_store import PinStore
from iris.storage.database import Database
from iris.ui.monitor.unified_monitor_panel import UnifiedMonitorPanel, _row_value

_STATUS_COLUMNS = ("handle", "status", "last_event", "last_checked_at")


def _temp_db(name: str) -> Database:
    path = Path(tempfile.mkdtemp(prefix="iris_targets_")) / name
    return Database(path)


def _columns(db: Database) -> set[str]:
    return {str(r["name"]) for r in db._execute("PRAGMA table_info(targets)").fetchall()}


def _load_meta(db: object) -> dict:
    """패널 인스턴스를 만들지 않고 메타 로더만 돌린다 (Qt 없이 검증)."""

    class _Panel:
        _db = db
        _load_monitor_meta = UnifiedMonitorPanel._load_monitor_meta

    return _Panel()._load_monitor_meta()


class TargetsSchemaTests(TestCase):
    def test_new_db_has_status_columns(self) -> None:
        db = _temp_db("new.db")
        columns = _columns(db)
        for name in _STATUS_COLUMNS:
            self.assertIn(name, columns)

    def test_legacy_db_is_migrated(self) -> None:
        """구버전 DB는 CREATE TABLE IF NOT EXISTS 로 갱신되지 않는다."""
        path = Path(tempfile.mkdtemp(prefix="iris_targets_legacy_")) / "old.db"
        raw = sqlite3.connect(path)
        raw.execute(
            """CREATE TABLE targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                focus_hint TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL)"""
        )
        raw.execute(
            "INSERT INTO targets(kind,title,focus_hint,enabled,created_at)"
            " VALUES(?,?,?,?,?)",
            ("desktop_window", "구버전 창", "", 1, "2026-01-01T00:00:00"),
        )
        raw.commit()
        raw.close()

        db = Database(path)
        for name in _STATUS_COLUMNS:
            self.assertIn(name, _columns(db))

        row = db.list_targets(True)[0]
        self.assertEqual(row["title"], "구버전 창")  # 기존 행 보존
        self.assertEqual(row["status"], "UNKNOWN")

        db.update_target_status("구버전 창", status="NORMAL", last_event="정상")
        self.assertEqual(db.list_targets(True)[0]["status"], "NORMAL")


class TargetsWriteApiTests(TestCase):
    def setUp(self) -> None:
        self.db = _temp_db("write.db")

    def test_upsert_inserts_then_updates(self) -> None:
        first = self.db.upsert_target("Visual Studio Code", handle="123")
        self.assertIsInstance(first, int)
        self.assertEqual(len(self.db.list_targets(True)), 1)

        second = self.db.upsert_target("Visual Studio Code", handle="456")
        self.assertEqual(first, second)  # 제목이 키 — 중복 행이 생기지 않는다
        self.assertEqual(len(self.db.list_targets(False)), 1)
        self.assertEqual(self.db.list_targets(True)[0]["handle"], "456")

    def test_upsert_keeps_status(self) -> None:
        self.db.upsert_target("Chrome")
        self.db.update_target_status("Chrome", status="ERROR_DETECTED", last_event="빌드 실패")
        self.db.upsert_target("Chrome", handle="9")
        row = self.db.list_targets(True)[0]
        self.assertEqual(row["status"], "ERROR_DETECTED")
        self.assertEqual(row["last_event"], "빌드 실패")

    def test_update_status_stamps_time_when_omitted(self) -> None:
        self.db.upsert_target("Chrome")
        self.db.update_target_status("Chrome", status="NORMAL")
        self.assertTrue(self.db.list_targets(True)[0]["last_checked_at"])

    def test_disable_keeps_row(self) -> None:
        self.db.upsert_target("Chrome")
        self.db.set_target_enabled_by_title("Chrome", False)
        self.assertEqual(len(self.db.list_targets(True)), 0)
        self.assertEqual(len(self.db.list_targets(False)), 1)  # 이력은 남는다

    def test_blank_title_is_ignored(self) -> None:
        self.assertIsNone(self.db.upsert_target("   "))
        self.assertEqual(len(self.db.list_targets(False)), 0)


class PinStoreTargetSyncTests(TestCase):
    def setUp(self) -> None:
        self.db = _temp_db("pin.db")
        self.store = PinStore(self.db)

    def test_pin_registers_target(self) -> None:
        self.store.pin("Chrome — 문서", 777)
        rows = self.db.list_targets(True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Chrome — 문서")
        self.assertEqual(rows[0]["handle"], "777")

    def test_analysis_result_is_persisted(self) -> None:
        self.store.pin("Chrome — 문서", 1)
        self.store.update_result(
            "Chrome — 문서",
            StatusCategory.APPROVAL_WAITING,
            0.9,
            "승인 대기 다이얼로그",
            "확인을 누르세요",
            "2026-08-24T17:30:00",
        )
        row = self.db.list_targets(True)[0]
        self.assertEqual(row["status"], "APPROVAL_WAITING")
        self.assertEqual(row["last_event"], "승인 대기 다이얼로그")
        self.assertEqual(row["last_checked_at"], "2026-08-24T17:30:00")

    def test_unpin_disables_but_keeps_history(self) -> None:
        self.store.pin("Chrome — 문서", 1)
        self.store.unpin("Chrome — 문서")
        self.assertEqual(len(self.db.list_targets(True)), 0)
        self.assertEqual(len(self.db.list_targets(False)), 1)

    def test_status_restored_after_restart(self) -> None:
        self.store.pin("Chrome — 문서", 1)
        self.store.update_result(
            "Chrome — 문서",
            StatusCategory.NORMAL,
            0.8,
            "정상 동작",
            "",
            "2026-08-24T18:00:00",
        )
        restarted = PinStore(self.db)  # 앱 재기동
        pin = restarted.get("Chrome — 문서")
        self.assertIsNotNone(pin)
        assert pin is not None
        self.assertEqual(pin.status, StatusCategory.NORMAL)
        self.assertEqual(pin.reason, "정상 동작")
        self.assertEqual(pin.last_checked_at, "2026-08-24T18:00:00")
        self.assertFalse(pin.analyzing)

    def test_db_without_target_api_does_not_break_pinning(self) -> None:
        """user_preferences만 있는 DB(구버전/테스트 더블)에서도 고정은 동작한다."""

        class _PrefsOnlyDb:
            def __init__(self) -> None:
                self.prefs: dict[str, str] = {}

            def get_preference(self, key: str, default: str = "") -> str:
                return self.prefs.get(key, default)

            def set_preference(self, key: str, value: str) -> None:
                self.prefs[key] = value

        store = PinStore(_PrefsOnlyDb())
        self.assertTrue(store.pin("Chrome", 1))
        self.assertTrue(store.is_pinned("Chrome"))
        self.assertTrue(store.unpin("Chrome"))


class MonitorMetaLoadTests(TestCase):
    def test_meta_is_actually_returned(self) -> None:
        db = _temp_db("meta.db")
        db.upsert_target("Chrome — 문서")
        db.update_target_status(
            "Chrome — 문서",
            status="NORMAL",
            last_event="정상 동작",
            last_checked_at="2026-08-24T18:00:00",
        )
        meta = _load_meta(db)
        self.assertIn("chrome — 문서", meta)  # 소문자 키
        entry = meta["chrome — 문서"]
        self.assertEqual(entry.status, "NORMAL")
        self.assertEqual(entry.last_event, "정상 동작")

    def test_disabled_target_is_excluded(self) -> None:
        db = _temp_db("meta_disabled.db")
        db.upsert_target("Chrome")
        db.set_target_enabled_by_title("Chrome", False)
        self.assertEqual(_load_meta(db), {})

    def test_row_missing_columns_falls_back(self) -> None:
        """예전에는 여기서 KeyError 가 나고 `except: continue` 에 먹혔다."""

        class _Row:
            def __init__(self, data: dict) -> None:
                self._data = data

            def keys(self) -> list[str]:
                return list(self._data)

            def __getitem__(self, key: str) -> object:
                return self._data[key]

        class _LegacyDb:
            def list_targets(self, enabled_only: bool = True) -> list:
                return [_Row({"title": "레거시 창", "enabled": 1})]

        meta = _load_meta(_LegacyDb())
        self.assertIn("레거시 창", meta)
        self.assertEqual(meta["레거시 창"].status, "UNKNOWN")
        self.assertEqual(meta["레거시 창"].last_event, "-")

    def test_no_db_returns_empty(self) -> None:
        self.assertEqual(_load_meta(None), {})


class RowValueTests(TestCase):
    def test_missing_key_returns_default(self) -> None:
        self.assertEqual(_row_value({"a": 1}, {"a"}, "b", "fallback"), "fallback")

    def test_none_value_returns_default(self) -> None:
        self.assertEqual(_row_value({"a": None}, {"a"}, "a", "fallback"), "fallback")

    def test_present_value_is_returned(self) -> None:
        self.assertEqual(_row_value({"a": "x"}, {"a"}, "a", "fallback"), "x")
