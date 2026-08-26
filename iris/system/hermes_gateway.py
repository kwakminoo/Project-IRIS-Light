"""Hermes gateway 감지 및 자동 기동."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from iris.infrastructure.hermes_client import HermesClient
from iris.infrastructure.hermes_credentials import (
    hermes_home,
    load_hermes_dotenv,
    resolve_hermes_api_key,
)


def _windows_hermes_candidates() -> list[Path]:
    root = hermes_home() / "hermes-agent" / "venv" / "Scripts"
    return [root / "hermes.exe", root / "hermes-agent.exe"]


def hermes_executable(command: str = "hermes") -> str | None:
    """PATH·설정 경로·Windows 기본 설치 위치에서 hermes 실행 파일 찾기."""
    cmd = (command or "hermes").strip() or "hermes"
    as_path = Path(cmd)
    if as_path.is_file():
        return str(as_path)
    found = shutil.which(cmd)
    if found:
        return found
    if sys.platform == "win32":
        for candidate in _windows_hermes_candidates():
            if candidate.is_file():
                return str(candidate)
    return None


def is_hermes_gateway_running(
    base_url: str,
    *,
    api_key: str = "",
) -> bool:
    return HermesClient(
        base_url,
        api_key=resolve_hermes_api_key(api_key),
    ).gateway_ready()


def _hermes_agent_dir() -> Path:
    return hermes_home() / "hermes-agent"


def _hermes_venv_dir() -> Path:
    return _hermes_agent_dir() / "venv"


def _hermes_venv_python() -> Path | None:
    """Hermes 전용 venv python — uv trampoline 오염 회피용."""
    if sys.platform == "win32":
        py = _hermes_venv_dir() / "Scripts" / "python.exe"
    else:
        py = _hermes_venv_dir() / "bin" / "python"
    return py if py.is_file() else None


def _gateway_argv() -> list[str]:
    # 신규 기동 — stop 후 start 경로를 쓰므로 --replace에 의존하지 않음
    return ["gateway", "run", "--quiet", "--accept-hooks"]


def _gateway_child_env() -> dict[str, str]:
    """Hermes gateway 자식 프로세스 환경 — .env + HERMES_HOME 필수.

    Iris (.venv) VIRTUAL_ENV/PYTHONPATH 를 그대로 넘기면 uv hermes.exe 가
    패키지 없는 base Python 으로 re-exec 되어
    ``No module named 'pydantic_core._pydantic_core'`` 가 난다.
    """
    env = os.environ.copy()
    home = hermes_home()
    env["HERMES_HOME"] = str(home)
    env["HERMES_ACCEPT_HOOKS"] = "1"
    for key, val in load_hermes_dotenv().items():
        # Iris 프로세스 값이 있어도 Hermes 전용 키는 파일 값을 쓴다
        env[key] = val
    env.setdefault("API_SERVER_ENABLED", "true")

    venv = _hermes_venv_dir()
    venv_py = _hermes_venv_python()
    if venv.is_dir() and venv_py is not None:
        env["VIRTUAL_ENV"] = str(venv)
        scripts = str(venv / ("Scripts" if sys.platform == "win32" else "bin"))
        path = env.get("PATH", "")
        if scripts and not path.lower().startswith(scripts.lower()):
            env["PATH"] = scripts + os.pathsep + path
        for k in (
            "PYTHONHOME",
            "PYTHONPATH",
            "PYTHONEXECUTABLE",
            "UV_PROJECT",
            "UV_PROJECT_ENVIRONMENT",
            "UV_PYTHON",
            "UV_PYTHON_PREFERENCE",
            "CONDA_PREFIX",
            "CONDA_DEFAULT_ENV",
        ):
            env.pop(k, None)
    return env


def _windows_hidden_cmd(hermes_exe: str) -> list[str]:
    """콘솔 창 없이 기동.

    venv python -m hermes_cli.main 우선 — hermes.exe(uv trampoline)만 쓰면
    Iris VIRTUAL_ENV 오염 시 base Python 으로 re-exec 되어 pydantic_core 가 빠진다.
    """
    venv_py = _hermes_venv_python()
    if venv_py is not None:
        return [str(venv_py), "-m", "hermes_cli.main", *_gateway_argv()]
    return [hermes_exe, *_gateway_argv()]


def _popen_hidden(
    cmd: list[str],
    *,
    env: dict[str, str],
    cwd: str | None = None,
) -> subprocess.Popen[bytes]:
    popen_kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "env": env,
        "close_fds": True,
    }
    if cwd:
        popen_kwargs["cwd"] = cwd
    if sys.platform == "win32":
        # CREATE_NEW_PROCESS_GROUP은 Hermes gateway가 수 초 내 종료되는 원인이 됨
        # (자식/런타임 락과 충돌). CREATE_NO_WINDOW만 사용.
        creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        popen_kwargs["creationflags"] = creationflags
        popen_kwargs["startupinfo"] = startupinfo
    else:
        popen_kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **popen_kwargs)


def start_hermes_gateway(command: str = "hermes") -> bool:
    """`hermes gateway run`을 창 없이 백그라운드로 기동. 실행 파일이 없으면 False."""
    exe = hermes_executable(command)
    if not exe and _hermes_venv_python() is None:
        return False
    env = _gateway_child_env()
    cwd = str(_hermes_agent_dir())
    if not Path(cwd).is_dir():
        cwd = None
    try:
        if sys.platform == "win32":
            _popen_hidden(_windows_hidden_cmd(exe or "hermes"), env=env, cwd=cwd)
        else:
            venv_py = _hermes_venv_python()
            if venv_py is not None:
                _popen_hidden(
                    [str(venv_py), "-m", "hermes_cli.main", *_gateway_argv()],
                    env=env,
                    cwd=cwd,
                )
            else:
                _popen_hidden([exe or "hermes", *_gateway_argv()], env=env, cwd=cwd)
        return True
    except OSError:
        return False


def stop_hermes_gateway(command: str = "hermes", *, wait_sec: float = 20.0) -> bool:
    """`hermes gateway stop --all`로 락을 잡고 있는 구 프로세스를 내린다.

    ponytail: `--replace`만으로는 Windows에서 lock 보유 인스턴스가 남을 수 있음.
    천장: CLI stop 실패 시 taskkill + stale gateway.lock 제거.
    """
    exe = hermes_executable(command)
    if exe:
        try:
            subprocess.run(
                [exe, "gateway", "stop", "--all"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=45,
                check=False,
                env=_gateway_child_env(),
                creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if sys.platform == "win32"
                else 0,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

    _force_kill_windows_gateway_procs()
    _clear_stale_gateway_lock()

    deadline = time.monotonic() + wait_sec
    while time.monotonic() < deadline:
        if not _windows_gateway_procs_alive() and not _lock_pid_alive():
            _clear_stale_gateway_lock()
            return True
        time.sleep(0.35)
    _clear_stale_gateway_lock()
    return not _windows_gateway_procs_alive()


def _gateway_lock_path() -> Path:
    return hermes_home() / "gateway.lock"


def _lock_pid_alive() -> bool:
    path = _gateway_lock_path()
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        pid = int(data.get("pid") or 0)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    if pid <= 0:
        return False
    return _pid_exists(pid)


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                text=True,
                timeout=10,
                creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return str(pid) in (out or "")
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _clear_stale_gateway_lock() -> None:
    """죽은 PID가 남긴 gateway.lock / gateway.pid / kanban lock 제거.

    Hermes는 gateway.pid를 O_CREAT|O_EXCL로 만들므로, 죽은 프로세스의 pid
    파일이 남으면 새 기동이 FileExistsError로 즉시 종료한다(exit 계열).
    """
    home = hermes_home()
    pid_path = home / "gateway.pid"
    lock_path = home / "gateway.lock"

    # pid 파일 — 기록된 PID가 없거나 죽었어야 삭제
    if pid_path.is_file():
        stale = True
        try:
            data = json.loads(pid_path.read_text(encoding="utf-8"))
            pid = int(data.get("pid") or 0)
            if pid > 0 and _pid_exists(pid):
                stale = False
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            stale = True
        if stale:
            try:
                pid_path.unlink()
            except OSError:
                pass

    if lock_path.is_file() and not _lock_pid_alive():
        try:
            lock_path.unlink()
        except OSError:
            pass

    # kanban dispatcher stale lock
    klock = home / "kanban" / ".dispatcher.lock"
    if klock.is_file():
        try:
            raw = klock.read_text(encoding="utf-8", errors="replace").strip()
            kpid = int(raw) if raw.isdigit() else 0
        except (OSError, ValueError):
            kpid = 0
        if (not kpid) or (not _pid_exists(kpid)):
            try:
                klock.unlink()
            except OSError:
                pass


def _gateway_process_pids() -> list[int]:
    """Hermes gateway 프로세스 PID.

    ponytail: Win32_Process 전체 스캔(PowerShell CIM)은 환경에 따라 수 초~무한 대기에
    가깝게 느려질 수 있음 → gateway.lock PID + psutil(있으면)만 사용.
    """
    pids: set[int] = set()

    lock = _gateway_lock_path()
    if lock.is_file():
        try:
            data = json.loads(lock.read_text(encoding="utf-8"))
            pid = int(data.get("pid") or 0)
            if pid > 0 and _pid_exists(pid):
                pids.add(pid)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    try:
        import psutil  # type: ignore
    except Exception:
        return sorted(pids)

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            cmdline_list = proc.info.get("cmdline") or []
            cmdline = " ".join(cmdline_list).lower()
            if " -m iris" in cmdline or "iris_launcher" in cmdline:
                continue
            looks_hermes = (
                name.startswith("hermes")
                or "hermes_cli.main" in cmdline
                or "\\hermes" in cmdline
                or "/hermes" in cmdline
            )
            if looks_hermes and "gateway" in cmdline and "run" in cmdline:
                pids.add(int(proc.info["pid"]))
        except (psutil.Error, TypeError, ValueError):
            continue
    return sorted(pids)


def _windows_gateway_procs_alive() -> bool:
    return bool(_gateway_process_pids())


def _force_kill_windows_gateway_procs() -> None:
    me = os.getpid()
    if sys.platform != "win32":
        import signal

        for pid in _gateway_process_pids():
            if pid == me:
                continue
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and _gateway_process_pids():
            time.sleep(0.2)
        for pid in _gateway_process_pids():
            if pid == me:
                continue
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        return
    for pid in _gateway_process_pids():
        if pid == me:
            continue
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
                creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


def ensure_hermes_gateway_running(
    base_url: str,
    *,
    api_key: str = "",
    command: str = "hermes",
    wait_sec: float = 45.0,
) -> bool:
    """켜져 있으면 즉시 True. 아니면 기동 후 /health 준비까지 대기."""
    key = resolve_hermes_api_key(api_key)
    if is_hermes_gateway_running(base_url, api_key=key):
        return True
    # 좀비 프로세스/락만 있으면 정리 후 재기동
    if _windows_gateway_procs_alive() or _gateway_lock_path().is_file():
        stop_hermes_gateway(command, wait_sec=min(15.0, wait_sec / 2))
        if is_hermes_gateway_running(base_url, api_key=key):
            return True
    if not start_hermes_gateway(command):
        return False
    deadline = time.monotonic() + wait_sec
    while time.monotonic() < deadline:
        if is_hermes_gateway_running(base_url, api_key=key):
            return True
        time.sleep(0.5)
    return False


def restart_hermes_gateway(
    base_url: str,
    *,
    api_key: str = "",
    command: str = "hermes",
    wait_sec: float = 60.0,
) -> bool:
    """구 gateway를 완전히 내리고 새로 기동 — MCP 서브프로세스를 다시 붙인다.

    `--replace`만 쓰면 Windows에서 'runtime lock already held'로 신 프로세스가
    죽고, 오전부터 떠 있던 구 gateway(MCP 0 tools)가 그대로 남는 문제가 있었다.
    """
    key = resolve_hermes_api_key(api_key)
    stop_hermes_gateway(command, wait_sec=min(20.0, wait_sec / 2))

    # health가 내려갈 때까지 대기
    down_deadline = time.monotonic() + 15.0
    while time.monotonic() < down_deadline:
        if not is_hermes_gateway_running(base_url, api_key=key):
            break
        time.sleep(0.3)

    _clear_stale_gateway_lock()
    if not start_hermes_gateway(command):
        return False

    deadline = time.monotonic() + wait_sec
    while time.monotonic() < deadline:
        if is_hermes_gateway_running(base_url, api_key=key):
            return True
        time.sleep(0.5)
    return False


def verify_iris_mcp_tools(*, command: str = "hermes", timeout_sec: float = 45.0) -> tuple[bool, str]:
    """게이트웨이 밖에서도 MCP stdio 핸드셰이크가 되는지만 확인 (설정 유지 검증)."""
    exe = hermes_executable(command)
    if not exe:
        return False, "hermes executable missing"
    try:
        proc = subprocess.run(
            [exe, "mcp", "test", "iris-control"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
            env=_gateway_child_env(),
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if sys.platform == "win32"
            else 0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"mcp test failed: {exc}"
    out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    ok = proc.returncode == 0 and ("Connected" in out or "Tools discovered" in out)
    if ok and "iris_invoke" in out:
        return True, "iris-control tools ok (iris_get_state/catalog/invoke)"
    if ok:
        return True, "iris-control connected"
    snippet = out.replace("\n", " ")[:180] or f"exit {proc.returncode}"
    return False, snippet


def ensure_hermes_provider_config() -> None:
    """config.yaml provider 'ollama' → 'custom' (0.19+ 로컬 OpenAI-compat)."""
    path = hermes_home() / "config.yaml"
    if not path.is_file():
        return
    try:
        import yaml  # type: ignore
    except Exception:
        return
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError:
        return
    if not isinstance(data, dict):
        return
    model = data.get("model")
    if not isinstance(model, dict):
        return
    if str(model.get("provider") or "").strip().lower() != "ollama":
        return
    model["provider"] = "custom"
    data["model"] = model
    try:
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    except OSError:
        pass


if __name__ == "__main__":
    ensure_hermes_provider_config()
    assert is_hermes_gateway_running("http://127.0.0.1:1/v1") is False
    # Iris VIRTUAL_ENV 오염 시에도 Hermes venv 로 고정되는지
    os.environ["VIRTUAL_ENV"] = str(Path.cwd() / ".venv-fake-iris")
    os.environ["PYTHONPATH"] = str(Path.cwd())
    cleaned = _gateway_child_env()
    venv_py = _hermes_venv_python()
    if venv_py is not None:
        assert cleaned.get("VIRTUAL_ENV") == str(_hermes_venv_dir())
        assert "PYTHONPATH" not in cleaned
        cmd = _windows_hidden_cmd(hermes_executable("hermes") or "hermes")
        assert cmd[:3] == [str(venv_py), "-m", "hermes_cli.main"]
    exe = hermes_executable("hermes")
    print(
        "hermes_gateway ok - exe:",
        exe,
        "venv_py:",
        venv_py,
        "home:",
        hermes_home(),
        "key_set:",
        bool(resolve_hermes_api_key()),
        "running:",
        is_hermes_gateway_running("http://127.0.0.1:8642/v1"),
    )
