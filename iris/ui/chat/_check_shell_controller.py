"""U07 shell controller identity map + live paint + cancel."""

from __future__ import annotations

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

    def fake_stream(_job: ShellJob, on_chunk, cancel_event=None) -> ShellOutcome:
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
    mapped = sc.get_by_request(req.request_id)
    assert mapped is not None
    assert mapped.block_id == "live-1"
    assert mapped.run_id == "run-live"
    assert mapped.status == "completed"
    inserts = [op for op in chat.ops if op[0] == "insert"]
    assert len(inserts) == 1


def _check_cancel_without_run() -> None:
    sc.reset_for_tests()
    req = sc.new_request(command="noop")
    assert sc.cancel_request(req.request_id) is False
    assert sc.get_by_request(req.request_id).status == "cancelled"


def main() -> None:
    _check_identity_and_phase()
    _check_concurrent_isolation()
    _check_run_shell_live_one_box()
    _check_cancel_without_run()
    print("shell_controller ok")


if __name__ == "__main__":
    main()
