"""project.run argv binding: python/py → project interpreter; node/pip unchanged.

Legacy name kept for callers; implementation is ``bind_python_argv`` (U04).
W11-D: allow_create=False never creates; start_managed_run binds bare python.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from iris.system.project_ops import bind_python_argv, ensure_project_python, start_managed_run
from iris.system.workspace_env import bind_execution_argv


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        py = ensure_project_python(root, create=True)
        assert py is not None and py.is_file()
        py_s = str(py.resolve())

        script = bind_python_argv(["python", "script.py"], root, allow_create=False)
        assert script == [py_s, "script.py"], script

        # find-only: no create when venv already present
        again = bind_python_argv(["python", "-c", "pass"], root)
        assert again[0] == py_s, again

        node = bind_python_argv(["node", "app.js"], root)
        assert node == ["node", "app.js"], node

        # pip / uv are not python launchers — left alone (no silent rewrite)
        pip = bind_python_argv(["pip", "install", "x"], root)
        assert pip == ["pip", "install", "x"], pip
        uv = bind_python_argv(["uv", "pip", "install", "x"], root)
        assert uv == ["uv", "pip", "install", "x"], uv

        # Leading .py file binds via execution helper
        py_file = bind_execution_argv(["app.py"], project_root=root, allow_create=False)
        assert py_file[0] == py_s and py_file[1] == "app.py", py_file

        # Full interpreter path must not be remapped by execution binder
        full = bind_execution_argv(
            [sys.executable, "-c", "pass"],
            project_root=root,
            allow_create=False,
        )
        assert full[0] == sys.executable, full

    with tempfile.TemporaryDirectory() as empty:
        # no .venv + allow_create=False → PATH/system python; never create project .venv
        bare = bind_python_argv(["python", "x.py"], empty, allow_create=False)
        assert len(bare) == 2 and bare[1] == "x.py", bare
        assert not (Path(empty) / ".venv").exists(), bare
        assert Path(bare[0]).is_file(), bare

        # start_managed_run also must not create
        from iris.system import execution_runtime as rtmod
        from iris.system.execution_runtime import ExecutionRuntime, reset_default_runtime_for_tests

        reset_default_runtime_for_tests()
        rt = ExecutionRuntime(runs_root=Path(empty) / "runs")
        rtmod._DEFAULT = rt
        try:
            run_id = start_managed_run(
                argv=["python", "-c", "pass"],
                cwd=empty,
                timeout_s=30,
                owner="check_bind",
            )
            rec = rt.wait(run_id, timeout_s=30)
            assert not (Path(empty) / ".venv").exists(), "start_managed_run must not create .venv"
            assert rec.argv and Path(rec.argv[0]).is_file(), rec.argv
            assert Path(rec.argv[0]).name.lower().startswith("python"), rec.argv
        finally:
            reset_default_runtime_for_tests()

    print("bind_python_argv self-check ok")


if __name__ == "__main__":
    main()
