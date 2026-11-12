"""Hermes 업데이트 감지 자검. 실제 hermes update 는 호출하지 않는다."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from iris.system.iris_agent_update import (
    check_hermes_update,
    hermes_update_argv,
)
from iris.system.win_subprocess import no_window_kwargs


def _git(repo: Path, *args: str) -> None:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
        **no_window_kwargs(),
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "git failed")[:240])


def _main() -> None:
    assert hermes_update_argv(r"C:\hermes.exe")[-2:] == ["update", "--yes"]

    with tempfile.TemporaryDirectory(prefix="iris-hermes-upd-") as tmp:
        repo = Path(tmp) / "hermes-agent"
        repo.mkdir()
        (repo / "hermes_cli").mkdir()
        _git(repo, "init")
        _git(repo, "config", "user.email", "iris@example.com")
        _git(repo, "config", "user.name", "iris")
        (repo / "README").write_text("x\n", encoding="utf-8")
        _git(repo, "add", "README")
        _git(repo, "commit", "-m", "init")
        local = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            **no_window_kwargs(),
        ).stdout.strip()

        same = check_hermes_update(repo=repo, remote_sha=local)
        assert not same.available, same
        assert same.detail == "최신"

        behind = check_hermes_update(repo=repo, remote_sha="f" * 40)
        assert behind.available, behind
        assert behind.local_sha == local
        assert "→" in behind.detail

        missing = check_hermes_update(repo=Path(tmp) / "nope", remote_sha="abc")
        assert not missing.available

    print("hermes_update check ok")


if __name__ == "__main__":
    _main()
