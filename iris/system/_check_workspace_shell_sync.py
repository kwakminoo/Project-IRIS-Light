"""U09 — product run paths share WorkspaceEnvironmentResolver / build_child_env."""

from __future__ import annotations

from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent  # iris/system
    iris = root.parent
    runtime = (root / "execution_runtime.py").read_text(encoding="utf-8")
    assert "bind_execution_argv" in runtime or "WorkspaceEnvironment" in runtime
    assert "build_child_env" in runtime
    project_ops = (root / "project_ops.py").read_text(encoding="utf-8")
    assert "start_managed_run" in project_ops
    assert "bind_execution_argv" in project_ops
    # Shell-string intentional non-rewrite (W11-D residual preserved).
    ws = (root / "workspace_env.py").read_text(encoding="utf-8")
    assert "class WorkspaceEnvironment" in ws or "WorkspaceEnvironmentResolver" in ws
    # Product paths must not invent a second env mixer.
    project = (iris / "ui" / "control_actions" / "project.py").read_text(encoding="utf-8")
    assert "start_managed_run" in project
    assert "append_terminal_output" in project  # U08 mirror, not second process
    assert "echo IRIS_RUN_ID=" not in project or "append_terminal_output" in project
    shell = (iris / "ui" / "control_actions" / "shell.py").read_text(encoding="utf-8")
    assert "stream_shell_job" in shell
    print("workspace_shell_sync ok")


if __name__ == "__main__":
    main()
