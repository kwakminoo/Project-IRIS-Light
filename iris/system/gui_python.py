"""GUI 기동용 Python — venv Scripts\\pythonw 스텁을 건너뛴다.

Windows venv의 Scripts\\pythonw.exe 는 CreateProcess 후 자식(실제 pythonw)을
기다리며 남는다. 둘 다 cmdline 이 `-m iris` 로 보여 Hermes/제어 경로가
스텁 PID 를 집으면 done 이 채팅 UI 에 안 붙는다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _parse_venv_home(venv: Path) -> Path | None:
    cfg = venv / "pyvenv.cfg"
    if not cfg.is_file():
        return None
    try:
        for line in cfg.read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("home"):
                _, _, value = line.partition("=")
                home = Path(value.strip())
                if home.is_dir():
                    return home
    except OSError:
        return None
    return None


def venv_scripts_pythonw(root: Path) -> Path | None:
    path = root / ".venv" / "Scripts" / "pythonw.exe"
    return path if path.is_file() else None


def base_pythonw(root: Path) -> Path | None:
    """pyvenv.cfg home 의 pythonw — 스텁이 아닌 실제 인터프리터."""
    home = _parse_venv_home(root / ".venv")
    if home is None:
        return None
    path = home / "pythonw.exe"
    return path if path.is_file() else None


def gui_launch_env(root: Path, *, base: dict[str, str] | None = None) -> dict[str, str]:
    """base pythonw 로도 venv site-packages 를 쓰게 하는 환경."""
    env = dict(base if base is not None else os.environ)
    venv = root / ".venv"
    launcher = venv_scripts_pythonw(root)
    if venv.is_dir():
        env["VIRTUAL_ENV"] = str(venv.resolve())
        scripts = venv / "Scripts"
        if scripts.is_dir():
            env["PATH"] = str(scripts.resolve()) + os.pathsep + env.get("PATH", "")
    if launcher is not None:
        env["__PYVENV_LAUNCHER__"] = str(launcher.resolve())
    return env


def resolve_gui_pythonw(root: Path) -> Path:
    """GUI 스폰에 쓸 pythonw. 가능하면 base, 없으면 venv 스텁."""
    base = base_pythonw(root)
    if base is not None:
        return base
    stub = venv_scripts_pythonw(root)
    if stub is not None:
        return stub
    sibling = Path(sys.executable).with_name("pythonw.exe")
    if sibling.is_file():
        return sibling
    return Path(sys.executable)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    exe = resolve_gui_pythonw(root)
    stub = venv_scripts_pythonw(root)
    assert exe.is_file(), exe
    if stub is not None and base_pythonw(root) is not None:
        assert exe.resolve() != stub.resolve(), (exe, stub)
    env = gui_launch_env(root)
    assert env.get("VIRTUAL_ENV")
    assert env.get("__PYVENV_LAUNCHER__")
    print("gui_python ok", exe)
