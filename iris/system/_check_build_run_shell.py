"""project.run string command = Cursor shell mode (no shlex → & 'cd' bug)."""

from __future__ import annotations

from iris.system.project_ops import (
    RunPlan,
    build_iris_terminal_command,
    build_iris_terminal_shell,
    build_run_command,
    plan_run,
)


def main() -> None:
    sentence = "cd /tmp && echo hi"
    plan = plan_run(command=sentence)
    assert isinstance(plan, RunPlan)
    assert plan.shell_command == sentence
    assert plan.argv is None

    wrapper = build_iris_terminal_shell(sentence)
    assert "&&" in wrapper, wrapper
    assert "cd /tmp && echo hi" in wrapper, wrapper
    assert "& 'cd'" not in wrapper, wrapper
    assert "Tee-Object" in wrapper or " tee " in wrapper, wrapper
    assert "IRIS_EXIT" in wrapper

    try:
        build_run_command(command=sentence)
        raise AssertionError("string command must not argv-split via build_run_command")
    except ValueError as exc:
        assert "shell mode" in str(exc).lower() or "plan_run" in str(exc)

    argv_plan = plan_run(command=["python", "-c", "print(1)"])
    assert argv_plan.shell_command is None
    assert argv_plan.argv == ["python", "-c", "print(1)"]
    argv_wrap = build_iris_terminal_command(argv_plan.argv or [])
    assert argv_wrap.startswith("New-Item") or "mkdir -p .iris" in argv_wrap
    if "Tee-Object" in argv_wrap:
        assert "& 'python'" in argv_wrap or "& 'python.exe'" in argv_wrap, argv_wrap
        assert "& 'cd'" not in argv_wrap

    file_argv = build_run_command(file="hello.py")
    assert file_argv == ["python", "hello.py"]

    print("build_run_shell self-check ok")


if __name__ == "__main__":
    main()
