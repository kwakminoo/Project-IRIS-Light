"""project.run status mapping: running / ok / failed from terminal log parse."""

from __future__ import annotations

from pathlib import Path

from iris.system.project_ops import result_from_terminal_log, run_status_from_log_result


def main() -> None:
    argv = ["pip", "install", "x"]
    cwd = "C:/proj"

    no_exit = result_from_terminal_log(
        "Collecting torch...\n",
        argv=argv,
        cwd=cwd,
        elapsed_sec=12.0,
    )
    assert no_exit["confirmed"] is False
    assert no_exit["exit_code"] is None
    assert run_status_from_log_result(no_exit) == "running"

    empty = result_from_terminal_log("", argv=argv, cwd=cwd, elapsed_sec=12.0)
    assert run_status_from_log_result(empty) == "running"

    ok = result_from_terminal_log(
        "done\nIRIS_EXIT:0\n",
        argv=argv,
        cwd=cwd,
        elapsed_sec=3.0,
    )
    assert ok["confirmed"] is True and ok["exit_code"] == 0
    assert run_status_from_log_result(ok) == "ok"

    failed = result_from_terminal_log(
        "boom\nIRIS_EXIT:1\n",
        argv=argv,
        cwd=cwd,
        elapsed_sec=2.0,
    )
    assert failed["exit_code"] == 1
    assert run_status_from_log_result(failed) == "failed"

    timed = {**ok, "timed_out": True}
    assert run_status_from_log_result(timed) == "failed"

    project_src = (
        Path(__file__).resolve().parents[1] / "ui" / "control_actions" / "project.py"
    ).read_text(encoding="utf-8")
    assert "run_status_from_log_result" in project_src
    assert '"status": "running"' in project_src
    assert "waiting for IRIS_EXIT" in project_src
    # Delivered-but-unconfirmed must not burn budget via err_result.
    assert project_src.count("command was delivered but") == 0

    print("project_run_status self-check ok")


if __name__ == "__main__":
    main()
