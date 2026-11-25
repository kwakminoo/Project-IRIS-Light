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
        rt = ExecutionRuntime(runs_root=Path(td) / "runs")
        rt.set_human_confirm(lambda _s, _a: True)
        owner = make_execution_context(session_id="session_a")
        started = rt.manage(
            {
                "action": "start",
                "argv": [sys.executable, "-c", "import time; time.sleep(30)"],
                "cwd": str(Path.home()),
            },
            ctx=owner,
        )
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


def main() -> None:
    _check_mid_turn_switch_keeps_frozen_acl_fields()
    _check_handlers_prefer_frozen_over_live()
    _check_clear_on_finish_falls_back_to_live()
    _check_strip_trust_fields_unchanged()
    _check_legacy_unscoped_denies_cross_session()
    print("execution_context ok")


if __name__ == "__main__":
    main()
