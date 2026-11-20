"""uv sync 성공 후 probe miss → boost만, pip install -e . 금지.

재현 사례: aiohttp ModuleNotFoundError 뒤 editable 재설치가
Pillow==13 vs browser-harness pillow==12.3.0 ResolutionImpossible.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

from iris.system import iris_agent_install as install


def _ok(stdout: str = "ok") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["mock"], 0, stdout, "")


def _drive_finish(*, installed_via_uv: bool) -> tuple[list[str], list[str]]:
    """관측 순서: 'boost' / 'editable' 이벤트 열과 install 성공 여부."""
    timeline: list[str] = []
    probe_n = {"n": 0}

    with tempfile.TemporaryDirectory(prefix="iris-uv-probe-") as tmp:
        root = Path(tmp)
        staging = root / "staging"
        home = root / "home"
        staging.mkdir()
        home.mkdir()
        (staging / "uv.lock").write_text("# lock\n", encoding="utf-8")
        (staging / "pyproject.toml").write_text(
            '[project]\nname="hermes-agent"\nversion="0"\n',
            encoding="utf-8",
        )

        venv_scripts = staging / "venv" / ("Scripts" if sys.platform == "win32" else "bin")
        venv_py = venv_scripts / ("python.exe" if sys.platform == "win32" else "python")

        def fake_run(cmd, **kwargs):
            cmd_l = [str(c) for c in cmd]
            if len(cmd_l) >= 3 and cmd_l[1] == "-m" and cmd_l[2] == "venv":
                venv_scripts.mkdir(parents=True, exist_ok=True)
                venv_py.write_text("", encoding="utf-8")
                return _ok("venv")
            if "-e" in cmd_l:
                timeline.append("editable")
                return _ok("editable")
            return _ok()

        def fake_run_dep(cmd, **kwargs):
            cmd_l = [str(c) for c in cmd]
            if "sync" in cmd_l:
                return _ok("uv sync") if installed_via_uv else subprocess.CompletedProcess(
                    cmd_l, 1, "", "uv fail"
                )
            if "-e" in cmd_l:
                timeline.append("editable")
                return _ok("pip -e")
            return _ok()

        def fake_probe(_venv_py):
            probe_n["n"] += 1
            if probe_n["n"] == 1:
                return False, "ModuleNotFoundError: aiohttp"
            return True, "venv import ok"

        def fake_boost(venv_py_arg):
            timeline.append("boost")
            return _ok("boost")

        log: list[str] = []
        events: list[str] = []

        def fail(kind: str, message: str, detail: str = "") -> install.InstallResult:
            return install.InstallResult(False, message, kind)

        with (
            mock.patch.object(install, "_run", side_effect=fake_run),
            mock.patch.object(install, "_run_dep", side_effect=fake_run_dep),
            mock.patch.object(install, "_probe_venv", side_effect=fake_probe),
            mock.patch.object(install, "_boost_probe_deps", side_effect=fake_boost),
            mock.patch.object(install, "_activate_staged", return_value=(True, "live ok")),
            mock.patch.object(install, "_user_path_prepend"),
            mock.patch.object(install, "_wanted_extras", return_value=["mcp"]),
        ):
            result = install._finish_staged_install(
                staging=staging,
                home=home,
                stamp="test",
                py=Path(sys.executable),
                uv="uv.exe" if installed_via_uv else None,
                command="hermes",
                log=log,
                emit=events.append,
                fail=fail,
                run_streamed=None,
                should_abort=None,
                probe_gateway=False,
            )
        assert result.ok, (result, log, events, timeline)
    return timeline, events


def _check_uv_probe_miss_boosts_not_editable() -> None:
    timeline, _events = _drive_finish(installed_via_uv=True)
    assert "boost" in timeline, timeline
    # uv sync 성공 뒤에는 editable 자체가 없어야 한다 (초기·복구 모두)
    assert "editable" not in timeline, timeline
    assert timeline == ["boost"], timeline


def _check_pip_path_still_may_editable() -> None:
    """installed=False: 초기 pip -e 후 probe miss → boost → editable 복구."""
    timeline, _events = _drive_finish(installed_via_uv=False)
    assert "boost" in timeline, timeline
    boost_i = timeline.index("boost")
    assert "editable" in timeline[:boost_i], f"초기 pip -e 없음: {timeline}"
    assert "editable" in timeline[boost_i + 1 :], f"probe 복구 editable 없음: {timeline}"


def _main() -> None:
    _check_uv_probe_miss_boosts_not_editable()
    _check_pip_path_still_may_editable()
    print("ok — uv probe miss: boost only; pip path keeps editable")


if __name__ == "__main__":
    _main()
