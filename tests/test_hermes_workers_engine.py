"""Default chat path uses shared_engine, not :8642."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.engine import (  # noqa: E402
    ContentDelta,
    EngineError,
    EngineErrorCode,
    EngineFailed,
    EngineHome,
    EngineReady,
    InternalSidecar,
    ToolProgress,
    TurnCancelled,
    TurnFinished,
)
from iris.infrastructure.hermes_client import HermesInferenceTarget  # noqa: E402
from iris.ui.workers.hermes_workers import (  # noqa: E402
    HermesChatWorker,
    HermesHealthWorker,
)


def _internal() -> InternalSidecar:
    return InternalSidecar(home=EngineHome(Path.home() / ".iris-light" / "engine"))


class _StubEngine:
    def __init__(self, *, ready=None, events=None) -> None:
        self.source = _internal()
        self.ready = ready or EngineReady(self.source, "engine is ready")
        self.events = list(events or [])
        self.turns: list[object] = []
        self.ensure_calls = 0

    def ensure_ready(self):
        self.ensure_calls += 1
        return self.ready

    def run_turn(self, turn):
        self.turns.append(turn)
        yield from self.events


class _Collector:
    def __init__(self, worker) -> None:
        self.ok: list[object] = []
        self.failed: list[str] = []
        self.notice: list[str] = []
        self.content: list[str] = []
        self.tools: list[str] = []
        worker.finished_ok.connect(self.ok.append)
        worker.failed.connect(self.failed.append)
        if hasattr(worker, "notice"):
            worker.notice.connect(self.notice.append)
        if hasattr(worker, "content_chunk"):
            worker.content_chunk.connect(self.content.append)
        if hasattr(worker, "tool_progress"):
            worker.tool_progress.connect(self.tools.append)


class InternalHealthWorkerTests(TestCase):
    def test_constructs_without_gateway_url(self) -> None:
        worker = HermesHealthWorker()
        self.assertIsNotNone(worker)

    def test_engine_ready_finishes_ok_without_starting_8642(self) -> None:
        engine = _StubEngine()
        worker = HermesHealthWorker()
        out = _Collector(worker)
        with (
            patch("iris.ui.workers.hermes_workers.shared_engine", return_value=engine),
            patch(
                "iris.ui.workers.hermes_workers.ensure_hermes_gateway_running"
            ) as start_gateway,
            patch("iris.ui.workers.hermes_workers.restart_hermes_gateway") as restart,
        ):
            worker.run()
        self.assertEqual(out.ok, [True])
        self.assertEqual(out.failed, [])
        self.assertEqual(engine.ensure_calls, 1)
        start_gateway.assert_not_called()
        restart.assert_not_called()

    def test_engine_failed_emits_user_message(self) -> None:
        error = EngineError(EngineErrorCode.NOT_INSTALLED, "missing")
        engine = _StubEngine(ready=EngineFailed(error))
        worker = HermesHealthWorker()
        out = _Collector(worker)
        with patch("iris.ui.workers.hermes_workers.shared_engine", return_value=engine):
            worker.run()
        self.assertEqual(out.ok, [])
        self.assertEqual(out.failed, [error.user_message])


class InternalChatWorkerTests(TestCase):
    def test_constructs_without_gateway_url(self) -> None:
        worker = HermesChatWorker(
            "llama",
            [{"role": "user", "content": "hi"}],
            target=HermesInferenceTarget(model="llama", provider="custom"),
        )
        self.assertIsNotNone(worker)

    def test_maps_delta_and_finished(self) -> None:
        engine = _StubEngine(
            events=[
                ContentDelta("안"),
                ContentDelta("녕"),
                ToolProgress("도구 호출"),
                TurnFinished("안녕"),
            ]
        )
        worker = HermesChatWorker(
            "llama",
            [{"role": "user", "content": "hi"}],
            target=HermesInferenceTarget(model="llama", provider="custom"),
        )
        out = _Collector(worker)
        with (
            patch("iris.ui.workers.hermes_workers.shared_engine", return_value=engine),
            patch(
                "iris.ui.workers.hermes_workers.ensure_hermes_gateway_running"
            ) as start_gateway,
        ):
            worker.run()
        self.assertEqual(out.content, ["안", "녕"])
        self.assertEqual(out.tools, ["도구 호출"])
        self.assertEqual(out.ok, ["안녕"])
        self.assertEqual(out.failed, [])
        self.assertEqual(len(engine.turns), 1)
        start_gateway.assert_not_called()

    def test_cancel_before_send_does_not_start_a_turn(self) -> None:
        engine = _StubEngine(events=[TurnFinished("no")])
        worker = HermesChatWorker(
            "llama",
            [{"role": "user", "content": "hi"}],
            target=HermesInferenceTarget(model="llama", provider="custom"),
        )
        out = _Collector(worker)
        worker.request_cancel()
        with patch("iris.ui.workers.hermes_workers.shared_engine", return_value=engine):
            worker.run()
        self.assertEqual(engine.turns, [])
        self.assertEqual(out.ok, [])
        self.assertEqual(out.failed, [])

    def test_turn_cancelled_is_silent(self) -> None:
        engine = _StubEngine(events=[ContentDelta("x"), TurnCancelled()])
        worker = HermesChatWorker(
            "llama",
            [{"role": "user", "content": "hi"}],
            target=HermesInferenceTarget(model="llama", provider="custom"),
        )
        out = _Collector(worker)
        with patch("iris.ui.workers.hermes_workers.shared_engine", return_value=engine):
            worker.run()
        self.assertEqual(out.content, ["x"])
        self.assertEqual(out.ok, [])
        self.assertEqual(out.failed, [])


class CloseEventShutdownTests(TestCase):
    def test_close_event_source_calls_shared_engine_shutdown(self) -> None:
        from iris.ui.window import main_window as mw

        src = inspect.getsource(mw.MainWindow.closeEvent)
        self.assertIn("shared_engine().shutdown", src)
        self.assertIn("app.quit()", src)
