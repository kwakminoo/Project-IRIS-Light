"""꺼져 있어도 실행 · 루틴별 모델 · 목록 화면."""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.runtime.backend_route import (  # noqa: E402
    resolve_backend_route,
    route_for_routine,
)
from iris.storage.database import Database  # noqa: E402
from iris.storage.routines import (  # noqa: E402
    create_routine,
    get_routine,
    list_routines,
    update_routine,
)
from iris.system import routine_wake  # noqa: E402
from iris.system.desktop_toast import build_toast_script  # noqa: E402
from iris.ui.settings.routines_box import (  # noqa: E402
    COL_LAST,
    COL_MODEL,
    COL_NAME,
    COL_ON,
    COL_SEARCH,
    COL_WAKE,
    COL_WHEN,
    build_routines_box,
)


class PerRoutineModelTests(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(Path(self._tmp.name) / "r.db")
        self.settings = SimpleNamespace(
            hermes_enabled=False, ollama_base_url="http://127.0.0.1:11434/v1"
        )

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_unpinned_routine_uses_the_current_model(self) -> None:
        r = create_routine(self.db, name="A", task="뭔가")
        route, note = route_for_routine(self.settings, self.db, r, "gemma4:free")
        self.assertEqual(route.model, "gemma4:free")
        self.assertEqual(note, "")

    def test_pinned_routine_uses_its_own_model(self) -> None:
        r = create_routine(self.db, name="B", task="뭔가", model="qwen3:32b")
        route, note = route_for_routine(self.settings, self.db, r, "gemma4:free")
        self.assertEqual(route.model, "qwen3:32b")
        self.assertEqual(note, "")

    def test_broken_pin_falls_back_and_says_so(self) -> None:
        """고정해 둔 API 가 설정에서 지워졌을 때 조용히 멈추면 안 된다."""
        r = create_routine(self.db, name="C", task="뭔가", model="api:gone:x")
        route, note = route_for_routine(self.settings, self.db, r, "gemma4:free")
        self.assertEqual(route.model, "gemma4:free")
        self.assertIn("api:gone:x", note)
        self.assertIn("쓸 수 없어", note)

    def test_no_model_at_all_is_reported_not_guessed(self) -> None:
        r = create_routine(self.db, name="D", task="뭔가")
        route, note = route_for_routine(self.settings, self.db, r, "")
        self.assertIsNone(route)
        self.assertIn("정하지 못했", note)

    def test_pin_survives_a_round_trip(self) -> None:
        r = create_routine(self.db, name="E", task="뭔가", model="qwen3:32b")
        self.assertEqual(get_routine(self.db, r.id).model, "qwen3:32b")
        cleared = update_routine(self.db, r.id, model="")
        self.assertEqual(cleared.model, "")

    def test_hermes_routes_everything_through_the_gateway(self) -> None:
        hermes = SimpleNamespace(
            hermes_enabled=True,
            hermes_base_url="http://127.0.0.1:8642/v1",
            hermes_api_key="k",
            hermes_command="hermes",
            ollama_base_url="http://127.0.0.1:11434/v1",
        )
        with patch(
            "iris.infrastructure.iris_agent_client.resolve_iris_agent_inference",
            side_effect=lambda m, **kw: SimpleNamespace(model=f"up/{m}", label=m),
        ):
            route = resolve_backend_route(hermes, self.db, "api:ab:remote")
        self.assertEqual(route.backend, "hermes")
        self.assertEqual(route.target.model, "up/api:ab:remote")


class WakeTaskTests(TestCase):
    def test_command_quotes_paths_with_spaces(self) -> None:
        cmd = routine_wake.build_task_command(
            Path(r"C:\py w\pythonw.exe"), Path(r"C:\my proj\routine_cli.py")
        )
        self.assertEqual(cmd.count('"'), 4)
        self.assertTrue(cmd.endswith(" tick"))

    def test_master_task_not_per_routine(self) -> None:
        """루틴마다 작업을 만들면 잔재가 남는다 — 이름이 하나여야 한다."""
        self.assertNotIn("{", routine_wake.TASK_NAME)
        self.assertEqual(routine_wake.TASK_NAME, r"\IrisLight\RoutineWake")

    def test_sync_removes_the_task_when_nothing_wants_it(self) -> None:
        with patch.object(routine_wake, "is_supported", return_value=True), patch.object(
            routine_wake, "query"
        ) as q, patch.object(routine_wake, "unregister") as unreg, patch.object(
            routine_wake, "register"
        ) as reg:
            q.return_value = routine_wake.WakeStatus(True, "등록됨")
            unreg.return_value = routine_wake.WakeStatus(False, "해제됨")
            routine_wake.sync(False)
            unreg.assert_called_once()
            reg.assert_not_called()

    def test_sync_does_not_delete_a_task_that_never_existed(self) -> None:
        """schtasks 는 프로세스를 띄운다 — 할 일이 없으면 부르지 않는다."""
        with patch.object(routine_wake, "is_supported", return_value=True), patch.object(
            routine_wake, "query"
        ) as q, patch.object(routine_wake, "unregister") as unreg:
            q.return_value = routine_wake.WakeStatus(False, "등록 안 됨")
            status = routine_wake.sync(False)
            unreg.assert_not_called()
            self.assertFalse(status.registered)

    def test_sync_registers_only_when_missing(self) -> None:
        with patch.object(routine_wake, "is_supported", return_value=True), patch.object(
            routine_wake, "query"
        ) as q, patch.object(routine_wake, "register") as reg:
            q.return_value = routine_wake.WakeStatus(True, "등록됨")
            routine_wake.sync(True)
            reg.assert_not_called()

            q.return_value = routine_wake.WakeStatus(False, "등록 안 됨")
            reg.return_value = routine_wake.WakeStatus(True, "5분마다 확인")
            routine_wake.sync(True)
            reg.assert_called_once()

    def test_korean_not_found_message_is_understood(self) -> None:
        """schtasks 는 콘솔 코드페이지로 말한다 — 한글 안내문을 놓치면 안 된다."""
        korean = "오류: 지정된 작업 이름을 찾을 수 없습니다.".encode("cp949")
        self.assertIn("찾을 수 없", routine_wake._decode(korean))

    def test_unsupported_platform_degrades_quietly(self) -> None:
        with patch.object(routine_wake, "is_supported", return_value=False):
            self.assertFalse(routine_wake.register().registered)
            self.assertFalse(routine_wake.query().registered)
            self.assertFalse(routine_wake.unregister().registered)


class ToastTests(TestCase):
    def test_user_text_cannot_break_out_of_the_script(self) -> None:
        script = build_toast_script("'; Remove-Item C:\\ -Recurse; '", "<b>&</b>")
        self.assertEqual(script.count("'") % 2, 0)
        self.assertIn("&lt;b&gt;", script)
        self.assertNotIn("<b>", script)


class RoutinesBoxTests(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(Path(self._tmp.name) / "r.db")
        self.base = datetime(2026, 9, 29, 8, 0)
        self.a = create_routine(
            self.db, name="아침 뉴스", task="뉴스 3개", time_of_day="09:00", now=self.base
        )
        self.b = create_routine(
            self.db, name="주간 정리", task="메일 정리", kind="weekly",
            weekdays="fri", time_of_day="18:00", now=self.base,
        )
        self.ran: list[int] = []
        self.box = build_routines_box(
            self.db,
            model_names=["qwen3:8b", "api:ab:remote"],
            on_run_now=lambda rid: (self.ran.append(rid), True)[1],
        )

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_table_lists_every_routine(self) -> None:
        table = self.box.routines_table
        self.assertEqual(table.rowCount(), 2)
        names = {table.item(i, COL_NAME).text() for i in range(2)}
        self.assertEqual(names, {"아침 뉴스", "주간 정리"})
        self.assertEqual(table.item(0, COL_WHEN).text(), "매일 09:00")
        self.assertIn("금", table.item(1, COL_WHEN).text())

    def test_unchecking_pauses_without_deleting(self) -> None:
        table = self.box.routines_table
        table.item(0, COL_ON).setCheckState(Qt.CheckState.Unchecked)

        self.assertFalse(get_routine(self.db, self.a.id).enabled)
        self.assertEqual(len(list_routines(self.db)), 2)
        self.assertIn("멈춤", self.box.routine_status.text())

    def test_rechecking_resumes(self) -> None:
        table = self.box.routines_table
        table.item(0, COL_ON).setCheckState(Qt.CheckState.Unchecked)
        self.box.routines_table.item(0, COL_ON).setCheckState(Qt.CheckState.Checked)
        self.assertTrue(get_routine(self.db, self.a.id).enabled)

    def test_editor_fills_from_the_selected_row(self) -> None:
        self.box.routines_table.selectRow(1)
        self.assertEqual(self.box.routine_kind.currentData(), "weekly")
        self.assertEqual(self.box.routine_time.text(), "18:00")
        self.assertEqual(self.box.routine_weekdays.text(), "fri")

    def test_apply_saves_schedule_model_and_wake(self) -> None:
        self.box.routines_table.selectRow(0)
        self.box.routine_time.setText("07:30")
        self.box.routine_deliver.setText("음성")
        self.box.routine_model.setCurrentIndex(self.box.routine_model.findData("qwen3:8b"))
        self.box.routine_wake.setChecked(True)
        self.box.routine_apply()

        saved = get_routine(self.db, self.a.id)
        self.assertEqual(saved.time_of_day, "07:30")
        self.assertEqual(saved.deliver, "voice")
        self.assertEqual(saved.model, "qwen3:8b")
        self.assertTrue(saved.wake_when_closed)

    def test_model_can_be_unpinned_from_the_combo(self) -> None:
        update_routine(self.db, self.a.id, model="qwen3:8b")
        self.box.reload_routines()
        self.box.routines_table.selectRow(0)
        self.box.routine_model.setCurrentIndex(self.box.routine_model.findData(""))
        self.box.routine_apply()
        self.assertEqual(get_routine(self.db, self.a.id).model, "")

    def test_run_now_calls_back_into_the_window(self) -> None:
        from PyQt6.QtWidgets import QPushButton

        self.box.routines_table.selectRow(0)
        run_btn = next(
            b for b in self.box.findChildren(QPushButton) if b.text() == "지금 실행"
        )
        run_btn.click()
        self.assertEqual(self.ran, [self.a.id])
        self.assertIn("실행 시작", self.box.routine_status.text())

    def test_table_shows_model_and_wake_columns(self) -> None:
        update_routine(self.db, self.b.id, model="qwen3:8b", wake_when_closed=True)
        self.box.reload_routines()
        table = self.box.routines_table
        row = next(i for i in range(table.rowCount()) if table.item(i, COL_NAME).text() == "주간 정리")
        self.assertEqual(table.item(row, COL_MODEL).text(), "qwen3:8b")
        self.assertEqual(table.item(row, COL_WAKE).text(), "O")

    def test_unpinned_row_says_current_model(self) -> None:
        table = self.box.routines_table
        self.assertEqual(table.item(0, COL_MODEL).text(), "현재 모델")

    def test_empty_list_shows_a_hint_instead_of_a_blank_table(self) -> None:
        from iris.storage.routines import delete_routine

        delete_routine(self.db, self.a.id)
        delete_routine(self.db, self.b.id)
        self.box.reload_routines()
        self.assertEqual(self.box.routines_table.rowCount(), 0)
        self.assertFalse(self.box.routines_table.isVisible())
