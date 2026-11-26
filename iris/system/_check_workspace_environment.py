"""U04 / W11-D / FPR-04 — Workspace Environment Manager.

Fails when:
- ensure_project_python(create=False) invents a .venv
- bind_python_argv / plan_run .py path auto-creates a venv
- resolver skips an existing nested .venv that IDE walk-up would find
- allow_create=True / create=True no longer creates
- VIRTUAL_ENV runnable marker loses to unrelated project .venv
- lockfile presence claims poetry/uv support without a binary/env
- allow_create=False silently creates .venv
- product sys.executable is chosen as system project env
- Agent Core ``…/agent/*/venv`` is silently chosen as a user project interpreter
- agent-core probe python / cwd / environment_id collapse into workspace run path
- home-without-workspace defaults change (shell cwd / process.manage cwd / bound root)

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_workspace_environment
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

from iris.system.project_ops import (
    bind_python_argv,
    build_run_command,
    ensure_project_python,
    find_project_venv_python,
    plan_run,
)
from iris.system.workspace_env import (
    WorkspaceEnvironmentResolver,
    _is_agent_core_interpreter,
    agent_core_home,
    bind_execution_argv,
    iris_product_python,
    lockfile_names,
    system_python_on_path,
)


def _fake_prefix_python(prefix: Path) -> Path:
    if sys.platform == "win32":
        scripts = prefix / "Scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        py = scripts / "python.exe"
    else:
        scripts = prefix / "bin"
        scripts.mkdir(parents=True, exist_ok=True)
        py = scripts / "python"
    py.write_bytes(b"")
    return py


def _check_create_false_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        assert find_project_venv_python(root) is None
        assert ensure_project_python(root, create=False) is None
        assert not (root / ".venv").exists()


def _check_bind_does_not_create() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = bind_python_argv(["python", "app.py"], root, allow_create=False)
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
    """project.run shell path must not bind_python — Runtime shell= string stays Cursor-style."""
    from iris.ui.control_actions import project as project_mod

    src = Path(project_mod.__file__).read_text(encoding="utf-8")
    compact = src.replace(" ", "")
    assert "plan.shell_command" in src and '"shell":plan.shell_command' in compact, (
        "project_run shell mode must start via shell= string, not bound argv"
    )
    # Shell branch must not call bind_python_argv (only the else/argv branch may).
    shell_idx = src.find("plan.shell_command is not None")
    else_idx = src.find("else:", shell_idx)
    assert shell_idx >= 0 and else_idx > shell_idx
    shell_block = src[shell_idx:else_idx]
    assert "bind_python_argv" not in shell_block, (
        "shell-string mode must not rewrite via bind_python_argv"
    )


def _check_virtual_env_beats_unrelated_venv() -> None:
    """VIRTUAL_ENV (runnable) wins over an unrelated project .venv."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        project_py = ensure_project_python(root, create=True)
        assert project_py is not None

        fake_prefix = root / "active-shell-env"
        fake_py = _fake_prefix_python(fake_prefix)
        env = {**os.environ, "VIRTUAL_ENV": str(fake_prefix)}
        env.pop("CONDA_PREFIX", None)
        with mock.patch.dict(os.environ, env, clear=True):
            hit = WorkspaceEnvironmentResolver().resolve(
                project_root=root, allow_create=False
            )
        assert hit.source == "virtual_env", hit
        assert hit.python is not None
        assert hit.python.resolve() == fake_py.resolve()
        assert hit.python.resolve() != project_py.resolve()


def _check_lockfile_not_support() -> None:
    """uv.lock / poetry.lock presence alone must not claim uv/poetry source."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "uv.lock").write_text("# fake\n", encoding="utf-8")
        (root / "poetry.lock").write_text("# fake\n", encoding="utf-8")
        locks = lockfile_names(root)
        assert "uv.lock" in locks and "poetry.lock" in locks

        # Hide tool binaries so discovery cannot succeed.
        with mock.patch("iris.system.workspace_env.shutil.which", return_value=None):
            with mock.patch.dict(
                os.environ,
                {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "CONDA_PREFIX")},
                clear=True,
            ):
                hit = WorkspaceEnvironmentResolver().resolve(
                    project_root=root, allow_create=False
                )
        assert hit.source not in ("uv", "poetry"), (
            f"lockfile must not imply support; got source={hit.source!r}"
        )
        assert hit.locks == locks


def _check_allow_create_false_never_creates() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "uv.lock").write_text("# fake\n", encoding="utf-8")
        before = list(root.iterdir())
        with mock.patch("iris.system.workspace_env.shutil.which", return_value=None):
            with mock.patch.dict(
                os.environ,
                {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "CONDA_PREFIX")},
                clear=True,
            ):
                hit = WorkspaceEnvironmentResolver().resolve(
                    project_root=root, allow_create=False
                )
        assert not (root / ".venv").exists(), "allow_create=False must never create .venv"
        assert hit.source != "created"
        # Only lockfile (+ maybe nothing else) — no silent venv dir.
        assert not any(p.name == ".venv" for p in root.iterdir())
        _ = before


def _check_product_python_excluded_from_system() -> None:
    product = iris_product_python()
    assert product is not None
    # system picker must skip product even if which() returns it first.
    with mock.patch(
        "iris.system.workspace_env.shutil.which",
        side_effect=lambda name: str(product) if name in ("python", "python3", "py") else None,
    ):
        picked = system_python_on_path(exclude=product)
    assert picked is None or picked.resolve() != product.resolve()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with mock.patch(
            "iris.system.workspace_env.shutil.which",
            side_effect=lambda name: str(product) if name in ("python", "python3", "py") else None,
        ):
            with mock.patch.dict(
                os.environ,
                {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "CONDA_PREFIX")},
                clear=True,
            ):
                hit = WorkspaceEnvironmentResolver().resolve(
                    project_root=root, allow_create=False
                )
        if hit.python is not None:
            assert hit.python.resolve() != product.resolve()
            assert hit.source != "none"
        else:
            assert hit.source == "none"


def _agent_core_venv_python() -> Path | None:
    """Live Agent Core interpreter when installed; else a synthetic path under Agent Home."""
    try:
        from iris.engine._home import engine_python
        from iris.engine.types import _default_engine_home

        live = engine_python(_default_engine_home())
        if live is not None and Path(live).is_file():
            return Path(live).resolve()
    except Exception:
        pass
    home = agent_core_home()
    if sys.platform == "win32":
        return (home / "hermes-agent" / "venv" / "Scripts" / "python.exe").resolve()
    return (home / "hermes-agent" / "venv" / "bin" / "python").resolve()


def _check_agent_core_venv_not_silent() -> None:
    """VIRTUAL_ENV / PATH pointing at Agent Core must not become a project interpreter."""
    agent_py = _agent_core_venv_python()
    assert _is_agent_core_interpreter(agent_py), agent_py
    agent_prefix = agent_py.parent.parent  # …/venv

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        project_py = ensure_project_python(root, create=True)
        assert project_py is not None

        env = {**os.environ, "VIRTUAL_ENV": str(agent_prefix)}
        env.pop("CONDA_PREFIX", None)
        with mock.patch.dict(os.environ, env, clear=True):
            hit = WorkspaceEnvironmentResolver().resolve(
                project_root=root, allow_create=False
            )
        assert hit.source != "virtual_env", hit
        assert hit.python is not None
        assert hit.python.resolve() == project_py.resolve()
        assert hit.python.resolve() != agent_py.resolve()
        assert not _is_agent_core_interpreter(hit.python)

        # Explicit user preference may still select Agent Core.
        explicit = WorkspaceEnvironmentResolver().resolve(
            project_root=root,
            user_python=agent_py,
            allow_create=False,
        )
        if agent_py.is_file():
            assert explicit.source == "user"
            assert explicit.python is not None
            assert explicit.python.resolve() == agent_py.resolve()


def _check_agent_probe_vs_workspace_run_distinct() -> None:
    """(a) agent-core probe vs (b) workspace run — sys.executable / cwd / environment_id."""
    from iris.engine._home import engine_python
    from iris.engine.types import _default_engine_home
    from iris.system.run_env import build_child_env as scrub_env

    agent_home = _default_engine_home()
    agent_py = engine_python(agent_home)
    if agent_py is None or not Path(agent_py).is_file():
        # No live Agent Core — still prove workspace path stays off Agent Home.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws_py = ensure_project_python(root, create=True)
            assert ws_py is not None
            hit = WorkspaceEnvironmentResolver().resolve(
                project_root=root, allow_create=False
            )
            assert hit.python is not None
            assert hit.python.resolve() == Path(ws_py).resolve()
            assert not _is_agent_core_interpreter(hit.python)
            env_ws = scrub_env(
                {"PATH": "C:\\Windows\\System32"},
                {"IRIS_ENVIRONMENT_ID": "workspace-run"},
            )
            assert env_ws.get("IRIS_ENVIRONMENT_ID") == "workspace-run"
        return

    agent_py_r = Path(agent_py).resolve()
    assert _is_agent_core_interpreter(agent_py_r)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ws_py = ensure_project_python(root, create=True)
        assert ws_py is not None
        hit = WorkspaceEnvironmentResolver().resolve(
            project_root=root, allow_create=False
        )
        assert hit.python is not None
        ws_py_r = hit.python.resolve()
        assert ws_py_r == Path(ws_py).resolve()
        assert ws_py_r != agent_py_r

        # argv bind for workspace run uses workspace interpreter, not Agent Core.
        bound = bind_execution_argv(
            ["python", "app.py"], project_root=root, allow_create=False
        )
        assert Path(bound[0]).resolve() == ws_py_r

        # Distinct environment_id / cwd contracts.
        env_agent = scrub_env(
            {"PATH": "C:\\Windows\\System32"},
            {"IRIS_ENVIRONMENT_ID": "agent-core-probe"},
        )
        env_ws = scrub_env(
            {"PATH": "C:\\Windows\\System32"},
            {"IRIS_ENVIRONMENT_ID": "workspace-run"},
        )
        assert env_agent.get("IRIS_ENVIRONMENT_ID") == "agent-core-probe"
        assert env_ws.get("IRIS_ENVIRONMENT_ID") == "workspace-run"
        assert env_agent["IRIS_ENVIRONMENT_ID"] != env_ws["IRIS_ENVIRONMENT_ID"]

        agent_cwd = str(Path(agent_home).resolve())
        workspace_cwd = str(root.resolve())
        assert agent_cwd != workspace_cwd
        assert str(agent_py_r).startswith(str(agent_core_home()))
        assert not str(ws_py_r).startswith(str(agent_core_home()))


def _check_home_without_workspace_defaults() -> None:
    """No bound workspace: allowed default work path is user home / settings — not Agent Home.

    Documented contracts (callable behavior):
    - iris_shell.default_shell_cwd → Path.home()
    - process.manage empty cwd without workspace_root → Path.home()
    - process.manage empty cwd with workspace_root → that workspace (binding kept)
    - resolve_bound_work_root without bound IDE → error (project write/run refuses Agent Home)
    """
    from iris.system.iris_shell import default_shell_cwd
    from iris.system.process_start_plan import (
        FinalizedStartPlan,
        finalize_process_start_plan,
    )
    from iris.ui.control_bindings import resolve_bound_work_root

    home = Path.home().resolve()
    assert default_shell_cwd() == home
    assert home != agent_core_home()

    # process.manage start plan: no cwd + no workspace_root → user home (not Agent Home).
    plan_home = finalize_process_start_plan(
        {"action": "start", "shell": "echo ok"},
        workspace_root=None,
    )
    assert isinstance(plan_home, FinalizedStartPlan)
    assert Path(plan_home.cwd).resolve() == home
    assert Path(plan_home.cwd).resolve() != Path(agent_core_home()).resolve()

    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp).resolve()
        plan_ws = finalize_process_start_plan(
            {"action": "start", "shell": "echo ok"},
            workspace_root=str(ws),
        )
        assert isinstance(plan_ws, FinalizedStartPlan)
        assert Path(plan_ws.cwd).resolve() == ws

    window = mock.MagicMock()
    window._conversation_id = 0
    window._bound_slot = None
    window._get_bound_ide_session.return_value = None
    root, err = resolve_bound_work_root(window, {})
    assert root == ""
    assert "bound IDE workspace" in err


def _check_ide_bound_workspace_user_interpreter() -> None:
    """IDE findProjectPython: bound workspace roots + optional userPython preference."""
    ide = (
        Path(__file__).resolve().parents[2]
        / "integrations"
        / "iris-ide"
        / "src"
        / "browser"
        / "iris-ide-project-python.ts"
    )
    text = ide.read_text(encoding="utf-8")
    assert "userPython" in text
    assert "workspaceRoots" in text
    assert "WorkspaceEnvironmentResolver" in text
    assert "findProjectPython" in text
    # Preference beats walk-up when the path exists.
    assert "if (userPython && (await exists(userPython)))" in text.replace("\r\n", "\n")


def main() -> None:
    _check_create_false_returns_none()
    _check_bind_does_not_create()
    _check_resolver_prefers_existing_and_walk_up()
    _check_explicit_create_still_works()
    _check_plan_run_py_no_create()
    _check_shell_mode_no_conflicting_argv()
    _check_virtual_env_beats_unrelated_venv()
    _check_lockfile_not_support()
    _check_allow_create_false_never_creates()
    _check_product_python_excluded_from_system()
    _check_agent_core_venv_not_silent()
    _check_agent_probe_vs_workspace_run_distinct()
    _check_home_without_workspace_defaults()
    _check_ide_bound_workspace_user_interpreter()
    print("workspace_environment ok")


if __name__ == "__main__":
    main()
