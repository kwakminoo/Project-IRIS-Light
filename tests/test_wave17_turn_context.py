import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import StringIO
from queue import Queue
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

from iris.engine import Engine, EngineHome, EngineReady, InternalSidecar, TurnCancelled, TurnFailed
from iris.system.execution_context import ExecutionContext, bind_host_tool_call_meta
from tests.test_iris_engine_turn_pipe import _turn


def test_qt_dispatch_preserves_host_identity():
    from PyQt6.QtCore import QCoreApplication, QTimer

    from iris.ui.control_bindings import _QtInvoker, trusted_execution_context

    app = QCoreApplication.instance() or QCoreApplication([])
    invoker = _QtInvoker()
    window = SimpleNamespace(_conversation_id=99)
    original = ExecutionContext(session_id="17", turn_id="desktop-turn", principal="desktop")

    def dispatch():
        with bind_host_tool_call_meta(
            tool_call_id="call", request_id="request", execution_context=original,
            run_id="attempt", schema_fingerprint="schema",
        ):
            return invoker.run(lambda: trusted_execution_context(window), timeout=2)

    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(dispatch)
        tick = QTimer()
        tick.timeout.connect(lambda: app.quit() if future.done() else None)
        tick.start(5)
        app.exec()
        tick.stop()
        result = future.result(timeout=1)

    assert result.session_id == "17"
    assert result.turn_id == "desktop-turn"
    assert result.tool_call_id == "call"
    assert result.request_id == "request"
    assert result.run_id == "attempt"
    assert result.schema_fingerprint == "schema"
    assert trusted_execution_context(window).session_id == "99"


def test_engine_dispatch_uses_frozen_context_and_strips_model_identity(tmp_path):
    from iris.infrastructure.speak_capability import engine_tool_bindings
    from iris.ui.control_bindings import trusted_execution_context

    engine = Engine(InternalSidecar(home=EngineHome(tmp_path)))
    turn = replace(_turn(), execution_context=ExecutionContext(
        session_id="17", conversation_id="17", turn_id="desktop-turn",
        workspace_id="workspace", source="desktop", principal="desktop",
    ))
    binding = next(iter(engine_tool_bindings("home")))
    child = SimpleNamespace(poll=lambda: None, pid=42, stdin=StringIO())
    engine._child = child
    calls = []

    def dispatch(action, args):
        calls.append((action, args, trusted_execution_context(SimpleNamespace(_conversation_id=99))))
        return {"ok": True}

    def read_events(_child, _cancel, **ids):
        engine._reply_to_tool_request(
            child, {
                "id": "call-request", "tool_call_id": "call", "turn_id": ids["turn_id"],
                "session_id": "17", "workspace_id": "workspace", "name": binding.canonical_action,
                "canonical_action": binding.canonical_action, "model_tool_name": binding.model_name,
                "schema_fingerprint": binding.fingerprint,
                "args": {"principal": "admin", "run_id": "target-process", "source": "input", "schema_fingerprint": "fake"},
            }, **{
                "surface": ids["surface"], "expected_turn_id": ids["turn_id"],
                "expected_session_id": ids["session_id"], "expected_workspace_id": ids["workspace_id"],
                "execution_context": ids["execution_context"],
            },
        )
        return iter(())

    engine.bind_tool_handler(dispatch)
    with (
        patch.object(engine, "ensure_ready", return_value=EngineReady(engine.source, "ready")),
        patch.object(engine, "_read_turn_events", side_effect=read_events),
        patch("iris.engine.runtime._bind_terminal_udp", return_value=(Mock(), 12345)),
    ):
        assert list(engine.run_turn(turn)) == []

    [(action, args, ctx)] = calls
    assert action == binding.canonical_action
    assert args == {"run_id": "target-process", "source": "input"}
    assert ctx.turn_id == "desktop-turn"
    assert ctx.session_id == "17"
    assert ctx.principal == "desktop"
    assert ctx.source == "desktop"
    assert ctx.run_id and ctx.run_id != ctx.turn_id
    assert ctx.schema_fingerprint == binding.fingerprint


def test_cancellation_during_pipe_wait_prevents_tool_dispatch(tmp_path):
    engine = Engine(InternalSidecar(home=EngineHome(tmp_path)))
    token = _turn().cancel

    def receive(**_kwargs):
        token.cancel()
        return '{"t":"tool_request","id":"late","name":"ping"}'

    with (
        patch.object(engine, "_stdout_lines", return_value=SimpleNamespace(get=receive)),
        patch.object(engine, "_reply_to_tool_request") as dispatch,
        patch.object(engine, "_stop_and_forget") as stop,
    ):
        events = list(engine._read_turn_events(Mock(), token))

    assert events == [TurnCancelled()]
    dispatch.assert_not_called()
    stop.assert_called_once()


def test_rejected_concurrent_turn_does_not_hold_engine_lock(tmp_path):
    engine = Engine(InternalSidecar(home=EngineHome(tmp_path)))
    engine._turn_active = True

    with patch.object(engine, "ensure_ready", return_value=EngineReady(engine.source, "ready")):
        events = engine.run_turn(_turn())
        try:
            assert isinstance(next(events), TurnFailed)
            assert engine._lock.acquire(blocking=False)
            engine._lock.release()
        finally:
            events.close()


def test_tool_bindings_are_snapshotted_for_the_turn(tmp_path):
    from iris.infrastructure.speak_capability import engine_tool_bindings

    binding = next(row for row in engine_tool_bindings("home") if row.model_name == "ping")
    engine = Engine(InternalSidecar(home=EngineHome(tmp_path)))
    child = SimpleNamespace(stdin=StringIO())
    dispatcher = Mock(return_value={"ok": True})
    engine.bind_tool_handler(dispatcher)
    pending = Queue()
    call = {"t": "tool_request", "id": "first", "name": "ping", "model_tool_name": "ping",
            "canonical_action": "ping", "schema_fingerprint": binding.fingerprint,
            "session_id": "session", "workspace_id": "", "tool_call_id": "call"}
    pending.put(json.dumps({**call, "turn_id": "stale"}))
    pending.put(json.dumps({**call, "turn_id": "active"}))
    pending.put(json.dumps({**call, "id": "second", "tool_call_id": "call2", "turn_id": "active"}))
    pending.put(json.dumps({"t": "done", "text": "done", "turn_id": "active"}))
    with (
        patch.object(engine, "_stdout_lines", return_value=pending),
        patch("iris.infrastructure.speak_capability.engine_tool_bindings", side_effect=[(binding,), ()]) as roster,
    ):
        list(engine._read_turn_events(child, _turn().cancel, surface="home", turn_id="active", session_id="session"))
    assert roster.call_count == 1
    assert dispatcher.call_count == 2


def test_cancelled_turn_cannot_execute_after_approval():
    from iris.system.control_surface import ActionRegistry

    cancelled = Event()
    registry = ActionRegistry()
    handler = Mock(return_value={})
    registry.register("mutation", handler, summary="Test mutation", confirm_required=True)

    def approve(*_args):
        cancelled.set()
        return True

    registry.set_human_confirm(approve)
    with bind_host_tool_call_meta(cancelled=cancelled.is_set):
        result = registry.invoke("mutation", {})
    assert result["status"] == "cancelled"
    handler.assert_not_called()
