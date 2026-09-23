"""Hermes Windows 설치 우회 — uv managed Python junction(WinError 448) 회피.

공식 install.ps1 은 시스템 Python을 거부하고 checkout 전용 uv managed
interpreter 만 받는다. OneDrive/필터 등으로 minor-version junction 생성이
실패하면(os error 448) 설치가 멈춘다.

우회: git HTTPS clone + (Iris/.venv 또는 시스템) Python 으로 venv 생성 후
pip install -e .
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from iris.system import hermes_gateway as gw

HERMES_REPO_HTTPS = "https://github.com/NousResearch/hermes-agent.git"
StreamFn = Callable[[str], None]

_UV_MOUNT_MARKERS = (
    "os error 448",
    "error 448",
    "신뢰할 수 없는 탑재",
    "untrusted mount",
    "failed to create python minor version link",
    "python 3.11 not available",
    "failed to install python 3.11",
)


def looks_like_uv_python_mount_failure(text: str) -> bool:
    t = (text or "").lower()
    if not t:
        return False
    return any(m in t for m in _UV_MOUNT_MARKERS)


def _no_window() -> dict:
    if sys.platform != "win32":
        return {}
    return {"creationflags": int(getattr(subprocess, "CREATE_NO_WINDOW", 0))}


def _run(
    cmd: list[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 600.0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        **_no_window(),
    )


def find_bootstrap_python() -> Path | None:
    """Hermes venv를 만들 베이스 인터프리터 — Iris .venv 우선, 그다음 py launcher."""
    try:
        from iris.system.hermes_iris_control_sync import project_root

        root = project_root()
    except Exception:  # noqa: BLE001
        root = Path.cwd()
    for cand in (
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    ):
        if cand.is_file():
            return cand
    if sys.platform == "win32":
        py = shutil.which("py")
        if py:
            for flag in ("-3.11", "-3.12", "-3.13", "-3.10", "-3"):
                try:
                    proc = _run([py, flag, "-c", "import sys; print(sys.executable)"], timeout=20)
                except (OSError, subprocess.TimeoutExpired):
                    continue
                line = (proc.stdout or "").strip().splitlines()
                if proc.returncode == 0 and line:
                    p = Path(line[-1].strip())
                    if p.is_file():
                        return p
    for name in ("python3.11", "python3.12", "python3", "python"):
        found = shutil.which(name)
        if found:
            return Path(found)
    if sys.executable:
        p = Path(sys.executable)
        if p.is_file():
            return p
    return None


def ensure_system_python_winget(
    *,
    run_streamed: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    on_stream: StreamFn | None = None,
) -> Path | None:
    """winget 으로 Python 3.11 설치 시도. 이미 있으면 find_bootstrap_python."""
    existing = find_bootstrap_python()
    if existing is not None:
        return existing
    if sys.platform != "win32":
        return None
    winget = shutil.which("winget")
    if not winget:
        local = os.environ.get("LOCALAPPDATA", "")
        cand = Path(local) / "Microsoft" / "WindowsApps" / "winget.exe"
        winget = str(cand) if cand.is_file() else None
    if not winget:
        return None
    if on_stream:
        on_stream("시스템 Python 3.11 설치 (winget)…")
    cmd = [
        winget,
        "install",
        "-e",
        "--id",
        "Python.Python.3.11",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]
    try:
        if run_streamed is not None:
            run_streamed(cmd, timeout=900.0, hard_timeout=1800.0, hidden=False)
        else:
            _run(cmd, timeout=1800.0)
    except (OSError, subprocess.TimeoutExpired):
        pass
    # PATH refresh for this process
    user = os.environ.get("PATH", "")
    machine = ""
    try:
        import winreg  # type: ignore

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Environment"
        ) as key:
            user, _ = winreg.QueryValueEx(key, "Path")
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ) as key:
            machine, _ = winreg.QueryValueEx(key, "Path")
    except OSError:
        pass
    if user or machine:
        os.environ["PATH"] = f"{user};{machine}"
    return find_bootstrap_python()


def _kill_hermes_tree_holders(agent: Path) -> None:
    if sys.platform != "win32" or not agent.is_dir():
        return
    prefix = str(agent.resolve()).lower()
    try:
        import psutil  # type: ignore
    except ImportError:
        # taskkill by image — best effort
        flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for image in ("hermes.exe", "python.exe", "pythonw.exe"):
            subprocess.run(
                ["taskkill", "/F", "/T", "/IM", image],
                capture_output=True,
                creationflags=flags,
                timeout=8,
                check=False,
            )
        return
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            exe = (proc.info.get("exe") or "") or ""
            if exe and exe.lower().startswith(prefix):
                proc.kill()
        except (psutil.Error, OSError):
            continue
    time.sleep(0.4)


def force_retire_hermes_agent(*, command: str = "hermes") -> str:
    """잠긴 hermes-agent / .broken-* 를 rename 으로 치우고 삭제 시도."""
    home = gw.hermes_home()
    home.mkdir(parents=True, exist_ok=True)
    try:
        gw.stop_hermes_gateway(command, wait_sec=6.0)
    except Exception:  # noqa: BLE001
        pass

    notes: list[str] = []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    targets = [home / "hermes-agent"]
    try:
        targets.extend(
            sorted(
                p
                for p in home.iterdir()
                if p.is_dir()
                and (
                    p.name.startswith("hermes-agent.broken-")
                    or p.name.startswith("hermes-agent.trash-")
                )
            )
        )
    except OSError:
        pass

    for path in targets:
        if not path.exists():
            continue
        _kill_hermes_tree_holders(path)
        trash = home / f"hermes-agent.trash-{stamp}-{path.name[-8:]}"
        try:
            path.rename(trash)
            notes.append(f"치움→{trash.name}")
            path = trash
        except OSError as exc:
            notes.append(f"rename 실패({exc})")
        try:
            shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass
        if path.exists():
            # robocopy mirror empty — Windows 잠금 파일 우회에 자주 통함
            empty = home / f".empty-wipe-{stamp}"
            try:
                empty.mkdir(exist_ok=True)
                subprocess.run(
                    [
                        "cmd",
                        "/c",
                        "robocopy",
                        str(empty),
                        str(path),
                        "/MIR",
                        "/NFL",
                        "/NDL",
                        "/NJH",
                        "/NJS",
                        "/nc",
                        "/ns",
                        "/np",
                    ],
                    capture_output=True,
                    timeout=120,
                    check=False,
                    **_no_window(),
                )
                shutil.rmtree(empty, ignore_errors=True)
                shutil.rmtree(path, ignore_errors=True)
            except (OSError, subprocess.TimeoutExpired):
                pass
        if path.exists():
            notes.append(f"잔존:{path.name}")
        else:
            notes.append(f"삭제:{path.name}")

    # 오래된 trash 최대 3개만 남기고 정리 시도
    try:
        trashes = sorted(
            p for p in home.iterdir() if p.is_dir() and p.name.startswith("hermes-agent.trash-")
        )
        for old in trashes[:-3]:
            shutil.rmtree(old, ignore_errors=True)
    except OSError:
        pass
    return "; ".join(notes) if notes else "정리할 hermes-agent 없음"


def _user_path_prepend(scripts: Path) -> None:
    if sys.platform != "win32" or not scripts.is_dir():
        return
    s = str(scripts)
    try:
        import winreg  # type: ignore

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ | winreg.KEY_SET_VALUE
        ) as key:
            try:
                cur, typ = winreg.QueryValueEx(key, "Path")
            except OSError:
                cur, typ = "", winreg.REG_EXPAND_SZ
            parts = [p for p in str(cur).split(";") if p]
            if not any(p.lower() == s.lower() for p in parts):
                winreg.SetValueEx(key, "Path", 0, typ, s + ";" + str(cur))
    except OSError:
        pass
    path = os.environ.get("PATH", "")
    if s.lower() not in path.lower():
        os.environ["PATH"] = s + os.pathsep + path


def install_hermes_with_system_python(
    *,
    command: str = "hermes",
    on_stream: StreamFn | None = None,
    run_streamed: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    should_abort: Callable[[], bool] | None = None,
) -> tuple[bool, str]:
    """공식 스크립트 대신 clone+venv+pip 로 Hermes 설치."""

    def _emit(msg: str) -> None:
        if on_stream:
            on_stream(msg)

    if should_abort and should_abort():
        return False, "사용자가 중단함"

    py = ensure_system_python_winget(run_streamed=run_streamed, on_stream=on_stream)
    if py is None:
        return False, "베이스 Python을 찾지 못했습니다 (Iris .venv / winget Python.Python.3.11)"

    _emit(f"우회 설치: 베이스 Python = {py}")
    wipe = force_retire_hermes_agent(command=command)
    _emit(f"런타임 정리: {wipe}")

    home = gw.hermes_home()
    agent = home / "hermes-agent"
    home.mkdir(parents=True, exist_ok=True)
    git = shutil.which("git")
    if not git:
        return False, "git 이 없습니다"

    if should_abort and should_abort():
        return False, "사용자가 중단함"

    _emit("Hermes 저장소 HTTPS clone…")
    clone = _run(
        [git, "-c", "core.longpaths=true", "clone", "--depth", "1", HERMES_REPO_HTTPS, str(agent)],
        timeout=600.0,
    )
    if clone.returncode != 0 or not agent.is_dir():
        err = ((clone.stderr or "") + (clone.stdout or ""))[:400]
        return False, f"git clone 실패: {err}"

    venv_dir = agent / "venv"
    _emit("venv 생성 (시스템/Iris Python, uv managed 없음)…")
    venv_proc = _run([str(py), "-m", "venv", str(venv_dir)], timeout=180.0)
    if venv_proc.returncode != 0:
        return False, f"venv 실패: {(venv_proc.stderr or venv_proc.stdout or '')[:300]}"

    venv_py = venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not venv_py.is_file():
        return False, f"venv python 없음: {venv_py}"

    if should_abort and should_abort():
        return False, "사용자가 중단함"

    _emit("pip 업그레이드…")
    _run([str(venv_py), "-m", "pip", "install", "-U", "pip", "wheel", "setuptools"], timeout=300.0)

    _emit("Hermes 패키지 설치 (pip install -e .)…")
    # 긴 설치 — 스트림 가능하면 사용
    pip_cmd = [str(venv_py), "-m", "pip", "install", "-e", "."]
    try:
        if run_streamed is not None:
            pip = run_streamed(pip_cmd, cwd=str(agent), timeout=900.0, hard_timeout=2400.0, hidden=True)
        else:
            pip = _run(pip_cmd, cwd=str(agent), timeout=2400.0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"pip 설치 중단: {exc}"

    if pip.returncode != 0:
        # pyproject extras / uv.lock 프로젝트일 수 있음 — requirements 폴백
        req = agent / "requirements.txt"
        if req.is_file():
            _emit("pip -e 실패 — requirements.txt 폴백…")
            if run_streamed is not None:
                pip = run_streamed(
                    [str(venv_py), "-m", "pip", "install", "-r", str(req)],
                    cwd=str(agent),
                    timeout=900.0,
                    hard_timeout=2400.0,
                    hidden=True,
                )
            else:
                pip = _run(
                    [str(venv_py), "-m", "pip", "install", "-r", str(req)],
                    cwd=str(agent),
                    timeout=2400.0,
                )
        if pip.returncode != 0:
            err = ((getattr(pip, "stderr", None) or "") + (getattr(pip, "stdout", None) or ""))[:400]
            return False, f"pip 설치 실패: {err}"

    scripts = venv_dir / ("Scripts" if sys.platform == "win32" else "bin")
    _user_path_prepend(scripts)

    # hermes 엔트리 확인 — console_scripts 또는 -m
    hermes_exe = scripts / ("hermes.exe" if sys.platform == "win32" else "hermes")
    if not hermes_exe.is_file():
        # module 진입만 있어도 gateway는 venv python -m hermes_cli.main 으로 동작
        check = _run(
            [str(venv_py), "-c", "import hermes_cli"],
            timeout=60.0,
        )
        if check.returncode != 0:
            return False, "hermes_cli import 실패 — 패키지 설치 불완전"

    ok, detail = gw.probe_hermes_runtime(command=command, timeout_sec=30.0)
    if ok:
        return True, f"우회 설치 성공 ({detail})"
    # probe 가 exe 없으면 venv python 기준이라도 import 통과 시 성공으로 본다
    if (scripts / "python.exe").is_file() or (scripts / "python").is_file():
        check = _run([str(venv_py), "-c", "import hermes_cli; print('ok')"], timeout=60.0)
        if check.returncode == 0 and "ok" in (check.stdout or ""):
            return True, f"우회 설치 성공 (venv import ok; probe={detail})"
    return False, f"우회 설치 후 런타임 실패: {detail}"


_OUT_TAIL_RE = re.compile(r".{0,200}$", re.DOTALL)


def combined_install_log_tail(*parts: str, limit: int = 1200) -> str:
    blob = "\n".join(p for p in parts if p)
    if len(blob) <= limit:
        return blob
    return blob[-limit:]


if __name__ == "__main__":
    assert looks_like_uv_python_mount_failure(
        "Failed to create Python minor version link directory\n"
        "cause: 경로에 신뢰할 수 없는 탑재 지점이 포함되어 있습니다. (os error 448)"
    )
    assert looks_like_uv_python_mount_failure("Python 3.11 not available")
    assert not looks_like_uv_python_mount_failure("connection refused")
    print("hermes_install helpers ok", find_bootstrap_python())
