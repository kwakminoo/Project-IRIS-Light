"""U07 / HF-06 shell controller identity map + live paint + cancel."""

from __future__ import annotations

import threading
import time

from iris.system.iris_shell import ShellJob, ShellOutcome, parse_shell_job
from iris.ui.chat import shell_controller as sc


def _check_identity_and_phase() -> None:
    sc.reset_for_tests()
    req = sc.new_request(session_id="s1", command="echo hi")
    sc.bind_block(req.request_id, "b1")
    sc.bind_run(req.request_id, "r1")
    assert sc.get_by_block("b1").run_id == "r1"
    assert sc.get_by_run("r1").block_id == "b1"
    assert sc.ui_phase("running") == "running"
    assert sc.ui_phase("awaiting_approval") == "pending"
    assert sc.ui_phase("cancelled") == "done"
    sc.set_status(req.request_id, "completed")
    assert sc.get_by_request(req.request_id).status == "completed"


def _check_concurrent_isolation() -> None:
    sc.reset_for_tests()
    a = sc.new_request(session_id="sA", command="a", block_id="ba")
    b = sc.new_request(session_id="sB", command="b", block_id="bb")
    sc.bind_run(a.request_id, "ra")
    sc.bind_run(b.request_id, "rb")
    assert sc.get_by_block("ba").run_id == "ra"
    assert sc.get_by_block("bb").run_id == "rb"
    assert sc.get_by_run("ra").request_id == a.request_id
    assert sc.get_by_run("rb").request_id == b.request_id
    assert a.request_id != b.request_id


def _check_run_shell_live_one_box() -> None:
    sc.reset_for_tests()

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
    req = sc.new_request(command=job.command)
    bound_midstream: list[str] = []

    def fake_stream(_job: ShellJob, on_chunk, cancel_event=None, on_started=None) -> ShellOutcome:
        # HF-06: bind as soon as start succeeds (before stream ends).
        if callable(on_started):
            on_started("run-live")
        mapped = sc.get_by_request(req.request_id)
        assert mapped is not None and mapped.run_id == "run-live"
        bound_midstream.append(mapped.run_id)
        on_chunk("line-a\n")
        return ShellOutcome(
            ok=True,
            command=_job.command,
            cwd=str(_job.cwd),
            exit_code=0,
            stdout="line-a\n",
            stderr="",
            summary="exit 0 · ok",
            run_id="run-live",
            status="completed",
        )

    outcome, bid = sc.run_shell_live(
        chat=chat,
        on_ui=lambda fn: fn(),
        job=job,
        block_id="",
        stream_fn=fake_stream,
        request_id=req.request_id,
    )
    assert outcome.ok and bid == "live-1"
    assert bound_midstream == ["run-live"]
    mapped = sc.get_by_request(req.request_id)
    assert mapped is not None
    assert mapped.block_id == "live-1"
    assert mapped.run_id == "run-live"
    assert mapped.status == "completed"
    inserts = [op for op in chat.ops if op[0] == "insert"]
    assert len(inserts) == 1


def _check_cancel_awaiting_approval() -> None:
    sc.reset_for_tests()
    req = sc.new_request(command="noop")
    assert req.status == "awaiting_approval"
    assert sc.cancel_request(req.request_id) is True
    assert sc.get_by_request(req.request_id).status == "cancelled"
    # HF-06: do not force running over cancelled.
    sc.set_status(req.request_id, "running")
    assert sc.get_by_request(req.request_id).status == "cancelled"
    sc.bind_run(req.request_id, "late-run")
    assert sc.get_by_request(req.request_id).status == "cancelled"
    assert sc.get_by_run("late-run").request_id == req.request_id


def _check_cancel_event_during_stream() -> None:
    sc.reset_for_tests()
    req = sc.new_request(command="sleep")
    saw_cancel = threading.Event()

    def fake_stream(_job, on_chunk, cancel_event=None, on_started=None):
        if callable(on_started):
            on_started("run-cancel")
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                saw_cancel.set()
                return ShellOutcome(
                    ok=False,
                    command=_job.command,
                    cwd=str(_job.cwd),
                    exit_code=-1,
                    stdout="",
                    stderr="",
                    summary="cancelled",
                    run_id="run-cancel",
                    status="cancelled",
                )
            time.sleep(0.02)
        raise AssertionError("cancel_event never set")

    def _cancel_soon() -> None:
        time.sleep(0.05)
        sc.cancel_request(req.request_id)

    threading.Thread(target=_cancel_soon, daemon=True).start()
    outcome, _bid = sc.run_shell_live(
        chat=None,
        on_ui=lambda fn: fn(),
        job=ShellJob(command="sleep", cwd=parse_shell_job({"command": "echo"}).cwd),
        stream_fn=fake_stream,
        request_id=req.request_id,
    )
    assert saw_cancel.is_set()
    assert outcome.status == "cancelled"
    assert sc.get_by_request(req.request_id).status == "cancelled"


def _check_live_ring_bounded() -> None:
    ring = sc.LiveOutputRing(limit=200)
    ring.append("H" * 80)
    ring.append("T" * 5000)
    snap = ring.snapshot()
    assert len(snap) <= 200 + 40, f"ring grew unbounded: {len(snap)}"
    assert "truncated" in snap or snap.endswith("T")
    assert "H" in snap


def main() -> None:
    _check_identity_and_phase()
    _check_concurrent_isolation()
    _check_run_shell_live_one_box()
    _check_cancel_awaiting_approval()
    _check_cancel_event_during_stream()
    _check_live_ring_bounded()
    print("shell_controller ok")


if __name__ == "__main__":
    main()
