"""로컬 Ollama 서버 감지 및 자동 기동."""

from __future__ import annotations

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


if __name__ == "__main__":
    base = "http://127.0.0.1:11434/v1"
    assert is_ollama_running(base) in (True, False)
    # 잘못된 포트는 반드시 꺼짐으로 감지되어야 함
    assert is_ollama_running("http://127.0.0.1:1/v1", timeout_sec=1.0) is False
    print("ollama_server ok - running:", is_ollama_running(base))
