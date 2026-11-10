from __future__ import annotations

import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOLBAR = ROOT / "integrations" / "iris-ide" / "src" / "browser" / "iris-ide-run-toolbar.ts"
HELPER = ROOT / "integrations" / "iris-ide" / "src" / "browser" / "iris-ide-project-python.ts"


def _venv_python_at(root: Path) -> Path:
    if root.anchor and len(str(root)) >= 2 and str(root)[1] == ":":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def find_project_python(file_abs: Path, workspace_roots: list[Path]) -> tuple[Path, Path] | None:
    ordered: list[Path] = []
    seen: set[Path] = set()

    def push(p: Path) -> None:
        key = p.resolve()
        if key in seen:
            return
        seen.add(key)
        ordered.append(key)

    file_res = file_abs.resolve()
    for root in workspace_roots:
        root_res = root.resolve()
        try:
            file_res.relative_to(root_res)
        except ValueError:
            continue
        push(root_res)

    cur = file_res.parent
    for _ in range(64):
        push(cur)
        if cur.parent == cur:
            break
        cur = cur.parent

    for root in ordered:
        py = _venv_python_at(root)
        if py.is_file():
            return py, root
    return None


def check_algorithm() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        nested = root / "lab" / "week7"
        nested.mkdir(parents=True)
        script = nested / "7-7.py"
        script.write_text("import tensorflow\n", encoding="utf-8")
        py = _venv_python_at(root)
        py.parent.mkdir(parents=True)
        py.write_text("", encoding="utf-8")

        hit = find_project_python(script, [root])
        assert hit is not None, "workspace .venv must win over nested dirs"
        assert hit[0] == py.resolve()
        assert hit[1] == root.resolve()

        bare = find_project_python(script, [])
        assert bare is not None and bare[0] == py.resolve()

        other = root / "other.py"
        other.write_text("print(1)\n", encoding="utf-8")
        hit2 = find_project_python(other, [root])
        assert hit2 is not None


def check_sources() -> None:
    assert HELPER.is_file(), f"missing helper module: {HELPER}"
    helper = HELPER.read_text(encoding="utf-8")
    assert "findProjectPython" in helper
    assert "argvForRunnableFile" in helper
    assert ".venv" in helper
    assert "Scripts" in helper and "python.exe" in helper

    toolbar = TOOLBAR.read_text(encoding="utf-8")
    assert "argvForRunnableFile" in toolbar, "toolbar must call argvForRunnableFile"
    assert "WorkspaceService" in toolbar
    assert "FileService" in toolbar
    assert "iris-ide-project-python" in toolbar or "argvForRunnableFile" in toolbar


def main() -> None:
    check_algorithm()
    check_sources()
    print("ide_run_python self-check ok")


if __name__ == "__main__":
    main()
