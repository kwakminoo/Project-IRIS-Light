"""uv sync 성공 후 editable pip 금지 (현재 _finish_staged_install API).

Owned finish 경로는 uv sync → _probe_owned_slot → activate 만 탄다.
pip install -e 는 이 경로에 없다. (engine-uv-probe-boost 계약 유지·강화)

python -m iris.system._check_uv_probe_boost_no_editable
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest import mock

from iris.system import iris_agent_install as m
from iris.system.iris_agent_install import InstallResult


def _ok(cmd=None, stdout="", stderr=""):
    return subprocess.CompletedProcess(list(cmd or ["x"]), 0, stdout, stderr)


def _fail(kind: str, msg: str, body: str = "") -> InstallResult:
    return InstallResult(False, msg, kind)


def _track_editable(cmd, editable: list[list[str]]) -> None:
    argv = [str(c) for c in cmd]
    if "-m" in argv and "pip" in argv and "install" in argv and "-e" in argv:
        editable.append(argv)


def _drive_finish(
    *,
    staging: Path,
    home: Path,
    py: Path,
    uv: str | None,
    editable: list[list[str]],
    probe_ok: bool = True,
) -> InstallResult:
    def fake_run_dep(cmd, **kw):
        _track_editable(cmd, editable)
        return _ok(cmd, stdout="ok")

    def fake_run(cmd, **kw):
        _track_editable(cmd, editable)
        return _ok(cmd, stdout="ok")

    log: list[str] = []
    with (
        mock.patch.object(m, "_run", side_effect=fake_run),
        mock.patch.object(m, "_run_dep", side_effect=fake_run_dep),
        mock.patch.object(
            m,
            "_probe_owned_slot",
            return_value=(True, "slot ok") if probe_ok else (False, "ModuleNotFoundError: aiohttp"),
        ),
        mock.patch.object(m, "_activate_staged", return_value=(True, "activated")),
        mock.patch.object(m, "_wanted_extras", return_value=()),
    ):
        return m._finish_staged_install(
            staging=staging,
            home=home,
            py=py,
            uv=uv,
            log=log,
            emit=lambda _s: None,
            fail=_fail,
            run_streamed=None,
            should_abort=None,
        )


def _check_uv_sync_ok_never_editable() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-uv-probe-") as tmp:
        root = Path(tmp)
        home = root / "home"
        staging = root / "staging"
        home.mkdir()
        staging.mkdir()
        (staging / "uv.lock").write_text("# lock\n", encoding="utf-8")
        py = root / "python.exe"
        py.write_bytes(b"x" * 2048)

        editable: list[list[str]] = []
        result = _drive_finish(
            staging=staging,
            home=home,
            py=py,
            uv="uv",
            editable=editable,
            probe_ok=True,
        )
        assert result.ok, result
        assert editable == [], editable


def _check_uv_sync_probe_miss_skips_editable() -> None:
    """uv sync 성공 + probe miss → fail(probe), pip -e 금지."""
    with tempfile.TemporaryDirectory(prefix="iris-uv-probe-miss-") as tmp:
        root = Path(tmp)
        home = root / "home"
        staging = root / "staging"
        home.mkdir()
        staging.mkdir()
        (staging / "uv.lock").write_text("# lock\n", encoding="utf-8")
        py = root / "python.exe"
        py.write_bytes(b"x" * 2048)

        editable: list[list[str]] = []
        result = _drive_finish(
            staging=staging,
            home=home,
            py=py,
            uv="uv",
            editable=editable,
            probe_ok=False,
        )
        assert not result.ok, result
        assert result.kind == "probe", result
        assert editable == [], editable


def _check_no_uv_rejects_without_editable() -> None:
    """uv/lock 없으면 lock fail. pip -e 폴백 없음 (계약 강화)."""
    with tempfile.TemporaryDirectory(prefix="iris-no-uv-") as tmp:
        root = Path(tmp)
        home = root / "home"
        staging = root / "staging"
        home.mkdir()
        staging.mkdir()
        py = root / "python.exe"
        py.write_bytes(b"x" * 2048)

        editable: list[list[str]] = []
        result = _drive_finish(
            staging=staging,
            home=home,
            py=py,
            uv=None,
            editable=editable,
            probe_ok=True,
        )
        assert not result.ok, result
        assert result.kind == "lock", result
        assert editable == [], editable


def _main() -> None:
    _check_uv_sync_ok_never_editable()
    _check_uv_sync_probe_miss_skips_editable()
    _check_no_uv_rejects_without_editable()
    print("ok")


if __name__ == "__main__":
    _main()
