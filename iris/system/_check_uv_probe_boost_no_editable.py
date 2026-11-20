"""uv sync 성공 후 probe miss → boost만, pip install -e 금지.

python -m iris.system._check_uv_probe_boost_no_editable
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

from iris.system import iris_agent_install as m
from iris.system.iris_agent_install import InstallResult


def _ok(cmd=None, stdout="", stderr=""):
    return subprocess.CompletedProcess(list(cmd or ["x"]), 0, stdout, stderr)


def _fail(kind: str, msg: str, body: str = "") -> InstallResult:
    return InstallResult(False, msg, kind)


def _drive_finish(
    *,
    staging: Path,
    home: Path,
    py: Path,
    uv: str | None,
    probe_n: dict[str, int],
    boost_n: dict[str, int],
    editable: list[list[str]],
) -> InstallResult:
    def fake_run(cmd, **kw):
        argv = [str(c) for c in cmd]
        if len(argv) >= 3 and argv[1] == "-m" and argv[2] == "venv":
            venv_py = staging / (
                "venv/Scripts/python.exe" if sys.platform == "win32" else "venv/bin/python"
            )
            venv_py.parent.mkdir(parents=True, exist_ok=True)
            venv_py.write_bytes(b"x" * 2048)
            return _ok(cmd)
        if "-m" in argv and "pip" in argv and "install" in argv and "-e" in argv:
            editable.append(argv)
            return _ok(cmd)
        return _ok(cmd, stdout="ok")

    def fake_probe(_venv_py):
        probe_n["n"] += 1
        if probe_n["n"] == 1:
            return False, "ModuleNotFoundError: No module named 'aiohttp'"
        return True, "venv import ok"

    def fake_boost(_venv_py):
        boost_n["n"] += 1
        return _ok(["pip", "install"])

    log: list[str] = []
    with (
        mock.patch.object(m, "_run", side_effect=fake_run),
        mock.patch.object(m, "_run_dep", side_effect=lambda *a, **k: _ok()),
        mock.patch.object(m, "_probe_venv", side_effect=fake_probe),
        mock.patch.object(m, "_boost_probe_deps", side_effect=fake_boost),
        mock.patch.object(m, "_activate_staged", return_value=(True, "activated")),
        mock.patch.object(m, "_wanted_extras", return_value=()),
        mock.patch.object(m, "_user_path_prepend"),
    ):
        return m._finish_staged_install(
            staging=staging,
            home=home,
            stamp="t",
            py=py,
            uv=uv,
            command="hermes",
            log=log,
            emit=lambda _s: None,
            fail=_fail,
            run_streamed=None,
            should_abort=None,
            probe_gateway=False,
        )


def _check_uv_installed_probe_miss_boosts_not_editable() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-uv-probe-") as tmp:
        root = Path(tmp)
        home = root / "home"
        staging = root / "staging"
        home.mkdir()
        staging.mkdir()
        (staging / "uv.lock").write_text("# lock\n", encoding="utf-8")
        py = root / "python.exe"
        py.write_bytes(b"x" * 2048)

        probe_n = {"n": 0}
        boost_n = {"n": 0}
        editable: list[list[str]] = []
        result = _drive_finish(
            staging=staging,
            home=home,
            py=py,
            uv="uv",
            probe_n=probe_n,
            boost_n=boost_n,
            editable=editable,
        )
        assert result.ok, result
        assert boost_n["n"] == 1, boost_n
        assert probe_n["n"] == 2, probe_n
        assert editable == [], editable


def _check_pip_path_probe_miss_still_editable() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-pip-probe-") as tmp:
        root = Path(tmp)
        home = root / "home"
        staging = root / "staging"
        home.mkdir()
        staging.mkdir()
        py = root / "python.exe"
        py.write_bytes(b"x" * 2048)

        probe_n = {"n": 0}
        boost_n = {"n": 0}
        editable: list[list[str]] = []
        result = _drive_finish(
            staging=staging,
            home=home,
            py=py,
            uv=None,
            probe_n=probe_n,
            boost_n=boost_n,
            editable=editable,
        )
        assert result.ok, result
        assert boost_n["n"] == 1, boost_n
        assert any("-e" in argv and "." in argv for argv in editable), editable


def _main() -> None:
    _check_uv_installed_probe_miss_boosts_not_editable()
    _check_pip_path_probe_miss_still_editable()
    print("ok")


if __name__ == "__main__":
    _main()
