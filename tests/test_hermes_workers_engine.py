"""Default chat path uses shared_engine, not :8642."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.engine import (  # noqa: E402
    ContentDelta,
    EngineError,
    EngineErrorCode,
    EngineFailed,
    EngineHome,
    EngineReady,
    ExternalGateway,
    InternalSidecar,
    ToolProgress,
    TurnCancelled,
    TurnFinished,
)
from iris.infrastructure.hermes_client import HermesInferenceTarget  # noqa: E402
from iris.ui.workers.hermes_workers import (  # noqa: E402
    HermesChatWorker,
    HermesHealthWorker,
    HermesModelSyncWorker,
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
                "iris.ui.workers.hermes_workers.sync_iris_control",
                return_value=SimpleNamespace(summary_line=lambda: "skip"),
            ),
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

    def test_engine_ready_syncs_engine_home_without_reconnecting_gateway(self) -> None:
        engine = _StubEngine()
        worker = HermesHealthWorker()
        out = _Collector(worker)
        report = SimpleNamespace(summary_line=lambda: "engine sync")
        with (
            patch("iris.ui.workers.hermes_workers.shared_engine", return_value=engine),
            patch(
                "iris.ui.workers.hermes_workers.sync_iris_control",
                return_value=report,
            ) as sync,
            patch(
                "iris.ui.workers.hermes_workers.ensure_hermes_gateway_running"
            ) as start_gateway,
            patch("iris.ui.workers.hermes_workers.restart_hermes_gateway") as restart,
        ):
            worker.run()
        self.assertEqual(out.ok, [True])
        self.assertEqual(out.failed, [])
        sync.assert_called_once()
        kwargs = sync.call_args.kwargs
        self.assertEqual(kwargs.get("home"), engine.source.home)
        self.assertIs(kwargs.get("reconnect_gateway"), False)
        start_gateway.assert_not_called()
        restart.assert_not_called()

    def test_engine_failed_emits_user_message(self) -> None:
        error = EngineError(EngineErrorCode.NOT_INSTALLED, "missing")
        engine = _StubEngine(ready=EngineFailed(error))
        worker = HermesHealthWorker()
        out = _Collector(worker)
        with (
            patch("iris.ui.workers.hermes_workers.shared_engine", return_value=engine),
            patch("iris.ui.workers.hermes_workers.sync_iris_control") as sync,
        ):
            worker.run()
        self.assertEqual(out.ok, [])
        self.assertEqual(out.failed, [error.user_message])
        sync.assert_not_called()


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


class InternalModelSyncTests(TestCase):
    def test_internal_source_does_not_construct_client_or_start_gateway(self) -> None:
        engine = _StubEngine()
        worker = HermesModelSyncWorker("http://127.0.0.1:8642/v1", "llama")
        ok: list[object] = []
        failed: list[str] = []
        worker.finished_ok.connect(lambda: ok.append(True))
        worker.failed.connect(failed.append)
        with (
            patch("iris.ui.workers.hermes_workers.shared_engine", return_value=engine),
            patch("iris.ui.workers.hermes_workers.HermesClient") as client_cls,
            patch(
                "iris.ui.workers.hermes_workers.ensure_hermes_gateway_running"
            ) as start_gateway,
        ):
            worker.run()
        self.assertEqual(ok, [True])
        self.assertEqual(failed, [])
        client_cls.assert_not_called()
        start_gateway.assert_not_called()

    def test_external_source_still_constructs_hermes_client(self) -> None:
        engine = _StubEngine()
        engine.source = ExternalGateway(
            base_url="http://127.0.0.1:8642/v1",
            api_key="",
        )
        client = MagicMock()
        worker = HermesModelSyncWorker("http://127.0.0.1:8642/v1", "llama")
        ok: list[object] = []
        failed: list[str] = []
        worker.finished_ok.connect(lambda: ok.append(True))
        worker.failed.connect(failed.append)
        with (
            patch("iris.ui.workers.hermes_workers.shared_engine", return_value=engine),
            patch(
                "iris.ui.workers.hermes_workers.HermesClient",
                return_value=client,
            ) as client_cls,
            patch(
                "iris.ui.workers.hermes_workers.ensure_hermes_gateway_running"
            ) as start_gateway,
        ):
            worker.run()
        self.assertEqual(ok, [True])
        self.assertEqual(failed, [])
        client_cls.assert_called_once()
        client.set_inference_model.assert_called_once_with("llama")
        start_gateway.assert_not_called()

    def test_sync_hermes_model_skips_worker_for_internal(self) -> None:
        from iris.ui.window.main_window import MainWindow

        host = SimpleNamespace(
            _settings=SimpleNamespace(hermes_enabled=True),
            _hermes_model_worker=None,
        )
        engine = _StubEngine()
        with (
            patch("iris.engine.shared_engine", return_value=engine),
            patch("iris.ui.window.main_window.HermesModelSyncWorker") as worker_cls,
        ):
            MainWindow._sync_hermes_model(host, "llama")
        worker_cls.assert_not_called()
