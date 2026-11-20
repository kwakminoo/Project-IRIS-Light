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
    env = os.environ.copy()
    env.setdefault("OLLAMA_NUM_PARALLEL", "5")
    popen_kwargs["env"] = env
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
    """클라우드 로그인 UI가 있는 Ollama 데스크톱 앱 후보 (CLI ollama.exe 제외)."""
    home = Path.home()
    local = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
    base = local / "Programs" / "Ollama"
    # GUI만 — ollama.exe 는 serve/CLI라 창이 안 뜸
    return [
        base / "ollama app.exe",
        base / "Ollama.exe",
    ]


_OLLAMA_SIGNIN_URL = "https://ollama.com/signin"


def open_ollama_app() -> tuple[bool, str]:
    """Ollama GUI만 띄우고 바로 돌아온다. 서버 대기·창 제목 조회는 하지 않는다.

    실행 파일이 없으면 ``missing:`` 으로 시작한다.
    """
    cands = [p for p in ollama_app_candidates() if p.is_file()]
    if not cands:
        return False, "missing: Ollama 앱을 찾지 못했습니다 — 설치 후 다시 시도하세요"
    if sys.platform != "win32":
        try:
            subprocess.Popen([str(cands[0])], start_new_session=True, close_fds=True)  # noqa: S603
            return True, str(cands[0])
        except OSError as exc:
            return False, str(exc)[:160]
    flags = int(getattr(subprocess, "DETACHED_PROCESS", 0)) | int(
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    )
    last_err = ""
    for cand in cands:
        try:
            subprocess.Popen(  # noqa: S603
                [str(cand)],
                cwd=str(cand.parent),
                close_fds=True,
                creationflags=flags,
            )
            return True, str(cand)
        except OSError as exc:
            last_err = str(exc)[:160]
    return False, last_err or "Ollama 앱을 시작하지 못했습니다"


def begin_ollama_cloud_login() -> tuple[bool, str]:
    """로그인 버튼 공통 진입. 앱이 없으면 브라우저 signin만 연다."""
    ok, detail = open_ollama_app()
    if not ok and detail.startswith("missing"):
        import webbrowser

        webbrowser.open(_OLLAMA_SIGNIN_URL)
    return ok, detail


def _self_check_open_ollama_app() -> None:
    """후보가 있으면 Popen만 하고, 서버 대기·sleep은 하지 않는다."""
    import tempfile

    exe = Path(tempfile.mkdtemp(prefix="iris-ollama-app-")) / "ollama app.exe"
    exe.write_bytes(b"MZ")
    pops: list[tuple[list[str], dict]] = []
    saved = (ollama_app_candidates, subprocess.Popen, time.sleep, ensure_ollama_running)

    def _boom(*_a: object, **_k: object) -> None:
        raise AssertionError("login launch must not block")

    def _popen(cmd: list[str], **kw: object) -> object:
        pops.append((list(cmd), kw))

        class _Proc:
            pid = 1

        return _Proc()

    try:
        globals()["ollama_app_candidates"] = lambda: [exe]
        globals()["ensure_ollama_running"] = _boom
        time.sleep = _boom  # type: ignore[method-assign]
        subprocess.Popen = _popen  # type: ignore[method-assign]
        ok, detail = open_ollama_app()
        assert ok is True, detail
        assert len(pops) == 1
        if sys.platform == "win32":
            flags = int(pops[0][1].get("creationflags", 0))
            detached = int(getattr(subprocess, "DETACHED_PROCESS", 0))
            group = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            no_window = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
            assert flags & detached and flags & group
            assert not (flags & no_window)
        globals()["ollama_app_candidates"] = lambda: []
        ok2, detail2 = open_ollama_app()
        assert ok2 is False and detail2.startswith("missing"), detail2
    finally:
        globals()["ollama_app_candidates"] = saved[0]
        subprocess.Popen = saved[1]  # type: ignore[method-assign]
        time.sleep = saved[2]  # type: ignore[method-assign]
        globals()["ensure_ollama_running"] = saved[3]
        shutil.rmtree(exe.parent, ignore_errors=True)


def _self_check_start_ollama_server_env() -> None:
    pops: list[dict] = []
    saved_popen = subprocess.Popen
    old_parallel = os.environ.pop("OLLAMA_NUM_PARALLEL", None)

    def _popen(cmd: list[str], **kw: object) -> object:
        pops.append(dict(kw))

        class _Proc:
            pid = 1

        return _Proc()

    try:
        globals()["ollama_executable"] = lambda: "ollama"  # type: ignore[assignment]
        subprocess.Popen = _popen  # type: ignore[method-assign]
        assert start_ollama_server() is True
        assert len(pops) == 1
        env = pops[0].get("env") or {}
        assert env.get("OLLAMA_NUM_PARALLEL") == "5"
        if sys.platform == "win32":
            flags = int(pops[0].get("creationflags", 0))
            no_window = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
            assert flags & no_window
    finally:
        globals()["ollama_executable"] = ollama_executable
        subprocess.Popen = saved_popen  # type: ignore[method-assign]
        if old_parallel is not None:
            os.environ["OLLAMA_NUM_PARALLEL"] = old_parallel


if __name__ == "__main__":
    base = "http://127.0.0.1:11434/v1"
    assert is_ollama_running(base) in (True, False)
    # 잘못된 포트는 반드시 꺼짐으로 감지되어야 함
    assert is_ollama_running("http://127.0.0.1:1/v1", timeout_sec=1.0) is False
    assert isinstance(ollama_app_candidates(), list)
    _self_check_open_ollama_app()
    _self_check_start_ollama_server_env()
    print("ollama_server ok - running:", is_ollama_running(base))
