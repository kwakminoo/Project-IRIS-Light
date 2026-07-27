"""Hermes gateway 감지 및 자동 기동."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from iris.infrastructure.hermes_client import HermesClient


def _windows_hermes_candidates() -> list[Path]:
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if not local:
        return []
    root = Path(local) / "hermes" / "hermes-agent" / "venv" / "Scripts"
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
    return HermesClient(base_url, api_key=api_key).health_ok()


def _gateway_argv() -> list[str]:
    # 신규 기동 — stop 후 start 경로를 쓰므로 --replace에 의존하지 않음
    return ["gateway", "run", "--quiet", "--accept-hooks"]


def _windows_hidden_cmd(hermes_exe: str) -> list[str]:
    """콘솔 창 없이 기동 — venv의 pythonw로 entry point 직접 호출."""
    scripts = Path(hermes_exe).resolve().parent
    pythonw = scripts / "pythonw.exe"
    if pythonw.is_file():
        code = (
            "import sys; from hermes_cli.main import main; "
            "sys.argv=['hermes','gateway','run','--quiet','--accept-hooks']; "
            "raise SystemExit(main())"
        )
        return [str(pythonw), "-c", code]
    return [hermes_exe, *_gateway_argv()]


def _popen_hidden(cmd: list[str], *, env: dict[str, str]) -> subprocess.Popen[bytes]:
    popen_kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "env": env,
        "close_fds": True,
    }
    if sys.platform == "win32":
        creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        creationflags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
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
    if not exe:
        return False
    env = os.environ.copy()
    env.setdefault("HERMES_ACCEPT_HOOKS", "1")
    try:
        if sys.platform == "win32":
            _popen_hidden(_windows_hidden_cmd(exe), env=env)
        else:
            _popen_hidden([exe, *_gateway_argv()], env=env)
        return True
    except OSError:
        return False


def stop_hermes_gateway(command: str = "hermes", *, wait_sec: float = 20.0) -> bool:
    """`hermes gateway stop --all`로 락을 잡고 있는 구 프로세스를 내린다.

    ponytail: `--replace`만으로는 Windows에서 lock 보유 인스턴스가 남을 수 있음.
    천장: CLI stop 실패 시 taskkill로 gateway run 프로세스만 강제 종료.
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
                creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if sys.platform == "win32"
                else 0,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

    if sys.platform == "win32":
        _force_kill_windows_gateway_procs()

    deadline = time.monotonic() + wait_sec
    while time.monotonic() < deadline:
        # base_url 모르는 stop 경로 — health는 호출측에서 확인
        if not _windows_gateway_procs_alive():
            return True
        time.sleep(0.35)
    return not _windows_gateway_procs_alive()


def _gateway_process_pids() -> list[int]:
    """Hermes CLI `gateway stop`가 못 잡는 pythonw -c 기동 인스턴스까지 수집.

    주의: CommandLine에 hermes/gateway/run 문자열이 있는 Iris/PowerShell 자기 자신을
    죽이면 안 됨 → hermes_cli.main 기동 형태만 매칭.
    """
    if sys.platform != "win32":
        return []
    # ponytail: 전체 JSON 덤프 금지. hermes_cli.main + gateway argv 만.
    ps = (
        "$procs = Get-CimInstance Win32_Process | "
        "Where-Object { "
        "$_.CommandLine -and "
        "($_.CommandLine -like '*hermes_cli.main*') -and "
        "($_.CommandLine -like '*gateway*') "
        "}; "
        "($procs | ForEach-Object { $_.ProcessId }) -join ','"
    )
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            timeout=20,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
        )
    except (OSError, subprocess.SubprocessError):
        return []
    pids: list[int] = []
    for part in (out or "").strip().split(","):
        part = part.strip()
        if not part:
            continue
        try:
            pids.append(int(part))
        except ValueError:
            continue
    return pids


def _windows_gateway_procs_alive() -> bool:
    return bool(_gateway_process_pids())


def _force_kill_windows_gateway_procs() -> None:
    if sys.platform != "win32":
        return
    me = os.getpid()
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
    wait_sec: float = 30.0,
) -> bool:
    """켜져 있으면 즉시 True. 아니면 기동 후 /health 준비까지 대기."""
    if is_hermes_gateway_running(base_url, api_key=api_key):
        return True
    if not start_hermes_gateway(command):
        return False
    deadline = time.monotonic() + wait_sec
    while time.monotonic() < deadline:
        if is_hermes_gateway_running(base_url, api_key=api_key):
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
    stop_hermes_gateway(command, wait_sec=min(20.0, wait_sec / 2))

    # health가 내려갈 때까지 대기
    down_deadline = time.monotonic() + 15.0
    while time.monotonic() < down_deadline:
        if not is_hermes_gateway_running(base_url, api_key=api_key):
            break
        time.sleep(0.3)

    if not start_hermes_gateway(command):
        return False

    deadline = time.monotonic() + wait_sec
    while time.monotonic() < deadline:
        if is_hermes_gateway_running(base_url, api_key=api_key):
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


if __name__ == "__main__":
    assert is_hermes_gateway_running("http://127.0.0.1:1/v1") is False
    exe = hermes_executable("hermes")
    print(
        "hermes_gateway ok - exe:",
        exe,
        "running:",
        is_hermes_gateway_running("http://127.0.0.1:8642/v1"),
    )
