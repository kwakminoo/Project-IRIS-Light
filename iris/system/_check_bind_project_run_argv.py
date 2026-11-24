"""project.run argv binding: pip / uv pip → project .venv python -m pip."""

from __future__ import annotations

import tempfile
from pathlib import Path

from iris.system.project_ops import bind_project_run_argv, ensure_project_python


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        py = ensure_project_python(root, create=True)
        assert py is not None and py.is_file()
        py_s = str(py.resolve())

        pip = bind_project_run_argv(["pip", "install", "x"], root)
        assert pip == [py_s, "-m", "pip", "install", "x"], pip

        uv = bind_project_run_argv(["uv", "pip", "install", "x"], root)
        assert uv == [py_s, "-m", "pip", "install", "x"], uv

        script = bind_project_run_argv(["python", "script.py"], root)
        assert script == [py_s, "script.py"], script

        node = bind_project_run_argv(["node", "app.js"], root)
        assert node == ["node", "app.js"], node

    print("bind_project_run_argv self-check ok")


if __name__ == "__main__":
    main()
