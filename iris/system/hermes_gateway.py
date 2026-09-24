"""Hermes gateway 감지 및 자동 기동."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from iris.infrastructure.hermes_client import HermesClient, HealthProbeResult
from iris.infrastructure.hermes_credentials import (
    hermes_home,
    load_hermes_dotenv,
    resolve_hermes_api_key,
)

# 진단 코드 — 설치 UI·로그에 노출 (시크릿 값 금지)
CODE_OK = "OK"
CODE_EXE_MISSING = "EXE_MISSING"  # G9
CODE_PROCESS_CRASH = "PROCESS_CRASH"  # G1
CODE_ENV_POLLUTION = "ENV_MISMATCH"  # G2/G5
CODE_STALE_LOCK = "STALE_LOCK"  # G3
CODE_TIMEOUT = "TIMEOUT"  # G4
CODE_PORT_CONFLICT = "PORT_CONFLICT"  # G6
CODE_HEALTH_BAD_BODY = "HEALTH_BAD_BODY"  # G7
CODE_HEALTH_REFUSED = "HEALTH_REFUSED"
CODE_SECURITY_BLOCK = "SECURITY_BLOCK_SUSPECTED"  # G8
CODE_API_KEY_SEPARATE = "API_KEY_NOT_HEALTH"  # G10 (안내 전용)
CODE_START_FAILED = "START_FAILED"

_POLLUTION_ENV_KEYS = (
    "VIRTUAL_ENV",
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONEXECUTABLE",
    "PYTHONUSERBASE",
    "UV_PROJECT",
    "UV_PROJECT_ENVIRONMENT",
    "UV_PYTHON",
    "UV_PYTHON_PREFERENCE",
    "CONDA_PREFIX",
    "CONDA_DEFAULT_ENV",
    "CONDA_PYTHON_EXE",
    "PIP_PYTHON",
)

_GATEWAY_PORT_DEFAULT = 8642


@dataclass
class GatewayDiagnosis:
    """gateway 기동/헬스 실패 스냅샷 — UI·복사·현장 진단용."""

    code: str = CODE_START_FAILED
    ok: bool = False
    message: str = ""
    action: str = ""
    detail: str = ""
    log_dir: str = ""
    stdout_log: str = ""
    stderr_log: str = ""
    command: list[str] = field(default_factory=list)
    exit_code: int | None = None
    port: int = _GATEWAY_PORT_DEFAULT
    port_owner_pid: int | None = None
    port_owner_name: str = ""
    health: dict[str, object] = field(default_factory=dict)
    hermes_home: str = ""
    api_server_enabled: str = ""
    has_api_key: bool = False
    timestamp: str = ""

    def user_message(self) -> str:
        """설치 UI용 짧은 문구 (시크릿 없음)."""
        parts = [f"[{self.code}] {self.message}".strip()]
        if self.action:
            parts.append(self.action)
        if self.stderr_log:
            parts.append(f"로그: {self.stderr_log}")
        elif self.log_dir:
            parts.append(f"로그: {self.log_dir}")
        return "\n".join(p for p in parts if p)

    def copy_text(self) -> str:
        """「진단 정보 복사」용 — 키 값 제외."""
        payload = asdict(self)
        # 방어: 혹시 detail에 키가 섞여도 길이를 제한
        payload["detail"] = str(payload.get("detail") or "")[:2000]
        return json.dumps(payload, ensure_ascii=False, indent=2)


_LAST_DIAGNOSIS: GatewayDiagnosis | None = None
_LAST_CHILD: subprocess.Popen[bytes] | None = None
_LAST_LOG_PATHS: tuple[Path, Path] | None = None


def get_last_gateway_diagnosis() -> GatewayDiagnosis | None:
    return _LAST_DIAGNOSIS


def clear_last_gateway_diagnosis() -> None:
    """재시도·재검사 전 잔상 TIMEOUT 진단을 지운다."""
    global _LAST_DIAGNOSIS, _LAST_CHILD, _LAST_LOG_PATHS
    _LAST_DIAGNOSIS = None
    _LAST_CHILD = None
    _LAST_LOG_PATHS = None
    try:
        path = gateway_diagnosis_path()
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def mark_gateway_already_running(base_url: str) -> GatewayDiagnosis:
    """이미 /health OK인 gateway — 진단을 OK로 덮어써 잔상 TIMEOUT을 막는다."""
    health = probe_gateway_health(base_url, timeout_sec=2.0)
    return _set_diagnosis(
        GatewayDiagnosis(
            code=CODE_OK,
            ok=True,
            message="gateway 이미 실행 중",
            health={
                "code": health.code,
                "url": health.url,
                "summary": health.body_summary,
            },
            has_api_key=bool(resolve_hermes_api_key()),
            api_server_enabled=load_hermes_dotenv().get("API_SERVER_ENABLED", "true"),
            port=gateway_port_from_base_url(base_url),
        )
    )


def gateway_diagnosis_path() -> Path:
    return _gateway_log_dir() / "gateway-last-diagnosis.json"


def _set_diagnosis(diag: GatewayDiagnosis) -> GatewayDiagnosis:
    global _LAST_DIAGNOSIS
    diag.timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    diag.hermes_home = diag.hermes_home or str(hermes_home())
    _LAST_DIAGNOSIS = diag
    try:
        path = gateway_diagnosis_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(diag.copy_text(), encoding="utf-8")
    except OSError:
        pass
    return diag


def _gateway_log_dir() -> Path:
    d = hermes_home() / "logs" / "iris-gateway"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def _new_gateway_log_paths() -> tuple[Path, Path]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = _gateway_log_dir() / f"gateway-{stamp}"
    return base.with_suffix(".out.log"), base.with_suffix(".err.log")


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


def gateway_port_from_base_url(base_url: str) -> int:
    try:
        parsed = urlparse((base_url or "").strip() or "http://127.0.0.1:8642/v1")
        if parsed.port:
            return int(parsed.port)
    except (ValueError, TypeError):
        pass
    env_port = load_hermes_dotenv().get("API_SERVER_PORT", "").strip()
    if env_port.isdigit():
        return int(env_port)
    return _GATEWAY_PORT_DEFAULT


def is_hermes_gateway_running(
    base_url: str,
    *,
    api_key: str = "",
    timeout_sec: float | None = None,
) -> bool:
    client = HermesClient(
        base_url,
        api_key=resolve_hermes_api_key(api_key),
    )
    if timeout_sec is not None:
        # 설정창 등 빠른 핑 — /models까지는 보지 않는다.
        return client.health_ok(timeout_sec=timeout_sec)
    return client.gateway_ready()


def probe_gateway_health(
    base_url: str, *, timeout_sec: float = 2.0
) -> HealthProbeResult:
    return HermesClient(base_url, api_key="").probe_health(timeout_sec=timeout_sec)


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


def is_hermes_trampoline_failure(text: str) -> bool:
    """uv trampoline이 베이스 Python을 못 찾는 실패(os error 2)인지."""
    t = (text or "").lower()
    if "uv trampoline" in t:
        return True
    return "entity not found" in t and "os error 2" in t


def _pyvenv_home_path(venv_dir: Path) -> Path | None:
    cfg = venv_dir / "pyvenv.cfg"
    if not cfg.is_file():
        return None
    try:
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("home"):
                _, _, raw = line.partition("=")
                home = Path(raw.strip().strip('"'))
                return home if str(home) else None
    except OSError:
        return None
    return None


def is_hermes_cli_missing_failure(text: str) -> bool:
    """gateway/venv 가 hermes_cli 없이 기동돼 ModuleNotFoundError 나는 경우."""
    t = (text or "").lower()
    if not t:
        return False
    if "no module named 'hermes_cli'" in t or 'no module named "hermes_cli"' in t:
        return True
    return "hermes_cli" in t and "modulenotfounderror" in t


def is_hermes_gateway_dep_missing_failure(text: str) -> bool:
    """API gateway 필수 의존성(aiohttp 등) 누락으로 즉시 죽는 경우."""
    t = (text or "").lower()
    if not t:
        return False
    if "requires the 'mcp' python sdk" in t:
        return True
    if "modulenotfounderror" not in t:
        return False
    for mod in ("aiohttp", "hermes_cli", "mcp"):
        if f"no module named '{mod}'" in t or f'no module named "{mod}"' in t:
            return True
    return False


def probe_hermes_runtime(
    *, command: str = "hermes", timeout_sec: float = 25.0
) -> tuple[bool, str]:
    """Hermes venv/exe가 실제로 gateway를 띄울 수 있는지.

    파일만 있고 베이스 인터프리터가 사라진 경우(uv trampoline os error 2)와
    venv만 있고 hermes_cli/aiohttp 가 없는 껍데기 설치를 설치·gateway 전에 잡는다.
    """
    venv_dir = _hermes_venv_dir()
    venv_py = _hermes_venv_python()
    if venv_py is not None:
        home = _pyvenv_home_path(venv_dir)
        if home is not None and not home.is_dir():
            return False, f"pyvenv home 없음: {home}"
        # gateway 는 python -m hermes_cli.main + aiohttp(tcp_site).
        # print('ok')/hermes_cli 만 보면 껍데기·extras 누락을 통과시킨다.
        try:
            proc = subprocess.run(
                [
                    str(venv_py),
                    "-c",
                    "import hermes_cli, aiohttp, mcp; print('ok')",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(5.0, timeout_sec),
                check=False,
                env=_gateway_child_env(),
                creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if sys.platform == "win32"
                else 0,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"venv python 실행 실패: {exc}"
        err = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()
        if proc.returncode != 0 or is_hermes_trampoline_failure(err):
            detail = err[:400] if err else f"exit {proc.returncode}"
            if is_hermes_cli_missing_failure(detail):
                return False, f"hermes_cli 없음: {detail[:240]}"
            if is_hermes_gateway_dep_missing_failure(detail):
                return False, f"gateway 의존성 없음: {detail[:240]}"
            return False, detail
        if "ok" not in (proc.stdout or ""):
            return False, f"hermes_cli import 응답 이상: {err[:240]}"
        return True, f"venv ok ({venv_py.name})"

    exe = hermes_executable(command)
    if not exe:
        return False, "hermes 실행 파일 없음"
    try:
        proc = subprocess.run(
            [exe, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(5.0, timeout_sec),
            check=False,
            env=_gateway_child_env(),
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if sys.platform == "win32"
            else 0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"hermes 실행 실패: {exc}"
    err = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()
    if proc.returncode != 0 or is_hermes_trampoline_failure(err):
        detail = err[:400] if err else f"exit {proc.returncode}"
        return False, detail
    return True, f"exe ok ({Path(exe).name})"


def _gateway_argv() -> list[str]:
    # 신규 기동 — stop 후 start 경로를 쓰므로 --replace에 의존하지 않음
    return ["gateway", "run", "--quiet", "--accept-hooks"]


def _strip_pollution(env: dict[str, str]) -> None:
    for k in _POLLUTION_ENV_KEYS:
        env.pop(k, None)


def _gateway_child_env() -> dict[str, str]:
    """Hermes gateway 자식 프로세스 환경 — Iris .venv 오염 제거 + Hermes 키만 명시.

    Iris (.venv) VIRTUAL_ENV/PYTHONPATH 를 그대로 넘기면 uv hermes.exe 가
    패키지 없는 base Python 으로 re-exec 되어
    ``No module named 'pydantic_core._pydantic_core'`` 가 난다.
    """
    env = os.environ.copy()
    # G2: Iris/IDE 오염을 먼저 제거한 뒤 Hermes 전용 값만 넣는다
    _strip_pollution(env)

    home = hermes_home()
    env["HERMES_HOME"] = str(home)
    env["HERMES_ACCEPT_HOOKS"] = "1"
    dotenv = load_hermes_dotenv()
    for key, val in dotenv.items():
        # Iris 프로세스 값이 있어도 Hermes 전용 키는 파일 값을 쓴다
        env[key] = val
    env.setdefault("API_SERVER_ENABLED", "true")
    env.setdefault("API_SERVER_HOST", "127.0.0.1")
    env.setdefault("API_SERVER_PORT", str(_GATEWAY_PORT_DEFAULT))

    venv = _hermes_venv_dir()
    venv_py = _hermes_venv_python()
    if venv.is_dir() and venv_py is not None:
        env["VIRTUAL_ENV"] = str(venv)
        scripts = str(venv / ("Scripts" if sys.platform == "win32" else "bin"))
        path = env.get("PATH", "")
        if scripts and not path.lower().startswith(scripts.lower()):
            env["PATH"] = scripts + os.pathsep + path
    return env


def _env_snapshot_safe(env: dict[str, str]) -> dict[str, str]:
    """진단용 — 키 값은 유무만."""
    return {
        "HERMES_HOME": env.get("HERMES_HOME", ""),
        "API_SERVER_ENABLED": env.get("API_SERVER_ENABLED", ""),
        "API_SERVER_HOST": env.get("API_SERVER_HOST", ""),
        "API_SERVER_PORT": env.get("API_SERVER_PORT", ""),
        "VIRTUAL_ENV": env.get("VIRTUAL_ENV", ""),
        "has_API_SERVER_KEY": "yes" if env.get("API_SERVER_KEY") else "no",
        "PYTHONPATH_set": "yes" if env.get("PYTHONPATH") else "no",
    }


def _windows_hidden_cmd(hermes_exe: str) -> list[str]:
    """콘솔 창 없이 기동.

    venv python -m hermes_cli.main 우선 — hermes.exe(uv trampoline)만 쓰면
    Iris VIRTUAL_ENV 오염 시 base Python 으로 re-exec 되어 pydantic_core 가 빠진다.
    """
    venv_py = _hermes_venv_python()
    if venv_py is not None:
        return [str(venv_py), "-m", "hermes_cli.main", *_gateway_argv()]
    return [hermes_exe, *_gateway_argv()]


def _build_gateway_cmd(command: str = "hermes") -> list[str] | None:
    exe = hermes_executable(command)
    venv_py = _hermes_venv_python()
    if not exe and venv_py is None:
        return None
    if sys.platform == "win32":
        return _windows_hidden_cmd(exe or "hermes")
    if venv_py is not None:
        return [str(venv_py), "-m", "hermes_cli.main", *_gateway_argv()]
    return [exe or "hermes", *_gateway_argv()]


def _popen_hidden(
    cmd: list[str],
    *,
    env: dict[str, str],
    cwd: str | None = None,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> subprocess.Popen[bytes]:
    global _LAST_CHILD, _LAST_LOG_PATHS
    out_f = None
    err_f = None
    if stdout_path is not None and stderr_path is not None:
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        out_f = open(stdout_path, "ab")  # noqa: SIM115
        err_f = open(stderr_path, "ab")  # noqa: SIM115
        _LAST_LOG_PATHS = (stdout_path, stderr_path)
    popen_kwargs: dict = {
        "stdout": out_f if out_f is not None else subprocess.DEVNULL,
        "stderr": err_f if err_f is not None else subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "env": env,
        "close_fds": out_f is None,
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
    proc = subprocess.Popen(cmd, **popen_kwargs)
    _LAST_CHILD = proc
    # Windows: CreateProcess 상속 후 부모 핸들은 닫아도 자식은 유지
    if out_f is not None:
        try:
            out_f.close()
        except OSError:
            pass
    if err_f is not None:
        try:
            err_f.close()
        except OSError:
            pass
    return proc


def _tail_log(path: Path | None, *, limit: int = 800) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    text = data.decode("utf-8", errors="replace").strip()
    if len(text) > limit:
        return text[-limit:]
    return text


def _child_exit_code() -> int | None:
    proc = _LAST_CHILD
    if proc is None:
        return None
    return proc.poll()


def start_hermes_gateway(command: str = "hermes") -> bool:
    """`hermes gateway run`을 창 없이 백그라운드로 기동. 실행 파일이 없으면 False."""
    cmd = _build_gateway_cmd(command)
    if cmd is None:
        _set_diagnosis(
            GatewayDiagnosis(
                code=CODE_EXE_MISSING,
                message="Hermes 실행 파일/venv python을 찾지 못했습니다.",
                action="시작 프로토콜에서 Hermes 설치를 다시 실행하거나 PATH를 확인하세요.",
            )
        )
        return False
    env = _gateway_child_env()
    cwd = str(_hermes_agent_dir())
    if not Path(cwd).is_dir():
        cwd = None
    out_log, err_log = _new_gateway_log_paths()
    try:
        # 기동 직전 스냅샷 (키 값 없음)
        snap = _env_snapshot_safe(env)
        try:
            (out_log.parent / "gateway-last-env.json").write_text(
                json.dumps(snap, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass
        _popen_hidden(cmd, env=env, cwd=cwd, stdout_path=out_log, stderr_path=err_log)
        # Popen 성공 ≠ 기동 성공 — 즉시 크래시는 ensure 루프에서 판정(G1)
        _set_diagnosis(
            GatewayDiagnosis(
                code=CODE_OK,
                ok=False,
                message="gateway 프로세스 기동 요청됨 — health 대기 중",
                command=cmd,
                log_dir=str(_gateway_log_dir()),
                stdout_log=str(out_log),
                stderr_log=str(err_log),
                api_server_enabled=snap.get("API_SERVER_ENABLED", ""),
                has_api_key=snap.get("has_API_SERVER_KEY") == "yes",
                detail=json.dumps(snap, ensure_ascii=False),
            )
        )
        return True
    except OSError as exc:
        _set_diagnosis(
            GatewayDiagnosis(
                code=CODE_START_FAILED,
                message=f"gateway 기동 실패: {exc}",
                action="백신/EDR이 차단했는지, 실행 파일 권한을 확인하세요.",
                command=cmd,
                log_dir=str(_gateway_log_dir()),
                stdout_log=str(out_log),
                stderr_log=str(err_log),
                detail=str(exc)[:400],
            )
        )
        return False


def stop_hermes_gateway(
    command: str = "hermes",
    *,
    wait_sec: float = 20.0,
    should_abort: Callable[[], bool] | None = None,
) -> bool:
    """`hermes gateway stop --all`로 락을 잡고 있는 구 프로세스를 내린다.

    ponytail: `--replace`만으로는 Windows에서 lock 보유 인스턴스가 남을 수 있음.
    천장: CLI stop 실패 시 taskkill + stale gateway.lock 제거.
    """
    exe = hermes_executable(command)
    if exe and not (should_abort and should_abort()):
        try:
            # ponytail: CLI stop이 길면 설치 위저드가 '멈춤'으로 보인다 — 상한을 짧게.
            cli_timeout = min(15.0, max(6.0, wait_sec))
            subprocess.run(
                [exe, "gateway", "stop", "--all"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=cli_timeout,
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
        if should_abort and should_abort():
            break
        if not _windows_gateway_procs_alive() and not _lock_pid_alive():
            _clear_stale_gateway_lock()
            return True
        time.sleep(0.35)
    _clear_stale_gateway_lock()
    return not _windows_gateway_procs_alive()


def _gateway_lock_path() -> Path:
    return hermes_home() / "gateway.lock"


def _gateway_pid_path() -> Path:
    return hermes_home() / "gateway.pid"


def _read_pid_file(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return int(data.get("pid") or 0)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        try:
            raw = path.read_text(encoding="utf-8", errors="replace").strip()
            return int(raw) if raw.isdigit() else 0
        except (OSError, ValueError):
            return 0


def _lock_pid_alive() -> bool:
    pid = _read_pid_file(_gateway_lock_path())
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


def _pid_name(pid: int) -> str:
    if pid <= 0:
        return ""
    try:
        import psutil  # type: ignore

        return str(psutil.Process(pid).name() or "")
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                text=True,
                timeout=10,
                creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
            )
            # "name.exe","pid","session",...
            line = (out or "").strip().splitlines()
            if line and line[0].startswith('"'):
                return line[0].split(",")[0].strip('"')
        except (OSError, subprocess.SubprocessError):
            pass
    return ""


def _pid_looks_like_hermes(pid: int) -> bool:
    """살아 있는 PID가 Hermes gateway인지 — PID 재사용/타 프로세스 오인 방지."""
    if pid <= 0:
        return False
    try:
        import psutil  # type: ignore

        proc = psutil.Process(pid)
        name = (proc.name() or "").lower()
        cmdline = " ".join(proc.cmdline() or []).lower()
        if " -m iris" in cmdline or "iris_launcher" in cmdline:
            return False
        return (
            name.startswith("hermes")
            or "hermes_cli.main" in cmdline
            or "\\hermes" in cmdline
            or "/hermes" in cmdline
            or "gateway" in cmdline
        )
    except Exception:
        # psutil 없으면 이름만
        name = _pid_name(pid).lower()
        return name.startswith("hermes") or "python" in name


def _clear_stale_gateway_lock() -> list[str]:
    """죽은 PID가 남긴 gateway.lock / gateway.pid / kanban lock 제거.

    Hermes는 gateway.pid를 O_CREAT|O_EXCL로 만들므로, 죽은 프로세스의 pid
    파일이 남으면 새 기동이 FileExistsError로 즉시 종료한다(exit 계열).
    살아 있는 Hermes PID의 lock/pid는 삭제하지 않는다 (G3).
    """
    cleared: list[str] = []
    home = hermes_home()
    pid_path = home / "gateway.pid"
    lock_path = home / "gateway.lock"

    for path, label in ((pid_path, "gateway.pid"), (lock_path, "gateway.lock")):
        if not path.is_file():
            continue
        pid = _read_pid_file(path)
        stale = True
        if pid > 0 and _pid_exists(pid) and _pid_looks_like_hermes(pid):
            stale = False
        if stale:
            try:
                path.unlink()
                cleared.append(label)
            except OSError:
                pass

    # kanban dispatcher stale lock (Hermes 전용 판정 금지 — dispatcher는 별 프로세스)
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
                cleared.append("kanban.lock")
            except OSError:
                pass
    return cleared


def _port_listeners(port: int) -> list[tuple[int, str]]:
    """(pid, name) listening on port — psutil 우선, 없으면 netstat."""
    found: list[tuple[int, str]] = []
    try:
        import psutil  # type: ignore

        for conn in psutil.net_connections(kind="inet"):
            try:
                if not conn.laddr or int(conn.laddr.port) != port:
                    continue
                status = str(getattr(conn, "status", "") or "").upper()
                if "LISTEN" not in status:
                    continue
                pid = int(conn.pid or 0)
                if pid <= 0:
                    continue
                found.append((pid, _pid_name(pid) or "?"))
            except (psutil.Error, TypeError, ValueError, AttributeError):
                continue
        if found:
            # 중복 PID 제거
            uniq: dict[int, str] = {}
            for pid, name in found:
                uniq[pid] = name
            return [(p, n) for p, n in uniq.items()]
    except Exception:
        pass

    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                ["netstat", "-ano", "-p", "tcp"],
                text=True,
                timeout=15,
                creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
            )
        except (OSError, subprocess.SubprocessError):
            return found
        needle = f":{port} "
        seen: set[int] = set()
        for line in (out or "").splitlines():
            if needle not in line or "LISTENING" not in line.upper():
                continue
            parts = line.split()
            if not parts:
                continue
            try:
                pid = int(parts[-1])
            except ValueError:
                continue
            if pid > 0 and pid not in seen:
                seen.add(pid)
                found.append((pid, _pid_name(pid) or "?"))
    return found


def _diagnose_port_conflict(base_url: str) -> GatewayDiagnosis | None:
    """8642(또는 base)를 Hermes가 아닌 프로세스가 점유하면 진단 반환 (G6)."""
    port = gateway_port_from_base_url(base_url)
    health = probe_gateway_health(base_url, timeout_sec=1.5)
    if health.ok and health.looks_like_hermes:
        return None
    listeners = _port_listeners(port)
    if not listeners:
        return None
    # health ok가 아닌데 포트만 점유 — 또는 health ok인데 hermes 아님
    for pid, name in listeners:
        if _pid_looks_like_hermes(pid):
            continue
        return GatewayDiagnosis(
            code=CODE_PORT_CONFLICT,
            message=(
                f"포트 {port}를 다른 프로세스가 사용 중입니다 "
                f"(PID {pid}, {name or 'unknown'})."
            ),
            action=(
                f"해당 프로그램을 종료하거나 API_SERVER_PORT를 변경한 뒤 "
                f"다시 시도하세요."
            ),
            port=port,
            port_owner_pid=pid,
            port_owner_name=name,
            health={
                "code": health.code,
                "url": health.url,
                "summary": health.body_summary,
            },
            detail=f"listeners={listeners!r} health={health.code}",
        )
    if health.ok and not health.looks_like_hermes and listeners:
        pid, name = listeners[0]
        return GatewayDiagnosis(
            code=CODE_PORT_CONFLICT,
            message=(
                f"포트 {port} 응답이 Hermes가 아닙니다 "
                f"(PID {pid}, {name or 'unknown'})."
            ),
            action="점유 프로세스를 종료한 뒤 설치를 다시 실행하세요.",
            port=port,
            port_owner_pid=pid,
            port_owner_name=name,
            health={
                "code": health.code,
                "url": health.url,
                "summary": health.body_summary,
            },
        )
    return None


def _gateway_process_pids() -> list[int]:
    """Hermes gateway 프로세스 PID.

    ponytail: Win32_Process 전체 스캔(PowerShell CIM)은 환경에 따라 수 초~무한 대기에
    가깝게 느려질 수 있음 → gateway.lock PID + psutil(있으면)만 사용.
    """
    pids: set[int] = set()

    for path in (_gateway_lock_path(), _gateway_pid_path()):
        pid = _read_pid_file(path)
        if pid > 0 and _pid_exists(pid) and _pid_looks_like_hermes(pid):
            pids.add(pid)

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


def _health_to_fail_code(health: HealthProbeResult) -> str:
    if health.code == "connection_refused":
        return CODE_HEALTH_REFUSED
    if health.code == "bad_body":
        return CODE_HEALTH_BAD_BODY
    if health.code == "timeout":
        return CODE_TIMEOUT
    if health.code in ("unreachable", "http_error"):
        # G8: 프로세스는 살아 있는데 localhost가 막히면 보안 제품 의심
        if _windows_gateway_procs_alive() or (_LAST_CHILD and _LAST_CHILD.poll() is None):
            return CODE_SECURITY_BLOCK
        return CODE_HEALTH_REFUSED
    return CODE_TIMEOUT


def _wait_until_healthy(
    base_url: str,
    *,
    wait_sec: float,
    should_abort: Callable[[], bool] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> bool:
    """짧은 간격 → backoff 폴링. 자식이 죽으면 즉시 실패 (G1/G4)."""
    deadline = time.monotonic() + max(5.0, wait_sec)
    delay = 0.25
    last_health: HealthProbeResult | None = None
    while time.monotonic() < deadline:
        if should_abort and should_abort():
            return False
        exit_code = _child_exit_code()
        if exit_code is not None:
            err_tail = _tail_log(_LAST_LOG_PATHS[1] if _LAST_LOG_PATHS else None)
            out_log = str(_LAST_LOG_PATHS[0]) if _LAST_LOG_PATHS else ""
            err_log = str(_LAST_LOG_PATHS[1]) if _LAST_LOG_PATHS else ""
            _set_diagnosis(
                GatewayDiagnosis(
                    code=CODE_PROCESS_CRASH,
                    message=f"gateway 프로세스가 즉시 종료되었습니다 (exit {exit_code}).",
                    action=(
                        "stderr 로그를 확인하세요. 흔한 원인: stale lock, "
                        "venv 오염, 누락 패키지, 포트 충돌."
                    ),
                    exit_code=exit_code,
                    log_dir=str(_gateway_log_dir()),
                    stdout_log=out_log,
                    stderr_log=err_log,
                    detail=err_tail[:1500],
                    has_api_key=bool(resolve_hermes_api_key()),
                )
            )
            return False
        health = probe_gateway_health(base_url, timeout_sec=min(2.0, delay + 1.0))
        last_health = health
        if health.ok:
            _set_diagnosis(
                GatewayDiagnosis(
                    code=CODE_OK,
                    ok=True,
                    message="gateway /health OK",
                    health={
                        "code": health.code,
                        "url": health.url,
                        "summary": health.body_summary,
                    },
                    log_dir=str(_gateway_log_dir()),
                    stdout_log=str(_LAST_LOG_PATHS[0]) if _LAST_LOG_PATHS else "",
                    stderr_log=str(_LAST_LOG_PATHS[1]) if _LAST_LOG_PATHS else "",
                    has_api_key=bool(resolve_hermes_api_key()),
                    api_server_enabled=load_hermes_dotenv().get(
                        "API_SERVER_ENABLED", "true"
                    ),
                )
            )
            return True
        if on_progress:
            on_progress(f"health 대기… ({health.code})")
        time.sleep(delay)
        delay = min(2.0, delay * 1.35)

    # timeout — 재시작 전 원인 스냅샷
    code = _health_to_fail_code(last_health) if last_health else CODE_TIMEOUT
    err_tail = _tail_log(_LAST_LOG_PATHS[1] if _LAST_LOG_PATHS else None)
    _set_diagnosis(
        GatewayDiagnosis(
            code=code,
            message="gateway /health 응답 대기 시간이 초과되었습니다.",
            action=(
                "느린 PC·백신 검사 중이면 재시도하세요. "
                "계속 실패하면 stderr 로그와 포트 점유를 확인하세요."
                + (
                    " (참고: API 키 문제는 /health와 무관합니다 — 채팅 단계에서 진단됩니다.)"
                    if not resolve_hermes_api_key()
                    else ""
                )
            ),
            log_dir=str(_gateway_log_dir()),
            stdout_log=str(_LAST_LOG_PATHS[0]) if _LAST_LOG_PATHS else "",
            stderr_log=str(_LAST_LOG_PATHS[1]) if _LAST_LOG_PATHS else "",
            health={
                "code": last_health.code if last_health else "",
                "url": last_health.url if last_health else "",
                "summary": last_health.body_summary if last_health else "",
            },
            detail=err_tail[:1500],
            port=gateway_port_from_base_url(base_url),
            has_api_key=bool(resolve_hermes_api_key()),
            api_server_enabled=load_hermes_dotenv().get("API_SERVER_ENABLED", ""),
        )
    )
    return False


def ensure_hermes_gateway_running(
    base_url: str,
    *,
    api_key: str = "",
    command: str = "hermes",
    wait_sec: float = 45.0,
    should_abort: Callable[[], bool] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> bool:
    """켜져 있으면 즉시 True. 아니면 기동 후 /health 준비까지 대기."""
    key = resolve_hermes_api_key(api_key)

    def _note(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    def _aborted() -> bool:
        return bool(should_abort and should_abort())

    # 이미 Hermes health OK
    health = probe_gateway_health(base_url, timeout_sec=2.0)
    if health.ok:
        _set_diagnosis(
            GatewayDiagnosis(
                code=CODE_OK,
                ok=True,
                message="gateway 이미 실행 중",
                health={
                    "code": health.code,
                    "url": health.url,
                    "summary": health.body_summary,
                },
                has_api_key=bool(key),
            )
        )
        return True
    if _aborted():
        return False

    # G6: 타 프로세스 포트 점유
    conflict = _diagnose_port_conflict(base_url)
    if conflict is not None:
        _note(conflict.message)
        _set_diagnosis(conflict)
        return False

    # G3: stale lock/pid 정리 (살아 있는 Hermes는 유지)
    cleared = _clear_stale_gateway_lock()
    if cleared:
        _note(f"stale lock 정리: {', '.join(cleared)}")
        _set_diagnosis(
            GatewayDiagnosis(
                code=CODE_STALE_LOCK,
                message=f"죽은 프로세스 잔재 제거: {', '.join(cleared)}",
                action="재기동을 계속합니다.",
                detail=",".join(cleared),
            )
        )

    # 좀비 Hermes만 있으면 정리 후 재기동
    if _windows_gateway_procs_alive() or _gateway_lock_path().is_file():
        # lock이 살아 있는 Hermes인데 health 실패 → 재시작 경로
        _note("좀비 gateway 정리 중…")
        stop_hermes_gateway(
            command,
            wait_sec=min(12.0, wait_sec / 2),
            should_abort=should_abort,
        )
        if probe_gateway_health(base_url, timeout_sec=2.0).ok:
            return True
    if _aborted():
        return False

    # G5/G9: 실행 경로·env 사전 점검
    if _build_gateway_cmd(command) is None:
        _set_diagnosis(
            GatewayDiagnosis(
                code=CODE_EXE_MISSING,
                message="Hermes 실행 파일/venv python을 찾지 못했습니다.",
                action="Hermes 설치 단계를 다시 실행하세요.",
            )
        )
        return False
    env = _gateway_child_env()
    if env.get("API_SERVER_ENABLED", "").lower() in ("0", "false", "no"):
        _set_diagnosis(
            GatewayDiagnosis(
                code=CODE_ENV_POLLUTION,
                message="API_SERVER_ENABLED가 꺼져 있습니다.",
                action="%LOCALAPPDATA%\\hermes\\.env 에서 API_SERVER_ENABLED=true 로 설정하세요.",
                api_server_enabled=env.get("API_SERVER_ENABLED", ""),
                has_api_key=bool(env.get("API_SERVER_KEY")),
            )
        )
        return False

    _note("Hermes gateway 기동…")
    if not start_hermes_gateway(command):
        return False
    return _wait_until_healthy(
        base_url,
        wait_sec=wait_sec,
        should_abort=should_abort,
        on_progress=on_progress,
    )


def restart_hermes_gateway(
    base_url: str,
    *,
    api_key: str = "",
    command: str = "hermes",
    wait_sec: float = 60.0,
    should_abort: Callable[[], bool] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> bool:
    """구 gateway를 완전히 내리고 새로 기동 — MCP 서브프로세스를 다시 붙인다.

    `--replace`만 쓰면 Windows에서 'runtime lock already held'로 신 프로세스가
    죽고, 오전부터 떠 있던 구 gateway(MCP 0 tools)가 그대로 남는 문제가 있었다.
    """
    key = resolve_hermes_api_key(api_key)

    def _note(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    def _aborted() -> bool:
        return bool(should_abort and should_abort())

    # 재시작 전 스냅샷
    pre = probe_gateway_health(base_url, timeout_sec=1.5)
    _note("기존 gateway 중지…")
    stop_hermes_gateway(
        command,
        wait_sec=min(12.0, wait_sec / 3),
        should_abort=should_abort,
    )
    if _aborted():
        return False

    down_deadline = time.monotonic() + 10.0
    while time.monotonic() < down_deadline:
        if _aborted():
            return False
        if not probe_gateway_health(base_url, timeout_sec=1.0).ok:
            break
        time.sleep(0.3)

    cleared = _clear_stale_gateway_lock()
    if cleared:
        _note(f"stale lock 정리: {', '.join(cleared)}")

    conflict = _diagnose_port_conflict(base_url)
    if conflict is not None:
        # stop 후에도 타 프로세스가 점유
        _set_diagnosis(conflict)
        return False

    _note("gateway 재기동…")
    if not start_hermes_gateway(command):
        return False

    ok = _wait_until_healthy(
        base_url,
        wait_sec=wait_sec,
        should_abort=should_abort,
        on_progress=on_progress,
    )
    if not ok and _LAST_DIAGNOSIS is not None:
        # 이전 health 정보를 detail에 보강
        d = _LAST_DIAGNOSIS
        d.detail = (
            (d.detail or "")
            + f"\npre_restart_health={pre.code}:{pre.body_summary}"
        )[:2000]
        d.has_api_key = bool(key)
        _set_diagnosis(d)
    return ok


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
    """config.yaml provider 정리 — Iris API id / 잘못된 openrouter 오염 복구.

    - `ollama` → `custom` (Hermes 0.19+ 로컬 OpenAI-compat)
    - `default`가 Iris `api:{id}:{model}` 이면 Ollama custom으로 되돌림
    - provider=openrouter + base_url이 :11434 이면 로컬 custom으로 복구
    """
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

    provider = str(model.get("provider") or "").strip().lower()
    default = str(model.get("default") or "").strip()
    base_url = str(model.get("base_url") or "").strip().lower()
    changed = False
    local_url = "http://127.0.0.1:11434/v1"

    def _looks_like_iris_api(mid: str) -> bool:
        return mid.lower().startswith("api:")

    if _looks_like_iris_api(default):
        # Iris 피커 API 모델이 Hermes default로 오염된 경우
        model["default"] = _fallback_ollama_model_name()
        model["provider"] = "custom"
        model["base_url"] = local_url
        changed = True
    elif provider == "ollama":
        model["provider"] = "custom"
        if not base_url:
            model["base_url"] = local_url
        changed = True
    elif provider == "openrouter" and (
        _looks_like_iris_api(default) or "11434" in base_url
    ):
        # Iris API id 또는 Ollama URL이 openrouter에 섞인 오염 상태
        model["provider"] = "custom"
        model["base_url"] = local_url
        if _looks_like_iris_api(default) or "/" in default:
            model["default"] = _fallback_ollama_model_name()
        changed = True

    if not changed:
        return
    data["model"] = model
    try:
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    except OSError:
        pass


def _fallback_ollama_model_name() -> str:
    """오염된 Hermes default 복구용 — 로컬 Ollama 목록의 첫 모델 또는 안전한 기본값."""
    try:
        from urllib.request import urlopen

        with urlopen("http://127.0.0.1:11434/api/tags", timeout=2.0) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        for item in payload.get("models") or []:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                if name and not name.lower().startswith("api:"):
                    return name
    except Exception:
        pass
    return "llama3.2"


if __name__ == "__main__":
    ensure_hermes_provider_config()
    assert is_hermes_gateway_running("http://127.0.0.1:1/v1") is False
    # Iris VIRTUAL_ENV 오염 시에도 Hermes venv 로 고정되는지
    os.environ["VIRTUAL_ENV"] = str(Path.cwd() / ".venv-fake-iris")
    os.environ["PYTHONPATH"] = str(Path.cwd())
    cleaned = _gateway_child_env()
    venv_py = _hermes_venv_python()
    assert "PYTHONPATH" not in cleaned
    if venv_py is not None:
        assert cleaned.get("VIRTUAL_ENV") == str(_hermes_venv_dir())
        cmd = _windows_hidden_cmd(hermes_executable("hermes") or "hermes")
        assert cmd[:3] == [str(venv_py), "-m", "hermes_cli.main"]
    else:
        assert "VIRTUAL_ENV" not in cleaned
    # health parse / diagnosis path
    from iris.infrastructure.hermes_client import parse_health_payload

    assert parse_health_payload({"status": "ok", "platform": "hermes-agent"})[0]
    assert parse_health_payload({"status": "healthy"})[0]
    assert not parse_health_payload({"status": "down"})[0]
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
        "log_dir:",
        _gateway_log_dir(),
    )
