"""로컬 Ollama 서버 감지 및 자동 기동."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from iris.infrastructure.ollama_client import _native_base

_WINDOWS_DEFAULT = Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe"


def is_ollama_running(base_url: str, *, timeout_sec: float = 2.0) -> bool:
    """서버가 응답하면 True. HTTP 401/403 등도 '켜짐'으로 간주(응답했으므로)."""
    url = f"{_native_base(base_url)}/api/version"
    try:
        with urlopen(Request(url, method="GET"), timeout=timeout_sec):
            return True
    except HTTPError:
        return True
    except (URLError, TimeoutError, OSError):
        return False


def ollama_executable() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    if sys.platform == "win32" and _WINDOWS_DEFAULT.is_file():
        return str(_WINDOWS_DEFAULT)
    return None


def start_ollama_server() -> bool:
    """`ollama serve`를 백그라운드로 기동. 실행 파일이 없으면 False."""
    exe = ollama_executable()
    if not exe:
        return False
    popen_kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        # 콘솔 창 없이 백그라운드 — CREATE_NO_WINDOW만 (DETACHED와 섞지 않음)
        creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        creationflags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        popen_kwargs["creationflags"] = creationflags
        popen_kwargs["startupinfo"] = startupinfo
    else:
        popen_kwargs["start_new_session"] = True
    try:
        subprocess.Popen([exe, "serve"], **popen_kwargs)
        return True
    except OSError:
        return False


def ensure_ollama_running(base_url: str, *, wait_sec: float = 12.0) -> bool:
    """켜져 있으면 즉시 True. 아니면 기동 후 준비될 때까지 대기."""
    if is_ollama_running(base_url):
        return True
    if not start_ollama_server():
        return False
    deadline = time.monotonic() + wait_sec
    while time.monotonic() < deadline:
        if is_ollama_running(base_url):
            return True
        time.sleep(0.5)
    return False


def ollama_app_candidates() -> list[Path]:
    """클라우드 로그인 UI가 있는 Ollama 데스크톱 앱 후보."""
    home = Path.home()
    local = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
    base = local / "Programs" / "Ollama"
    return [
        base / "ollama app.exe",
        base / "Ollama.exe",
        base / "ollama.exe",
        _WINDOWS_DEFAULT,
    ]


def open_ollama_app() -> tuple[bool, str]:
    """Ollama 데스크톱 앱을 연다 (serve만으로는 로그인 UI가 안 뜸).

    Returns: (ok, detail) — detail은 UI 힌트용, 시크릿 없음.
    """
    if sys.platform != "win32":
        exe = ollama_executable()
        if not exe:
            return False, "ollama 실행 파일을 찾지 못했습니다"
        try:
            subprocess.Popen([exe], start_new_session=True)  # noqa: S603
            return True, exe
        except OSError as exc:
            return False, str(exc)[:160]

    for cand in ollama_app_candidates():
        if not cand.is_file():
            continue
        try:
            # GUI — CREATE_NO_WINDOW 금지 (로그인 창이 떠야 함)
            os.startfile(str(cand))  # type: ignore[attr-defined]
            return True, str(cand)
        except OSError:
            try:
                subprocess.Popen([str(cand)], close_fds=True)  # noqa: S603
                return True, str(cand)
            except OSError as exc:
                return False, str(exc)[:160]
    return False, "Ollama 앱을 찾지 못했습니다 — 설치 후 다시 시도하세요"


if __name__ == "__main__":
    base = "http://127.0.0.1:11434/v1"
    assert is_ollama_running(base) in (True, False)
    # 잘못된 포트는 반드시 꺼짐으로 감지되어야 함
    assert is_ollama_running("http://127.0.0.1:1/v1", timeout_sec=1.0) is False
    assert isinstance(ollama_app_candidates(), list)
    print("ollama_server ok - running:", is_ollama_running(base))
