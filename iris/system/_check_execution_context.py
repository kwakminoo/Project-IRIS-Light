"""HF-03 — Turn-frozen Trusted ExecutionContext.

Fails when:
- mid-turn conversation / workspace switch rebinds ACL ownership for handlers
- frozen ctx loses turn_id
- legacy unscoped (no active turn) still forges cross-session via model args
- strip_trust_fields stops stripping Speak trust keys

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_execution_context
"""

from __future__ import annotations

from types import SimpleNamespace

from iris.runtime.chat_turn_gate import ChatTurnGate
from iris.system.execution_context import (
    TRUST_FIELD_KEYS,
    ExecutionContext,
    active_turn_id,
    clear_turn_execution_context,
    frozen_turn_execution_context,
    make_execution_context,
    store_turn_execution_context,
    strip_trust_fields,
)
from iris.system.execution_runtime import ExecutionRuntime
from iris.ui.control_bindings import (
    capture_execution_context,
    freeze_turn_execution_context,
    trusted_execution_context,
)


class _FakeWindow:
    """Minimal Control window: live conversation + bound workspace."""

    def __init__(self, cid: int, workspace: str) -> None:
        self._conversation_id = cid
        self._workspace = workspace
        self._turn_gate = ChatTurnGate()
        self._turn_execution_meta: dict[str, ExecutionContext] = {}

    def _get_bound_ide_session(self, refresh: bool = False) -> SimpleNamespace:
        return SimpleNamespace(mode="workspace", workspace_root=self._workspace)


def _check_mid_turn_switch_keeps_frozen_acl_fields() -> None:
    win = _FakeWindow(101, r"C:\ws\alpha")
    win._turn_gate.begin("turn-a")
    frozen = freeze_turn_execution_context(win, "turn-a")
    assert frozen.turn_id == "turn-a", frozen
    assert frozen.effective_session_id() == "101", frozen
    assert frozen.workspace_root.endswith("alpha") or frozen.workspace_id.endswith(
        "alpha"
    ), frozen

    # Mid-turn UI switch — live window now points elsewhere.
    win._conversation_id = 202
    win._workspace = r"C:\ws\beta"

    preferred = trusted_execution_context(win)
    assert preferred.effective_session_id() == "101", preferred
    assert preferred.turn_id == "turn-a", preferred
    assert "alpha" in (preferred.workspace_root or preferred.workspace_id), preferred
    assert preferred is frozen or preferred.session_id == frozen.session_id

    # Live capture alone would see the new bind — prove the fault surface still exists.
    live = capture_execution_context(win, turn_id="")
    assert live.effective_session_id() == "202", live
    assert "beta" in (live.workspace_root or live.workspace_id), live


def _check_handlers_prefer_frozen_over_live() -> None:
    win = _FakeWindow(7, r"C:\ws\one")
    win._turn_gate.begin("t1")
    store_turn_execution_context(
        win,
        "t1",
        make_execution_context(
            session_id="7",
            conversation_id="7",
            turn_id="t1",
            workspace_id=r"C:\ws\one",
            workspace_root=r"C:\ws\one",
        ),
    )
    win._conversation_id = 99
    win._workspace = r"C:\ws\other"
    assert active_turn_id(win) == "t1"
    ctx = frozen_turn_execution_context(win)
    assert ctx is not None
    assert ctx.effective_session_id() == "7"
    assert trusted_execution_context(win).effective_session_id() == "7"


def _check_clear_on_finish_falls_back_to_live() -> None:
    win = _FakeWindow(3, r"C:\ws\x")
    win._turn_gate.begin("done-turn")
    freeze_turn_execution_context(win, "done-turn")
    finished = win._turn_gate.finish("done-turn")
    clear_turn_execution_context(win, finished)
    win._conversation_id = 4
    win._workspace = r"C:\ws\y"
    # No active turn → legacy live bind.
    assert frozen_turn_execution_context(win) is None
    live = trusted_execution_context(win)
    assert live.effective_session_id() == "4", live


def _check_strip_trust_fields_unchanged() -> None:
    forged = {k: f"evil-{k}" for k in sorted(TRUST_FIELD_KEYS)}
    forged["argv"] = ["echo", "ok"]
    cleaned = strip_trust_fields(forged)
    assert cleaned.get("argv") == ["echo", "ok"]
    for key in TRUST_FIELD_KEYS:
        assert key not in cleaned, key


def _check_legacy_unscoped_denies_cross_session() -> None:
    """No turn freeze / empty ctx session → cross-session still denied unless admin."""
    import tempfile
    from pathlib import Path
    import sys

    with tempfile.TemporaryDirectory() as td:
        from iris.system.process_start_plan import (
            FinalizedStartPlan,
            finalize_process_start_plan,
        )
        from iris.system.request_approval import default_approval_ledger

        rt = ExecutionRuntime(runs_root=Path(td) / "runs")
        start_args = {
            "action": "start",
            "argv": [sys.executable, "-c", "import time; time.sleep(30)"],
            "cwd": str(Path.home()),
        }
        plan = finalize_process_start_plan(start_args)
        assert isinstance(plan, FinalizedStartPlan), plan
        rec = default_approval_ledger().grant(
            fingerprint=plan.fingerprint(),
            session_id="session_a",
        )
        owner = make_execution_context(
            session_id="session_a",
            approval_reference=rec.request_id,
        )
        started = rt.manage(start_args, ctx=owner)
        assert started.get("ok") is True, started
        run_id = (started.get("data") or {}).get("run_id")
        # Legacy unscoped invoke: no trusted session on ctx.
        denied = rt.manage(
            {
                "action": "status",
                "run_id": run_id,
                "session_id": "session_a",  # forged Speak field
            },
            ctx=None,
        )
        assert denied.get("ok") is False, denied
        empty = make_execution_context()  # unscoped non-admin
        denied2 = rt.manage(
            {"action": "status", "run_id": run_id, "session_id": "session_a"},
            ctx=empty,
        )
        assert denied2.get("ok") is False, denied2
        cancelled = rt.manage({"action": "cancel", "run_id": run_id}, ctx=owner)
        assert cancelled.get("ok") is True, cancelled


def _check_consume_binds_final_plan() -> None:
    """FPR-03: manage(start) consume requires fingerprint + optional tool_call_id."""
    import sys
    import tempfile
    from pathlib import Path

    from iris.system.process_start_plan import (
        FinalizedStartPlan,
        finalize_process_start_plan,
    )
    from iris.system.request_approval import (
        default_approval_ledger,
        reset_approval_ledger_for_tests,
    )

    reset_approval_ledger_for_tests()
    with tempfile.TemporaryDirectory() as td:
        rt = ExecutionRuntime(runs_root=Path(td) / "runs")
        start_args = {
            "action": "start",
            "argv": [sys.executable, "-c", "import time; time.sleep(30)"],
            "cwd": str(Path.home()),
        }
        plan = finalize_process_start_plan(start_args)
        assert isinstance(plan, FinalizedStartPlan), plan
        fp = plan.fingerprint()
        rec = default_approval_ledger().grant(
            fingerprint=fp,
            session_id="sess-fpr03",
            tool_call_id="call-fpr03",
        )
        # Wrong tool_call_id → deny
        denied_tc = rt.manage(
            start_args,
            ctx=make_execution_context(
                session_id="sess-fpr03",
                approval_reference=rec.request_id,
                tool_call_id="call-other",
            ),
        )
        assert denied_tc.get("ok") is False, denied_tc
        assert "tool_call" in str(denied_tc.get("error") or ""), denied_tc

        # Mutated argv after grant → fingerprint mismatch
        mutated = dict(start_args)
        mutated["argv"] = [sys.executable, "-c", "print('mutated')"]
        denied_fp = rt.manage(
            mutated,
            ctx=make_execution_context(
                session_id="sess-fpr03",
                approval_reference=rec.request_id,
                tool_call_id="call-fpr03",
            ),
        )
        assert denied_fp.get("ok") is False, denied_fp
        assert "fingerprint" in str(denied_fp.get("error") or ""), denied_fp

        # Matching final plan → start ok, then cancel
        started = rt.manage(
            start_args,
            ctx=make_execution_context(
                session_id="sess-fpr03",
                approval_reference=rec.request_id,
                tool_call_id="call-fpr03",
            ),
        )
        assert started.get("ok") is True, started
        run_id = (started.get("data") or {}).get("run_id")
        owner = make_execution_context(session_id="sess-fpr03")
        cancelled = rt.manage({"action": "cancel", "run_id": run_id}, ctx=owner)
        assert cancelled.get("ok") is True, cancelled
    reset_approval_ledger_for_tests()


def _check_host_tool_call_meta_reaches_execution_context() -> None:
    """Host-verified tool_call_id/request_id reach ctx; model args cannot override."""
    import json
    import tempfile
    from pathlib import Path

    from iris.engine.runtime import Engine
    from iris.engine.types import EngineHome, InternalSidecar

    win = _FakeWindow(101, r"C:\ws\alpha")
    win._turn_gate.begin("turn-meta")
    freeze_turn_execution_context(win, "turn-meta")
    frozen = frozen_turn_execution_context(win)
    assert frozen is not None
    assert not frozen.tool_call_id
    assert not frozen.request_id

    seen: dict[str, object] = {}

    def handler(action: str, args: dict) -> dict:
        ctx = trusted_execution_context(win)
        seen["action"] = action
        seen["tool_call_id"] = ctx.tool_call_id
        seen["request_id"] = ctx.request_id
        seen["args"] = dict(args)
        return {"ok": True, "action": action}

    with tempfile.TemporaryDirectory() as td:
        engine = Engine(InternalSidecar(EngineHome(Path(td))))
        engine.bind_tool_handler(handler)
        writes: list[str] = []
        sink = SimpleNamespace(
            stdin=SimpleNamespace(
                write=lambda text: writes.append(text), flush=lambda: None
            )
        )
        engine._reply_to_tool_request(
            sink,
            {
                "id": "req-host-1",
                "name": "process.manage",
                "tool_call_id": "call-host-1",
                "args": {
                    "action": "list",
                    "tool_call_id": "forged-call",
                    "request_id": "forged-req",
                    "session_id": "forged-session",
                },
            },
        )
        reply = json.loads("".join(writes))
        assert reply.get("result", {}).get("ok") is True, reply

    assert seen.get("action") == "process.manage", seen
    assert seen.get("tool_call_id") == "call-host-1", seen
    assert seen.get("request_id") == "req-host-1", seen
    args = seen.get("args")
    assert isinstance(args, dict)
    # Separate channel: forged trust keys may still sit in raw args here;
    # ExecutionContext must not take them (Host meta wins).
    assert seen.get("tool_call_id") != args.get("tool_call_id")
    assert seen.get("request_id") != args.get("request_id")
    # After invoke, per-call overlay must not leak into the frozen bag.
    after = trusted_execution_context(win)
    assert after.tool_call_id == "", after
    assert after.request_id == "", after


def _check_stateless_turn_carries_captured_session_workspace() -> None:
    """GUI Worker / turn construction fills StatelessTurn from turn-start capture."""
    import inspect
    from pathlib import Path

    from iris.engine.types import CancelToken, StatelessTurn
    from iris.ui.workers import iris_agent_workers as workers_mod
    from iris.ui.workers.iris_agent_workers import IrisAgentChatWorker

    src = inspect.getsource(IrisAgentChatWorker._run_internal)
    assert "session_id=" in src and "workspace_id=" in src, src
    assert "self._session_id" in src and "self._workspace_id" in src, src

    # Constructor accepts turn-start capture (not empty → random turn_id fallback alone).
    params = inspect.signature(IrisAgentChatWorker.__init__).parameters
    assert "session_id" in params, params
    assert "workspace_id" in params, params

    worker = IrisAgentChatWorker(
        "probe-model",
        [{"role": "user", "content": "hi"}],
        session_id="101",
        workspace_id=r"C:\ws\alpha",
    )
    assert worker._session_id == "101"
    assert worker._workspace_id == r"C:\ws\alpha"

    # Same shape the worker must put on the engine turn.
    turn = StatelessTurn(
        transcript=workers_mod.ChatTranscript.parse(
            [{"role": "user", "content": "hi"}]
        ),
        model=worker._resolve_target(worker._attempts[0]),
        cancel=CancelToken(),
        speak_surface="home",
        session_id=worker._session_id,
        workspace_id=worker._workspace_id,
    )
    assert turn.session_id == "101"
    assert turn.workspace_id == r"C:\ws\alpha"

    # MainWindow construction site must pass captured identity into the worker.
    mw_src = Path(__file__).resolve().parents[1] / "ui" / "window" / "main_window.py"
    text = mw_src.read_text(encoding="utf-8")
    assert "IrisAgentChatWorker(" in text
    # session_id= / workspace_id= kwargs near the worker construction.
    idx = text.index("IrisAgentChatWorker(")
    chunk = text[idx : idx + 500]
    assert "session_id=" in chunk, chunk
    assert "workspace_id=" in chunk, chunk


def main() -> None:
    _check_mid_turn_switch_keeps_frozen_acl_fields()
    _check_handlers_prefer_frozen_over_live()
    _check_clear_on_finish_falls_back_to_live()
    _check_strip_trust_fields_unchanged()
    _check_legacy_unscoped_denies_cross_session()
    _check_consume_binds_final_plan()
    _check_host_tool_call_meta_reaches_execution_context()
    _check_stateless_turn_carries_captured_session_workspace()
    print("execution_context ok")


if __name__ == "__main__":
    main()
