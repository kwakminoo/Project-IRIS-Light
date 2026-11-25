"""TDD: shell.run is SpeakTools-visible and maps to an Iris Shell chat card."""

from __future__ import annotations

from iris.infrastructure.speak_capability import (
    PHASE4_ALLOWLIST,
    default_speak_tools,
    set_speak_surface,
)
from iris.system.iris_shell import ShellJob, ShellOutcome, parse_shell_job, run_shell_job
from iris.ui.chat.run_visibility import card_from_control_result
from iris.ui.chat.shell_controller import clip_live as _clip_live
from iris.ui.chat.shell_controller import run_shell_live
from iris.ui.control_actions.shell import _ide_companion_active


def _check_live_stream_paints_running() -> None:
    """Fake stream chunks must paint phase=running before done (one card)."""

    class _Chat:
        def __init__(self) -> None:
            self.ops: list[tuple[str, dict]] = []

        def insert_tool_block(self, **kwargs) -> str:
            self.ops.append(("insert", dict(kwargs)))
            return "live-1"

        def replace_tool_block(self, block_id: str, **kwargs) -> bool:
            self.ops.append(("replace", {"block_id": block_id, **kwargs}))
            return True

    chat = _Chat()
    job = ShellJob(command="echo live", cwd=parse_shell_job({"command": "echo live"}).cwd)

    def fake_stream(_job: ShellJob, on_chunk, cancel_event=None) -> ShellOutcome:
        on_chunk("line-a\n")
        on_chunk("line-b\n")
        return ShellOutcome(
            ok=True,
            command=_job.command,
            cwd=str(_job.cwd),
            exit_code=0,
            stdout="line-a\nline-b\n",
            stderr="",
            summary="exit 0 · ok",
        )

    outcome, bid = run_shell_live(
        chat=chat,
        on_ui=lambda fn: fn(),
        job=job,
        block_id="",
        stream_fn=fake_stream,
    )
    assert outcome.ok
    assert bid == "live-1"
    phases = [op[1].get("phase") for op in chat.ops]
    assert "running" in phases, phases
    assert phases[-1] == "done", phases
    first_running = next(i for i, p in enumerate(phases) if p == "running")
    first_done = next(i for i, p in enumerate(phases) if p == "done")
    assert first_running < first_done
    # One card lifecycle: first op inserts (or replaces existing); no second insert after done.
    inserts = [op for op in chat.ops if op[0] == "insert"]
    assert len(inserts) == 1, inserts
    done_ops = [op for op in chat.ops if op[1].get("phase") == "done"]
    assert done_ops and "line-a" in (done_ops[-1][1].get("output") or "")

    # Pending confirm path: reuse same block_id (replace only, no second insert).
    pending = _Chat()
    outcome2, bid2 = run_shell_live(
        chat=pending,
        on_ui=lambda fn: fn(),
        job=job,
        block_id="pending-9",
        stream_fn=fake_stream,
    )
    assert outcome2.ok and bid2 == "pending-9"
    assert all(op[0] == "replace" for op in pending.ops), pending.ops
    assert pending.ops[0][1]["phase"] == "running"
    assert pending.ops[-1][1]["phase"] == "done"


def main() -> None:
    set_speak_surface("home")
    assert PHASE4_ALLOWLIST.grant("shell.run") is not None
    names = default_speak_tools().engine_names()
    assert "shell.run" in names, names

    job = parse_shell_job({"command": "echo shell-action-ok"})
    out = run_shell_job(job)
    assert out.ok, out.summary
    envelope = {
        "ok": True,
        "action": "shell.run",
        "result": {
            "command": out.command,
            "cwd": out.cwd,
            "exit_code": out.exit_code,
            "stdout": out.stdout,
            "stderr": out.stderr,
            "summary": out.summary,
            "via": out.via,
        },
    }
    card = card_from_control_result("shell.run", envelope)
    assert card is not None
    assert card.title == "Iris Shell"
    assert "shell-action-ok" in (card.output + card.command)

    class _Win:
        _ui_mode = "companion"
        _companion_page = None
        _body_stack = None

    assert _ide_companion_active(_Win()) is True

    class _Home:
        _ui_mode = "normal"
        _companion_page = None
        _body_stack = None

    assert _ide_companion_active(_Home()) is False

    set_speak_surface("ide_companion")
    hidden = default_speak_tools().invoke("shell.run", {"command": "echo nope"})
    assert hidden.ok is False
    assert "not_allowed" in (hidden.error or ""), hidden
    set_speak_surface("home")

    _check_live_stream_paints_running()
    # UI ring: long output keeps head + newest tail (full log stays on run record).
    long = "HEAD-" + ("x" * 20000) + "-TAIL"
    clipped = _clip_live(long, limit=2000)
    assert clipped.startswith("HEAD-")
    assert clipped.endswith("-TAIL")
    assert "truncated" in clipped
    assert len(clipped) <= 2000
    print("iris_shell_action ok")


if __name__ == "__main__":
    main()
