"""project.run argv binding: python/py → project interpreter; node/pip unchanged.

Legacy name kept for callers; implementation is ``bind_python_argv`` (U04).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from iris.system.project_ops import bind_python_argv, ensure_project_python


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

    with tempfile.TemporaryDirectory() as empty:
        # no .venv + allow_create=False → PATH/system python; never create project .venv
        bare = bind_python_argv(["python", "x.py"], empty, allow_create=False)
        assert len(bare) == 2 and bare[1] == "x.py", bare
        assert not (Path(empty) / ".venv").exists(), bare
        assert Path(bare[0]).is_file(), bare

    print("bind_python_argv self-check ok")


if __name__ == "__main__":
    main()
