from __future__ import annotations

import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOLBAR = ROOT / "integrations" / "iris-ide" / "src" / "browser" / "iris-ide-run-toolbar.ts"
HELPER = ROOT / "integrations" / "iris-ide" / "src" / "browser" / "iris-ide-project-python.ts"


def _is_win_path_style(path: Path | str) -> bool:
    s = str(path)
    return (len(s) >= 2 and s[1] == ":") or "\\" in s


def _venv_python_at(root: Path) -> Path:
    if _is_win_path_style(root):
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def default_python_argv(abs_path: Path | str) -> list[str]:
    """Mirror of TS defaultPythonArgv — user/system launcher, never bare python."""
    path = str(abs_path)
    if _is_win_path_style(path):
        return ["py", "-3", path]
    return ["python3", path]


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


def argv_for_runnable_file(
    abs_path: Path,
    workspace_roots: list[Path],
) -> tuple[list[str], Path]:
    """Mirror of TS argvForRunnableFile for .py files."""
    file_dir = abs_path.parent
    hit = find_project_python(abs_path, workspace_roots)
    if hit:
        py, root = hit
        return [str(py), str(abs_path)], root
    return default_python_argv(abs_path), file_dir


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

        argv, cwd = argv_for_runnable_file(script, [root])
        assert argv[0] == str(py.resolve())
        assert cwd == root.resolve()


def check_no_venv_fallback() -> None:
    """No .venv near the script → launcher prefers user/system interp, not bare python."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        script = root / "solo.py"
        script.write_text("print(1)\n", encoding="utf-8")
        assert find_project_python(script, []) is None
        assert find_project_python(script, [root]) is None

        argv, cwd = argv_for_runnable_file(script, [root])
        assert cwd == script.parent
        assert argv[0] != "python", f"must not fall back to bare python: {argv}"
        assert "python" not in argv[:1]
        if _is_win_path_style(script):
            assert argv == ["py", "-3", str(script)], argv
        else:
            assert argv == ["python3", str(script)], argv

        # Win-style path string even on posix hosts (TS path-style detect)
        win_script = r"C:\Users\demo\proj\solo.py"
        win_argv = default_python_argv(win_script)
        assert win_argv == ["py", "-3", win_script], win_argv
        assert win_argv[0] != "python"

        posix_script = "/home/demo/proj/solo.py"
        posix_argv = default_python_argv(posix_script)
        assert posix_argv == ["python3", posix_script], posix_argv
        assert posix_argv[0] != "python"


def check_sources() -> None:
    assert HELPER.is_file(), f"missing helper module: {HELPER}"
    helper = HELPER.read_text(encoding="utf-8")
    assert "findProjectPython" in helper
    assert "argvForRunnableFile" in helper
    assert ".venv" in helper
    assert "Scripts" in helper and "python.exe" in helper
    assert "defaultPythonArgv" in helper or ("'py'" in helper and "'-3'" in helper) or (
        '"py"' in helper and '"-3"' in helper
    ), "fallback must prefer py -3 (or defaultPythonArgv helper)"
    assert "py" in helper and "-3" in helper
    # Must not keep bare-python-only fallback for .py files
    assert "['python', absPath]" not in helper and '["python", absPath]' not in helper, (
        "must not fall back to bare ['python', absPath]"
    )
    assert "return { argv: ['python', absPath]" not in helper
    assert 'return { argv: ["python", absPath]' not in helper

    toolbar = TOOLBAR.read_text(encoding="utf-8")
    assert "argvForRunnableFile" in toolbar, "toolbar must call argvForRunnableFile"
    assert "WorkspaceService" in toolbar
    assert "FileService" in toolbar
    assert "iris-ide-project-python" in toolbar or "argvForRunnableFile" in toolbar


def main() -> None:
    check_algorithm()
    check_no_venv_fallback()
    check_sources()
    print("ide_run_python self-check ok")


if __name__ == "__main__":
    main()
