"""워크스페이스 .venv 바인딩 self-check."""

from __future__ import annotations

import tempfile
from pathlib import Path

from iris.system.project_ops import (
    bind_python_argv,
    build_run_command,
    ensure_project_python,
    find_project_venv_python,
)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "app.py").write_text("print(1)\n", encoding="utf-8")
        assert find_project_venv_python(root) is None
        py = ensure_project_python(root, create=True)
        assert py.is_file()
        assert find_project_venv_python(root) == py
        argv = build_run_command(file="app.py", project_root=root)
        assert argv[0] == str(py)
        assert argv[1] == "app.py"
        again = bind_python_argv(["python", "-m", "pip", "install", "x"], root)
        assert again[0] == str(py)
        assert again[1:4] == ["-m", "pip", "install"]
    print("project_python self-check ok")


if __name__ == "__main__":
    main()
