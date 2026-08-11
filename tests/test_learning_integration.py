"""ShowUI-Aloha Human-Taught Computer-Use 통합 테스트."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QHBoxLayout

# QtWebEngine: 반드시 QApplication 생성 전에 설정
if QApplication.instance() is None:
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

from iris.learning.aloha_adapter import event_to_aloha_message, write_aloha_input
from iris.learning.aloha_executor import MockExecutor
from iris.learning.aloha_learner import MockLearner
from iris.learning.manager import LearningManager
from iris.learning.models import LearningEvent, LearningState, SessionManifest
from iris.learning.workflow_registry import LearnedWorkflowRepository
from iris.storage.database import Database
from iris.ui.widgets.drag_tab import DragTab


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestDragTabLearningButton(unittest.TestCase):
    def setUp(self) -> None:
        self.app = _app()
        from PyQt6.QtWidgets import QWidget

        self.win = QWidget()
        self.tab = DragTab(self.win)

    def test_learning_button_exists(self) -> None:
        self.assertTrue(hasattr(self.tab, "_btn_learning"))
        self.assertIsNotNone(self.tab._btn_learning)

    def test_learning_left_of_mic(self) -> None:
        lay = self.tab.layout()
        assert lay is not None
        ctrl = None
        for i in range(lay.count()):
            item = lay.itemAt(i)
            if item is not None and item.layout() is not None:
                ctrl = item.layout()
        self.assertIsInstance(ctrl, QHBoxLayout)
        assert isinstance(ctrl, QHBoxLayout)
        widgets = []
        for i in range(ctrl.count()):
            w = ctrl.itemAt(i).widget()
            if w is not None:
                widgets.append(w)
        self.assertIn(self.tab._btn_learning, widgets)
        self.assertIn(self.tab._btn_mic, widgets)
        self.assertLess(
            widgets.index(self.tab._btn_learning),
            widgets.index(self.tab._btn_mic),
        )

    def test_state_idle_recording_processing_idle(self) -> None:
        self.tab.set_learning_state(LearningState.IDLE)
        self.assertEqual(self.tab._learning_state, LearningState.IDLE)
        self.assertTrue(self.tab._btn_learning.isEnabled())
        self.assertIn("시작", self.tab._btn_learning.toolTip())

        self.tab.set_learning_state(LearningState.RECORDING)
        self.assertEqual(self.tab._learning_state, LearningState.RECORDING)
        self.assertIn("종료", self.tab._btn_learning.toolTip())

        self.tab.set_learning_state(LearningState.PROCESSING)
        self.assertFalse(self.tab._btn_learning.isEnabled())
        self.assertIn("정리", self.tab._btn_learning.toolTip())

        self.tab.set_learning_state(LearningState.IDLE)
        self.assertTrue(self.tab._btn_learning.isEnabled())
        self.assertEqual(self.tab._learning_state, LearningState.IDLE)

    def test_error_then_idle(self) -> None:
        self.tab.set_learning_state(LearningState.ERROR)
        self.assertEqual(self.tab._learning_state, LearningState.ERROR)
        self.tab.set_learning_state(LearningState.IDLE)
        self.assertEqual(self.tab._learning_state, LearningState.IDLE)

    def test_mic_independent(self) -> None:
        self.tab.set_learning_state(LearningState.RECORDING)
        self.tab.set_mic_recording(True)
        self.assertTrue(self.tab._btn_mic.isChecked())
        self.assertEqual(self.tab._learning_state, LearningState.RECORDING)
        self.tab.set_mic_recording(False)
        self.assertFalse(self.tab._btn_mic.isChecked())
        self.assertEqual(self.tab._learning_state, LearningState.RECORDING)


class TestLearningPipeline(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "t.db")
        self.repo = LearnedWorkflowRepository(self.db)
        self.mgr = LearningManager(
            self.db,
            learner=MockLearner(),
            executor=MockExecutor(self.repo),
        )

    def tearDown(self) -> None:
        try:
            self.db._conn.close()
        except Exception:
            pass
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def test_exclude_learning_control_from_trace(self) -> None:
        events = [
            LearningEvent(
                0.1,
                "click",
                x=1,
                y=1,
                exclude_from_trace=True,
                metadata={"learning_control": True},
            ),
            LearningEvent(0.2, "click", x=10, y=10, process_name="notepad.exe"),
        ]
        msgs = [event_to_aloha_message(e) for e in events]
        self.assertIsNone(msgs[0])
        self.assertIsNotNone(msgs[1])

    def test_session_dir_and_registry(self) -> None:
        sid = "abc123testdemo"
        from iris.learning.paths import session_dir

        sdir = session_dir(sid)
        self.assertTrue(sdir.is_dir())
        events = [
            LearningEvent(0.0, "context", process_name="chrome.exe", window_title="GitHub"),
            LearningEvent(0.5, "click", x=100, y=200, process_name="chrome.exe"),
            LearningEvent(1.0, "key_down", key="A", process_name="chrome.exe"),
        ]
        manifest = SessionManifest(
            session_id=sid,
            started_at="2026-08-10T12:00:00",
            screen_width=1920,
            screen_height=1080,
            status="finalized",
        )
        write_aloha_input(sdir, manifest, events)
        self.assertTrue((sdir / "inputs" / "recording.log").is_file())

        self.mgr._session_id = sid
        self.mgr._recorder = mock.MagicMock()
        self.mgr._recorder.finalize.return_value = manifest
        self.mgr._recorder.events_snapshot.return_value = events
        self.mgr._recorder.directory = sdir

        result = self.mgr.finalize_and_process_payload()
        self.assertIn("trace_id", result)
        self.assertTrue(Path(result["trace_path"]).is_file())
        wfs = self.mgr.list_learned_workflows()
        self.assertEqual(len(wfs), 1)
        self.assertTrue(wfs[0].name)

        db2 = Database(Path(self.tmp.name) / "t.db")
        try:
            mgr2 = LearningManager(
                db2,
                learner=MockLearner(),
                executor=MockExecutor(LearnedWorkflowRepository(db2)),
            )
            self.assertEqual(len(mgr2.list_learned_workflows()), 1)
            run = mgr2.execute_workflow(wfs[0].trace_id, "다시 실행")
            self.assertEqual(run.status, "succeeded")
            st = mgr2.get_workflow_run_status(run.run_id)
            self.assertIsNotNone(st)
        finally:
            db2._conn.close()

    def test_state_machine_idle_recording_processing(self) -> None:
        states: list[LearningState] = []
        self.mgr._on_state = states.append
        with mock.patch("iris.learning.manager.DemonstrationRecorder") as Rec:
            rec = Rec.return_value
            rec.start.return_value = None
            rec.directory = Path(self.tmp.name)
            self.mgr.start_recording()
            self.assertEqual(self.mgr.state, LearningState.RECORDING)
            self.mgr.mark_processing()
            self.assertEqual(self.mgr.state, LearningState.PROCESSING)
            self.mgr.mark_success({"name": "테스트 업무"})
            self.assertEqual(self.mgr.state, LearningState.IDLE)
        self.assertIn(LearningState.RECORDING, states)
        self.assertIn(LearningState.PROCESSING, states)
        self.assertIn(LearningState.IDLE, states)

    def test_error_recovers(self) -> None:
        self.mgr.mark_error("boom")
        self.assertEqual(self.mgr.state, LearningState.ERROR)
        self.mgr.recover_to_idle()
        self.assertEqual(self.mgr.state, LearningState.IDLE)


class TestMainWindowLearningHook(unittest.TestCase):
    def test_main_window_learning_wiring_present(self) -> None:
        """전체 MainWindow 기동은 QtWebEngine 환경에 민감 — 소스/심볼만 회귀 확인."""
        import inspect
        from iris.ui import window as window_pkg

        src_path = Path(window_pkg.__file__).parent / "main_window.py"
        text = src_path.read_text(encoding="utf-8")
        self.assertIn("learning_clicked.connect(self._on_learning_toggle)", text)
        self.assertIn("LearningManager", text)
        self.assertIn("LearningProcessWorker", text)
        self.assertIn("interrupt_on_shutdown", text)
        # mic 회귀: mic 연결 유지
        self.assertIn("mic_clicked.connect(self._on_chat_mic_clicked)", text)

if __name__ == "__main__":
    unittest.main()
