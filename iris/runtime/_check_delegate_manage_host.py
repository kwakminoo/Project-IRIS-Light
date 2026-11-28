"""FFC-03 Unit 4d — delegate.manage host wire (grant reject + Engine.fork factory).

Fails when:
- spawn accepts grant escalation beyond current Speak grants
- production factory never calls Engine.fork / shared_engine().fork
- model schema name is not Hermes ``delegate_task``
- Hermes registry remains the dispatch path (absorb must map to Control)

Run:
  .venv\\Scripts\\python.exe -m iris.runtime._check_delegate_manage_host
"""

from __future__ import annotations

from iris.infrastructure.speak_capability import (
    PHASE4_ALLOWLIST,
    engine_tool_name,
    engine_tool_schemas,
)
from iris.runtime.delegate_host import (
    production_engine_factory,
    reset_delegate_registry,
)
from iris.system.control_surface import ActionRegistry
from iris.system.execution_context import bind_host_tool_call_meta, make_execution_context
from iris.ui.control_actions.delegate import register_delegate_actions


class _FakeHandle:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


def _factory(**_kwargs):
    return _FakeHandle()


def _invoke(reg: ActionRegistry, args: dict) -> dict:
    return reg.invoke("delegate.manage", args)


def _check_spawn_grant_reject() -> None:
    sid = "delegate-manage-wire-1"
    reset_delegate_registry(engine_factory=_factory)
    ctx = make_execution_context(
        session_id=sid,
        conversation_id=sid,
        turn_id="turn-delegate-1",
        source="desktop",
        principal="iris.desktop",
    )
    reg = ActionRegistry()
    register_delegate_actions(reg)

    with bind_host_tool_call_meta(execution_context=ctx):
        bad = _invoke(
            reg,
            {
                "operation": "spawn",
                "task": "steal",
                "grants": ["__not_a_real_speak_grant__"],
                "max_children": 2,
                "max_depth": 2,
                "depth": 0,
            },
        )
        assert bad.get("ok") is False, bad
        err = str(bad.get("error") or "").lower()
        assert "grant" in err or "escalation" in err, bad

        ok = _invoke(
            reg,
            {
                "operation": "spawn",
                "task": "ping child",
                "grants": ["ping"],
                "max_children": 2,
                "max_depth": 2,
                "depth": 0,
            },
        )
        assert ok.get("ok") is True, ok
        child = ok.get("result") or {}
        assert child.get("status") == "running", child
        assert child.get("grants") == ["ping"], child
        child_id = str(child.get("child_id") or "")
        assert child_id, child

        cancelled = _invoke(reg, {"operation": "cancel", "child_id": child_id})
        assert cancelled.get("ok") is True, cancelled
        assert cancelled.get("result", {}).get("status") == "cancelled"
        assert cancelled.get("result", {}).get("orphan_guard") is True

        listed = _invoke(reg, {"operation": "aggregate"})
        assert listed.get("ok") is True, listed
        rows = listed.get("result", {}).get("children") or []
        by_id = {row["child_id"]: row for row in rows}
        assert by_id[child_id]["status"] == "cancelled", by_id


def _check_production_factory_calls_fork() -> None:
    fork_calls: list[str] = []

    class _SpyEngine:
        def fork(self) -> "_SpyEngine":
            fork_calls.append("fork")
            return _SpyEngine()

        def shutdown(self) -> None:
            fork_calls.append("shutdown")

    import iris.engine.runtime as runtime_mod

    original = runtime_mod.shared_engine
    runtime_mod.shared_engine = lambda: _SpyEngine()  # type: ignore[assignment]
    try:
        handle = production_engine_factory(
            parent_session_id="p",
            child_id="c",
            task="t",
            grants=frozenset(),
            budget=None,
            depth=0,
        )
        assert fork_calls == ["fork"], fork_calls
        handle.cancel()
        assert "shutdown" in fork_calls, fork_calls
    finally:
        runtime_mod.shared_engine = original


def _check_schema_absorb() -> None:
    grant = PHASE4_ALLOWLIST.grant("delegate.manage")
    assert grant is not None
    assert engine_tool_name("delegate.manage") == "delegate_task"
    home = {str(row["name"]) for row in engine_tool_schemas("home")}
    assert "delegate_task" in home
    assert "delegate_manage" not in home


def main() -> None:
    _check_spawn_grant_reject()
    _check_production_factory_calls_fork()
    _check_schema_absorb()
    home_n = len(engine_tool_schemas("home"))
    print(f"delegate_manage_host: ok schema=delegate_task home_n={home_n}")


if __name__ == "__main__":
    main()
