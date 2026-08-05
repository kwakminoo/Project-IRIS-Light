"""고정(pin) 대상 관리 — 최대 3개 제한과 영속화."""

from __future__ import annotations

import json
from unittest import TestCase

from iris.monitoring.models import StatusCategory
from iris.monitoring.pin_store import MAX_PINS, PinStore


class _FakeDb:
    """user_preferences만 흉내낸다."""

    def __init__(self, initial: dict[str, str] | None = None) -> None:
        self.prefs = dict(initial or {})

    def get_preference(self, key: str, default: str = "") -> str:
        return self.prefs.get(key, default)

    def set_preference(self, key: str, value: str) -> None:
        self.prefs[key] = value


class PinStoreTests(TestCase):
    def test_pin_and_unpin(self) -> None:
        store = PinStore()
        self.assertTrue(store.pin("Chrome", 10))
        self.assertTrue(store.is_pinned("Chrome"))
        self.assertEqual(store.count(), 1)
        self.assertTrue(store.unpin("Chrome"))
        self.assertFalse(store.is_pinned("Chrome"))

    def test_max_three_pins(self) -> None:
        store = PinStore()
        for i in range(MAX_PINS):
            self.assertTrue(store.pin(f"창{i}", i))
        self.assertTrue(store.is_full())
        self.assertFalse(store.pin("네번째", 99))
        self.assertEqual(store.count(), MAX_PINS)
        self.assertFalse(store.is_pinned("네번째"))

    def test_toggle_reports_full(self) -> None:
        store = PinStore()
        for i in range(MAX_PINS):
            store.pin(f"창{i}", i)
        ok, reason = store.toggle("네번째")
        self.assertFalse(ok)
        self.assertEqual(reason, "full")

    def test_toggle_unpins_when_already_pinned(self) -> None:
        store = PinStore()
        store.pin("Chrome", 10)
        ok, reason = store.toggle("Chrome")
        self.assertTrue(ok)
        self.assertEqual(reason, "unpinned")
        self.assertEqual(store.count(), 0)

    def test_title_match_is_case_insensitive(self) -> None:
        store = PinStore()
        store.pin("Chrome", 10)
        self.assertTrue(store.is_pinned("  chrome  "))
        self.assertFalse(store.pin("CHROME", 11))  # 중복 고정 방지

    def test_empty_title_is_rejected(self) -> None:
        store = PinStore()
        self.assertFalse(store.pin("   ", 1))
        self.assertEqual(store.count(), 0)

    def test_update_result_returns_previous_status(self) -> None:
        store = PinStore()
        store.pin("빌드", 1)
        # 첫 분석은 직전 상태가 없다 → None (최초 결과로 알림을 남발하지 않도록)
        first = store.update_result(
            "빌드", StatusCategory.NORMAL, 0.9, "진행 중", "", "10:00:00"
        )
        self.assertIsNone(first)
        second = store.update_result(
            "빌드", StatusCategory.TASK_STALLED, 0.8, "멈춤", "확인", "10:00:30"
        )
        self.assertEqual(second, StatusCategory.NORMAL)
        pin = store.get("빌드")
        self.assertIsNotNone(pin)
        assert pin is not None
        self.assertEqual(pin.status, StatusCategory.TASK_STALLED)
        self.assertEqual(pin.recommended_action, "확인")

    def test_list_pins_returns_copies(self) -> None:
        """워커가 들고 있는 사본을 고쳐도 원본이 오염되지 않아야 한다."""
        store = PinStore()
        store.pin("Chrome", 10)
        snapshot = store.list_pins()
        snapshot[0].title = "바뀜"
        self.assertTrue(store.is_pinned("Chrome"))

    def test_persists_titles_to_db(self) -> None:
        db = _FakeDb()
        store = PinStore(db)  # type: ignore[arg-type]
        store.pin("Chrome", 10)
        store.pin("빌드", 11)
        saved = json.loads(db.prefs["monitor.pinned_titles"])
        self.assertEqual(saved, ["Chrome", "빌드"])

        restored = PinStore(db)  # type: ignore[arg-type]
        self.assertTrue(restored.is_pinned("Chrome"))
        self.assertTrue(restored.is_pinned("빌드"))
        self.assertEqual(restored.count(), 2)

    def test_restore_honors_max_pins(self) -> None:
        """DB가 손상돼 4개가 들어 있어도 3개까지만 살린다."""
        db = _FakeDb({"monitor.pinned_titles": json.dumps(["a", "b", "c", "d"])})
        store = PinStore(db)  # type: ignore[arg-type]
        self.assertEqual(store.count(), MAX_PINS)
        self.assertFalse(store.is_pinned("d"))

    def test_corrupt_pref_is_ignored(self) -> None:
        db = _FakeDb({"monitor.pinned_titles": "{not json"})
        store = PinStore(db)  # type: ignore[arg-type]
        self.assertEqual(store.count(), 0)
