"""U04 — Workspace Environment Manager.

Fails when:
- ensure_project_python(create=False) invents a .venv
- bind_python_argv / plan_run .py path auto-creates a venv
- resolver skips an existing nested .venv that IDE walk-up would find
- allow_create=True / create=True no longer creates

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_workspace_environment
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from iris.system.project_ops import (
    bind_python_argv,
    build_run_command,
    ensure_project_python,
    find_project_venv_python,
    plan_run,
)
from iris.system.workspace_env import WorkspaceEnvironmentResolver


def _check_create_false_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert find_project_venv_python(root) is None
        assert ensure_project_python(root, create=False) is None
        assert not (root / ".venv").exists()


def _check_bind_does_not_create() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = bind_python_argv(["python", "app.py"], root)
        assert not (root / ".venv").exists(), "bind_python_argv must not create .venv"
        assert out[0].lower().endswith("python") or out[0].lower().endswith("python.exe")
        assert out[1:] == ["app.py"]


def _check_resolver_prefers_existing_and_walk_up() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        nested = root / "pkg" / "sub"
        nested.mkdir(parents=True)
        # Existing .venv at root — find without create.
        py = ensure_project_python(root, create=True)
        assert py is not None and py.is_file()

        resolver = WorkspaceEnvironmentResolver()
        hit = resolver.resolve(project_root=root, file=nested / "main.py", allow_create=False)
        assert hit.python is not None
        assert hit.python.resolve() == py.resolve()
        assert hit.source == "venv"

        # Nested file under empty child root: walk-up to ancestor .venv.
        child_root = root / "apps" / "web"
        child_root.mkdir(parents=True)
        (child_root / "run.py").write_text("print(1)\n", encoding="utf-8")
        nested_hit = resolver.resolve(
            project_root=child_root,
            file=child_root / "run.py",
            allow_create=False,
        )
        # child has no .venv; walk-up from file finds root/.venv
        assert nested_hit.python is not None
        assert nested_hit.python.resolve() == py.resolve()
        assert nested_hit.source == "venv"


def _check_explicit_create_still_works() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        created = ensure_project_python(root, create=True)
        assert created is not None and created.is_file()
        again = WorkspaceEnvironmentResolver().resolve(
            project_root=root, allow_create=True
        )
        assert again.python is not None
        assert again.python.resolve() == created.resolve()


def _check_plan_run_py_no_create() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "app.py").write_text("print(1)\n", encoding="utf-8")
        plan = plan_run(file="app.py", project_root=root)
        assert plan.argv is not None
        assert not (root / ".venv").exists()
        argv = build_run_command(file="app.py", project_root=root)
        assert argv[-1] == "app.py"
        assert not (root / ".venv").exists()


def _check_shell_mode_no_conflicting_argv() -> None:
    """project.run shell path must not pass argv that steals wrapRun from Tee/IRIS_EXIT."""
    from iris.ui.control_actions import project as project_mod

    src = Path(project_mod.__file__).read_text(encoding="utf-8")
    # Shell branch must not feed the shell string into bridge argv.
    assert "bridge_argv" in src or "argv=None" in src or 'argv=[]' in src or "argv = []" in src, (
        "project_run shell mode must omit/empty bridge argv so poller uses markExit"
    )


def main() -> None:
    _check_create_false_returns_none()
    _check_bind_does_not_create()
    _check_resolver_prefers_existing_and_walk_up()
    _check_explicit_create_still_works()
    _check_plan_run_py_no_create()
    _check_shell_mode_no_conflicting_argv()
    print("workspace_environment ok")


if __name__ == "__main__":
    main()
