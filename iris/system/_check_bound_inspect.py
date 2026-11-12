"""bound_inspect capsule self-check.

.venv\\Scripts\\python.exe -m iris.system._check_bound_inspect
"""

from __future__ import annotations

import inspect
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

from iris.system import bound_inspect as bi
from iris.system.win_subprocess import no_window_kwargs


def _git_init(root: Path) -> None:
    env = bi._git_env(root)
    bi._run_hidden(("git", "init"), cwd=root, timeout_sec=30.0, env=env)
    bi._run_hidden(
        ("git", "config", "user.email", "iris@test"),
        cwd=root,
        timeout_sec=10.0,
        env=env,
    )
    bi._run_hidden(
        ("git", "config", "user.name", "iris"),
        cwd=root,
        timeout_sec=10.0,
        env=env,
    )


def check_search_and_jail() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        src = root / "pkg"
        src.mkdir()
        (src / "hit.py").write_text("token_FINDME_bound\n", encoding="utf-8")
        (src / "other.txt").write_text("nope\n", encoding="utf-8")
        rep = bi.search_content(root, pattern="FINDME_bound", path="pkg", max_matches=20)
        assert rep["kind"] == "search"
        assert rep["tool"] in ("rg", "python-grep")
        assert rep["payload"]["match_count"] >= 1
        assert any("FINDME_bound" in m["text"] for m in rep["payload"]["matches"])
        try:
            bi.search_content(root, pattern="x", path="../")
            raise AssertionError("path escape must fail")
        except ValueError:
            pass


def check_git_status_soft_and_dirty() -> None:
    with tempfile.TemporaryDirectory() as td:
        bare = Path(td) / "norepo"
        bare.mkdir()
        soft = bi.git_status(bare)
        assert soft["kind"] == "git_status"
        assert soft["payload"]["is_repo"] is False
        assert soft["payload"]["porcelain"] == []

        root = Path(td) / "repo"
        root.mkdir()
        _git_init(root)
        (root / "a.txt").write_text("hello\n", encoding="utf-8")
        st = bi.git_status(root)
        assert st["payload"]["is_repo"] is True
        assert st["payload"]["clean"] is False
        paths = [e["path"] for e in st["payload"]["porcelain"]]
        assert "a.txt" in paths


def check_git_diff_and_truncate() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _git_init(root)
        target = root / "mark.txt"
        target.write_text("base\n", encoding="utf-8")
        env = bi._git_env(root)
        bi._run_hidden(("git", "add", "mark.txt"), cwd=root, timeout_sec=15.0, env=env)
        bi._run_hidden(
            ("git", "commit", "-m", "init"),
            cwd=root,
            timeout_sec=15.0,
            env=env,
        )
        target.write_text("base\nMARKER_DIFF_TOKEN\n", encoding="utf-8")
        diff = bi.git_diff(root, path="mark.txt")
        assert diff["kind"] == "git_diff"
        assert diff["payload"]["is_repo"] is True
        assert "MARKER_DIFF_TOKEN" in diff["payload"]["patch"]
        tiny = bi.git_diff(root, path="mark.txt", max_bytes=20)
        assert tiny["payload"]["truncated"] is True
        assert tiny["truncated"] is True


def check_no_window_kwargs() -> None:
    expected = no_window_kwargs()
    if not expected:
        return
    seen: dict = {}

    def fake_run(*_a, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(args=["git"], returncode=0, stdout="", stderr="")

    with mock.patch("iris.system.bound_inspect.subprocess.run", side_effect=fake_run):
        with tempfile.TemporaryDirectory() as td:
            bi._run_hidden(("git", "status"), cwd=Path(td), timeout_sec=5.0)
    assert seen.get("shell") is False
    if "creationflags" in expected:
        assert seen.get("creationflags") == expected["creationflags"]


def check_no_mutating_git_in_source() -> None:
    src = Path(inspect.getsourcefile(bi) or "").read_text(encoding="utf-8")
    for banned in ("git commit", "git push", "git reset", "git checkout"):
        assert banned not in src, banned
    assert "shell=True" not in src


def main() -> None:
    check_search_and_jail()
    check_git_status_soft_and_dirty()
    check_git_diff_and_truncate()
    check_no_window_kwargs()
    check_no_mutating_git_in_source()
    print("bound_inspect check ok")


if __name__ == "__main__":
    main()
