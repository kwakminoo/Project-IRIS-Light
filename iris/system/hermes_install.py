"""Hermes Windows 설치 우회 — uv managed Python junction(WinError 448) 회피.

공식 install.ps1 은 시스템 Python을 거부하고 checkout 전용 uv managed
interpreter 만 받는다. OneDrive/필터 등으로 minor-version junction 생성이
실패하면(os error 448) 설치가 멈춘다.

우회: staging clone 후 검증에 성공하면 교체한다.
의존성은 uv.lock 이 있으면 uv sync --frozen 이 우선이고, 없을 때만 pip.
pip 는 uv.lock pin 을 재현하지 않으며 requirements.txt 는 쓰지 않는다.

Python: 처음엔 3.11 → 3.12 → 3.13 을 고르고, clone 한 뒤 그 저장소의 uv.lock·pyproject 가
요구하는 범위(hermes_python_range)를 벗어나면 다시 고른다. 2026-10-02 upstream 은
requires-python 이 >=3.11,<3.15 인데 의존성이 전부 `python_version >= '3.14'` 로 묶여
3.11 로는 핵심 패키지가 하나도 깔리지 않았다 (ruamel 없음, 실제 사례).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from iris.system import hermes_gateway as gw

HERMES_REPO_HTTPS = "https://github.com/NousResearch/hermes-agent.git"
StreamFn = Callable[[str], None]
_HERMES_PYTHON_MIN = (3, 11)
_HERMES_PYTHON_MAX_EXCLUSIVE = (3, 14)
_PY_LAUNCHER_FLAGS = ("-3.11", "-3.12", "-3.13")
_PIP_FALLBACK_LIMIT = (
    "pip 폴백은 uv.lock pin을 재현하지 않습니다. "
    "extras homeassistant,mcp 만 설치하며 requirements.txt 는 사용하지 않습니다."
)
_ERROR_LINE = re.compile(
    r"(?i)\b(error|exception|traceback|failed|winerror|timeout|permissionerror)\b"
)
_LAST_BYPASS_LOG: str = ""
# trash/staging 잔존 상한 (오래된 것부터 삭제)
_MAX_TRASH_KEEP = 3
_NEEDS_USER_MSG_LIMIT = 800
_NEEDS_USER_MSG_LINES = 12

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


def python_version(path: Path) -> tuple[int, int] | None:
    """Return a candidate interpreter's major/minor version."""
    try:
        proc = _run(
            [str(path), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"(?m)^(\d+)\.(\d+)\s*$", proc.stdout or "")
    return (int(match.group(1)), int(match.group(2))) if proc.returncode == 0 and match else None


PyRange = tuple[tuple[int, int], tuple[int, int]]  # (최소, 미만)


def is_supported_hermes_python(path: Path, want: PyRange | None = None) -> bool:
    lo, hi = want or (_HERMES_PYTHON_MIN, _HERMES_PYTHON_MAX_EXCLUSIVE)
    version = python_version(path)
    return version is not None and lo <= version < hi


def _ver(text: str) -> tuple[int, int]:
    major, minor = text.split(".")[:2]
    return int(major), int(minor)


def hermes_python_range(repo: Path) -> PyRange:
    """그 checkout 이 실제로 설치되는 Python 범위.

    pyproject 의 requires-python 과 uv.lock 의 supported-markers 중 좁은 쪽."""
    lo, hi = _HERMES_PYTHON_MIN, _HERMES_PYTHON_MAX_EXCLUSIVE
    lock = ""
    for name in ("pyproject.toml", "uv.lock"):
        try:
            text = (repo / name).read_text(encoding="utf-8", errors="replace")[:20000]
        except OSError:
            continue
        if name == "uv.lock":
            lock = text
        m = re.search(r'(?m)^requires-python\s*=\s*"([^"]+)"', text)
        if m:
            if (g := re.search(r">=\s*(\d+\.\d+)", m.group(1))):
                lo = _ver(g.group(1))
            if (g := re.search(r"<\s*(\d+)(?:\.(\d+))?", m.group(1))):
                hi = (int(g.group(1)), int(g.group(2) or 0))  # '<4' 처럼 주 버전만 쓰기도 한다
    m = re.search(r"(?ms)^supported-markers\s*=\s*\[(.*?)\]", lock)
    if m:
        markers = re.findall(r'"([^"]+)"', m.group(1))
        floors = [re.search(r"python_full_version\s*>=\s*'(\d+\.\d+)", x) for x in markers]
        if markers and all(floors):  # 모든 marker 에 하한이 있을 때만 좁힌다
            lo = max(lo, min(_ver(f.group(1)) for f in floors))
    if hi <= lo:
        # 상한이 없거나('>=3.11') 기본 상한보다 하한이 올라간 경우 — 빈 범위면 어떤 Python 도
        # 통과 못 해 설치가 늘 'Python 없음'으로 끝난다. 하한 버전 하나는 받게 둔다
        hi = (lo[0], lo[1] + 1)
    return lo, hi


def _launcher_flags(want: PyRange | None) -> list[str]:
    if want is None:
        return list(_PY_LAUNCHER_FLAGS)
    (lo_major, lo_minor), (hi_major, hi_minor) = want
    if lo_major != hi_major:
        return [f"-{lo_major}"]
    return [f"-{lo_major}.{m}" for m in range(lo_minor, hi_minor)]


def _py_launcher_python(want: PyRange | None = None) -> Path | None:
    if sys.platform != "win32":
        return None
    py = shutil.which("py")
    if not py:
        return None
    for flag in _launcher_flags(want):
        try:
            proc = _run([py, flag, "-c", "import sys; print(sys.executable)"], timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            continue
        line = (proc.stdout or "").strip().splitlines()
        if proc.returncode == 0 and line:
            p = Path(line[-1].strip())
            if p.is_file() and is_supported_hermes_python(p, want):
                return p
    return None


def find_bootstrap_python(want: PyRange | None = None) -> Path | None:
    """Hermes venv 베이스. 3.11 → 3.12 → 3.13 (want 가 있으면 그 범위). Iris .venv 는 그 다음."""
    launched = _py_launcher_python(want)
    if launched is not None:
        return launched
    try:
        from iris.system.hermes_iris_control_sync import project_root

        root = project_root()
    except Exception:  # noqa: BLE001
        root = Path.cwd()
    for cand in (
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    ):
        if cand.is_file() and is_supported_hermes_python(cand, want):
            return cand
    for name in [f"python{f[1:]}" for f in _launcher_flags(want)] + ["python3", "python"]:
        found = shutil.which(name)
        if found and is_supported_hermes_python(Path(found), want):
            return Path(found)
    if sys.executable:
        p = Path(sys.executable)
        if p.is_file() and is_supported_hermes_python(p, want):
            return p
    return None


def ensure_system_python_winget(
    *,
    run_streamed: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    on_stream: StreamFn | None = None,
    want: PyRange | None = None,
) -> Path | None:
    """winget 으로 Python 설치 시도 (기본 3.11, want 가 있으면 그 하한). 이미 있으면 find_bootstrap_python."""
    existing = find_bootstrap_python(want)
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
    major, minor = want[0] if want else _HERMES_PYTHON_MIN
    if on_stream:
        on_stream(f"시스템 Python {major}.{minor} 설치 (winget)…")
    cmd = [
        winget,
        "install",
        "-e",
        "--id",
        f"Python.Python.{major}.{minor}",
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
    return find_bootstrap_python(want)


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


def force_retire_hermes_agent(
    *,
    command: str = "hermes",
    keep_staging: str | None = None,
) -> str:
    """잠긴 hermes-agent / .broken-* / staging-* 를 rename 으로 치우고 삭제 시도.

    keep_staging: 진행 중 clone 디렉터리명(예: hermes-agent.staging-…)만 보존.
    """
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
                    or (
                        p.name.startswith("hermes-agent.staging-")
                        and p.name != (keep_staging or "")
                    )
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

    # 오래된 trash 최대 N개 · 남은 staging(보존분 제외) 전부 삭제
    try:
        trashes = sorted(
            p for p in home.iterdir() if p.is_dir() and p.name.startswith("hermes-agent.trash-")
        )
        for old in trashes[:-_MAX_TRASH_KEEP]:
            shutil.rmtree(old, ignore_errors=True)
        for st in home.iterdir():
            if (
                st.is_dir()
                and st.name.startswith("hermes-agent.staging-")
                and st.name != (keep_staging or "")
            ):
                shutil.rmtree(st, ignore_errors=True)
    except OSError:
        pass
    return "; ".join(notes) if notes else "정리할 hermes-agent 없음"


def _user_path_prepend(scripts: Path) -> None:
    if sys.platform != "win32" or not scripts.is_dir():
        return
    s = str(scripts)
    path = os.environ.get("PATH", "")
    if s.lower() not in path.lower():
        os.environ["PATH"] = s + os.pathsep + path
    # 실제 사용자 Hermes 홈만 레지스트리에 남긴다. Temp 등 테스트 홈은 이 프로세스만.
    real = Path(os.environ.get("LOCALAPPDATA") or "") / "hermes"
    try:
        scripts.resolve().relative_to(real.resolve())
    except (ValueError, OSError):
        return
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


class InstallBusy(RuntimeError):
    """다른 프로세스가 Hermes 설치 잠금을 잡고 있음."""


@dataclass
class InstallResult:
    ok: bool
    message: str
    kind: str = "ok"
    log_path: str = ""


def error_log_tail(text: str, *, max_lines: int = 12) -> str:
    """사용자 메시지용. 오류 줄이 있으면 그 꼬리, 없으면 로그 꼬리."""
    lines = [ln.rstrip() for ln in (text or "").splitlines() if ln.strip()]
    hits = [ln for ln in lines if _ERROR_LINE.search(ln)]
    chosen = (hits or lines)[-max_lines:]
    return "\n".join(chosen)


def _redact(text: str) -> str:
    from iris.system.setup_protocol import redact_secrets

    return redact_secrets(text or "")


def write_install_log(body: str, *, prefix: str = "iris-install") -> Path:
    log_dir = gw.hermes_home() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = log_dir / f"{prefix}-{stamp}.log"
    path.write_text(_redact(body), encoding="utf-8")
    return path


def format_install_failure(prefix: str, body: str, log_path: Path | None, kind: str) -> str:
    labels = {
        "cancel": "사용자 취소",
        "idle": "무출력 타임아웃",
        "hard": "전체 시간 제한",
        "exit": "비정상 종료",
        "probe": "실행 검증 실패",
        "lock": "다른 설치가 진행 중",
        "clone": "clone 실패",
        "python": "Python 없음",
    }
    tail = error_log_tail(body)
    where = f"로그: {log_path}" if log_path else "로그 파일 없음"
    return "\n".join(p for p in (f"{prefix} ({labels.get(kind, kind)})", tail, where) if p)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@contextmanager
def hermes_install_lock(home: Path) -> Iterator[Path]:
    home.mkdir(parents=True, exist_ok=True)
    path = home / "iris-hermes-install.lock"
    if path.is_file():
        try:
            pid = int((path.read_text(encoding="utf-8") or "0").strip() or "0")
        except (OSError, ValueError):
            pid = 0
        if _pid_alive(pid):
            raise InstallBusy(f"다른 Hermes 설치가 진행 중입니다 (pid {pid})")
    path.write_text(str(os.getpid()), encoding="utf-8")
    try:
        yield path
    finally:
        try:
            if path.is_file() and (path.read_text(encoding="utf-8") or "").strip() == str(os.getpid()):
                path.unlink()
        except OSError:
            pass


def _timeout_kind(exc: BaseException) -> str:
    kind = getattr(exc, "kind", "")
    return str(kind) if kind in ("idle", "hard") else "hard"


def _probe_venv(venv_py: Path) -> tuple[bool, str]:
    try:
        proc = _run(
            [str(venv_py), "-c", "import hermes_cli, aiohttp, mcp; print('ok')"],
            timeout=60.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"venv python 실행 실패: {exc}"
    blob = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()
    if proc.returncode != 0 or "ok" not in (proc.stdout or ""):
        return False, blob or f"exit {proc.returncode}"
    return True, f"venv import ok ({venv_py})"


def _discard_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _restore_backup(home: Path, stamp: str) -> None:
    live = home / "hermes-agent"
    backup = home / f"hermes-agent.prev-{stamp}"
    failed = home / f"hermes-agent.failed-{stamp}"
    if live.exists():
        try:
            _discard_tree(failed)
            live.rename(failed)
        except OSError:
            return
    if backup.exists() and not live.exists():
        try:
            backup.rename(live)
        except OSError:
            pass


def _retarget_moved_tree(root: Path, old: Path, new: Path) -> int:
    """venv·editable 설치가 staging 절대 경로를 들고 있으면 최종 경로로 바꾼다.

    pyvenv.cfg 의 home(베이스 Python)은 staging 아래가 아니면 그대로다.
    __pycache__ 는 옛 경로가 박혀 있으므로 지우고, 다음 import 가 다시 만든다.
    """
    pairs: list[tuple[bytes, bytes]] = []
    forms = [
        (str(old), str(new)),
        (old.as_posix(), new.as_posix()),
        # editable finder 는 Python 문자열로 백슬래시를 두 번 쓴다.
        (str(old).replace("\\", "\\\\"), str(new).replace("\\", "\\\\")),
    ]
    for src, dst in forms:
        if not src or src == dst:
            continue
        pairs.append((src.encode("utf-8"), dst.encode("utf-8")))
        pairs.append((src.encode("utf-16le"), dst.encode("utf-16le")))
    changed = 0
    for path in root.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix.lower() == ".pyc":
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        updated = data
        for src_b, dst_b in pairs:
            if src_b in updated:
                updated = updated.replace(src_b, dst_b)
        if updated != data:
            try:
                path.write_bytes(updated)
                changed += 1
            except OSError:
                continue
    for cache in root.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)
    return changed


def _activate_staged(home: Path, staging: Path, stamp: str, command: str) -> tuple[bool, str]:
    """교체하고 경로를 고친 뒤, 최종 위치에서만 실행 probe 한다."""
    old = Path(staging)
    swapped, note = _swap_in_staging(home, staging, stamp)
    if not swapped:
        return False, note
    live = home / "hermes-agent"
    _retarget_moved_tree(live, old, live)
    ok, detail = gw.probe_hermes_runtime(command=command, timeout_sec=30.0)
    if not ok:
        _restore_backup(home, stamp)
        return False, detail
    return True, detail


def _swap_in_staging(home: Path, staging: Path, stamp: str) -> tuple[bool, str]:
    live = home / "hermes-agent"
    backup = home / f"hermes-agent.prev-{stamp}"
    moved = False
    if live.exists():
        try:
            live.rename(backup)
            moved = True
        except OSError as exc:
            return False, f"기존 설치를 비키지 못했습니다: {exc}"
    try:
        staging.rename(live)
    except OSError as exc:
        if moved and backup.exists() and not live.exists():
            try:
                backup.rename(live)
            except OSError:
                pass
        return False, f"staging 교체 실패, 기존 설치 유지 시도: {exc}"
    return True, backup.name if moved else ""


def _run_dep(
    cmd: list[str],
    *,
    cwd: str,
    run_streamed: Callable[..., subprocess.CompletedProcess[str]] | None,
    hard: float,
) -> subprocess.CompletedProcess[str]:
    """pip/uv 는 무출력만으로 죽이지 않는다. 전체 시간 제한과 취소는 유지."""
    if run_streamed is not None:
        return run_streamed(cmd, cwd=cwd, timeout=None, hard_timeout=hard, hidden=True)
    return _run(cmd, cwd=cwd, timeout=hard)


def _pip_unmarked_core_deps(venv_py: Path, agent: Path) -> subprocess.CompletedProcess[str]:
    """3.14 마커를 떼고 core pin을 설치. 없으면 빈 성공."""
    text = ""
    try:
        text = (agent / "pyproject.toml").read_text(encoding="utf-8")
    except OSError as exc:
        return subprocess.CompletedProcess(["pip"], 1, "", str(exc))
    match = re.search(r"^dependencies = \[(.*?)^\]", text, re.S | re.M)
    specs: list[str] = []
    if match:
        for line in match.group(1).splitlines():
            line = line.split("#", 1)[0].strip().strip(",")
            found = re.match(r'"([^"]+)"', line)
            if not found:
                continue
            spec = found.group(1).split(";", 1)[0].strip()
            if "==" in spec:
                specs.append(spec)
    if not specs:
        return subprocess.CompletedProcess(["pip"], 0, "", "")
    return _run([str(venv_py), "-m", "pip", "install", *specs], timeout=900.0)


def _finish_staged_install(
    *,
    staging: Path,
    home: Path,
    stamp: str,
    py: Path,
    uv: str | None,
    command: str,
    log: list[str],
    emit: Callable[[str], None],
    fail: Callable[..., InstallResult],
    run_streamed: Callable[..., subprocess.CompletedProcess[str]] | None,
    should_abort: Callable[[], bool] | None,
) -> InstallResult:
    venv_dir = staging / "venv"
    emit("venv 생성…")
    venv_proc = _run([str(py), "-m", "venv", str(venv_dir)], timeout=180.0)
    log.append(venv_proc.stdout or "")
    log.append(venv_proc.stderr or "")
    if venv_proc.returncode != 0:
        _discard_tree(staging)
        return fail("exit", "venv 실패", "\n".join(log))
    venv_py = venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not venv_py.is_file():
        _discard_tree(staging)
        return fail("exit", "venv python 없음", str(venv_py))
    if should_abort and should_abort():
        _discard_tree(staging)
        return InstallResult(False, "사용자가 중단함", "cancel")

    lock = staging / "uv.lock"
    installed = False
    if uv and lock.is_file():
        emit("uv sync --frozen (homeassistant, mcp)…")
        cmd = [
            uv, "sync", "--frozen", "--no-dev",
            "--extra", "homeassistant", "--extra", "mcp",
            "--python", str(venv_py),
        ]
        started = time.monotonic()
        try:
            proc = _run_dep(cmd, cwd=str(staging), run_streamed=run_streamed, hard=2400.0)
        except subprocess.TimeoutExpired as exc:
            log.append(str(exc))
            _discard_tree(staging)
            return fail(_timeout_kind(exc), "uv sync 시간 초과", "\n".join(log))
        log.append(f"uv sync rc={proc.returncode} elapsed={time.monotonic() - started:.1f}s")
        log.append(proc.stdout or "")
        log.append(proc.stderr or "")
        installed = proc.returncode == 0
        if not installed:
            log.append(_PIP_FALLBACK_LIMIT)
            emit(_PIP_FALLBACK_LIMIT)
    else:
        log.append("uv.lock 또는 uv 없음 — " + _PIP_FALLBACK_LIMIT)
        emit(_PIP_FALLBACK_LIMIT)

    if not installed:
        emit("pip install -e .[homeassistant,mcp]…")
        pip_cmd = [str(venv_py), "-m", "pip", "install", "-e", ".[homeassistant,mcp]"]
        started = time.monotonic()
        try:
            pip = _run_dep(pip_cmd, cwd=str(staging), run_streamed=run_streamed, hard=2400.0)
        except subprocess.TimeoutExpired as exc:
            log.append(str(exc))
            _discard_tree(staging)
            return fail(_timeout_kind(exc), "pip 시간 초과", "\n".join(log))
        log.append(f"pip extras rc={pip.returncode} elapsed={time.monotonic() - started:.1f}s")
        log.append(pip.stdout or "")
        log.append(pip.stderr or "")
        if pip.returncode != 0:
            emit("extras 실패 — pip install -e . 후 aiohttp/mcp pin…")
            log.append(_PIP_FALLBACK_LIMIT)
            try:
                pip = _run_dep(
                    [str(venv_py), "-m", "pip", "install", "-e", "."],
                    cwd=str(staging),
                    run_streamed=run_streamed,
                    hard=2400.0,
                )
            except subprocess.TimeoutExpired as exc:
                log.append(str(exc))
                _discard_tree(staging)
                return fail(_timeout_kind(exc), "pip 시간 초과", "\n".join(log))
            log.append(pip.stdout or "")
            log.append(pip.stderr or "")
            if pip.returncode == 0:
                boost = _run(
                    [
                        str(venv_py), "-m", "pip", "install",
                        "aiohttp==3.14.3", "mcp==2.0.0", "httpx2==2.7.0", "starlette==1.3.1",
                        "python-dotenv==1.2.2", "ruamel.yaml==0.18.16",
                    ],
                    timeout=300.0,
                )
                log.append(boost.stdout or "")
                log.append(boost.stderr or "")
                if boost.returncode != 0:
                    _discard_tree(staging)
                    return fail("exit", "gateway/mcp 의존성 보강 실패", "\n".join(log))
                # pyproject pins are `python_version >= 3.14`. 3.12 editable
                # install then has zero runtime deps and gateway dies on import.
                ver = python_version(venv_py)
                if ver is not None and ver < (3, 14):
                    core = _pip_unmarked_core_deps(venv_py, staging)
                    log.append(core.stdout or "")
                    log.append(core.stderr or "")
                    if core.returncode != 0:
                        _discard_tree(staging)
                        return fail("exit", "Python<3.14 core deps 설치 실패", "\n".join(log))
        if pip.returncode != 0:
            _discard_tree(staging)
            return fail("exit", "pip 설치 실패", "\n".join(log))

    ok, detail = _probe_venv(venv_py)
    log.append(f"probe={ok} {detail}")
    if not ok:
        _discard_tree(staging)
        return fail("probe", "실행 검증 실패", "\n".join(log))

    runtime_ok, runtime_detail = _activate_staged(home, staging, stamp, command)
    if not runtime_ok:
        log.append(runtime_detail)
        return fail("probe", "최종 경로 실행 검증 실패", "\n".join(log))
    live_scripts = (home / "hermes-agent" / "venv" / ("Scripts" if sys.platform == "win32" else "bin"))
    _user_path_prepend(live_scripts)
    return InstallResult(True, f"우회 설치 성공 ({runtime_detail})", "ok")


def combined_install_log_tail(*parts: str, limit: int = 1200) -> str:
    blob = "\n".join(p for p in parts if p)
    if len(blob) <= limit:
        return blob
    return blob[-limit:]


def last_bypass_log_path() -> str:
    return _LAST_BYPASS_LOG


def new_bypass_pip_log_path() -> Path:
    logs = gw.hermes_home() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return logs / f"iris-bypass-pip-{stamp}.log"


def write_bypass_pip_log(stdout: str, stderr: str, *, path: Path | None = None) -> Path:
    global _LAST_BYPASS_LOG
    log_path = path or new_bypass_pip_log_path()
    blob = "\n".join(p for p in (stderr or "", stdout or "") if p)
    log_path.write_text(blob, encoding="utf-8", errors="replace")
    _LAST_BYPASS_LOG = str(log_path)
    return log_path


def format_pip_failure(stdout: str, stderr: str, *, log_path: Path | str) -> str:
    """pip 실패 메시지 — 앞(Obtaining…)이 아니라 꼬리 + 전체 로그 경로."""
    tail = combined_install_log_tail(stderr or "", stdout or "", limit=1200)
    lines = [ln for ln in tail.splitlines() if ln.strip()]
    short = "\n".join(lines[-_NEEDS_USER_MSG_LINES:]) if lines else "(로그 없음)"
    return f"pip 설치 실패 (로그: {log_path})\n{short}"


def format_runtime_failure(detail: str, *, log_path: Path | str) -> str:
    """우회 설치 후 probe/import 실패 — pip 실패와 동일하게 로그 경로 + 꼬리."""
    tail = combined_install_log_tail(detail or "", limit=1200)
    lines = [ln for ln in tail.splitlines() if ln.strip()]
    short = "\n".join(lines[-_NEEDS_USER_MSG_LINES:]) if lines else "(로그 없음)"
    return f"우회 설치 후 런타임 실패 (로그: {log_path})\n{short}"


def clip_needs_user_message(msg: str, *, limit: int = _NEEDS_USER_MSG_LIMIT) -> str:
    """NeedsUser 카드용 — 마지막 N줄·전체 limit자(꼬리). 전체 로그는 파일에만."""
    text = (msg or "").strip()
    if not text:
        return text
    lines = [ln for ln in text.splitlines() if ln.strip()]
    short = "\n".join(lines[-_NEEDS_USER_MSG_LINES:]) if lines else text
    if len(short) <= limit:
        return short
    return short[-limit:]


def should_skip_official_installer(
    *,
    prefer_bypass: bool,
    last_error: object = None,
) -> bool:
    """R1(a): 세션 prefer_bypass 또는 직전 last_error가 bypass/448이면 공식 생략."""
    if prefer_bypass:
        return True
    if isinstance(last_error, dict):
        kind = str(last_error.get("kind") or "").lower()
        if kind.startswith("bypass") or "448" in kind:
            return True
        if looks_like_uv_python_mount_failure(str(last_error.get("tail") or "")):
            return True
    return False


def _run_pkg_install(
    cmd: list[str],
    *,
    cwd: str,
    run_streamed: Callable[..., subprocess.CompletedProcess[str]] | None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """pip/uv 단계 — quiet 구간 idle 오탐 방지(hard만, idle 없음)."""
    if run_streamed is not None:
        return run_streamed(
            cmd,
            cwd=cwd,
            env=env,
            timeout=None,
            hard_timeout=3600.0,
            hidden=True,
        )
    return _run(cmd, cwd=cwd, env=env, timeout=3600.0)


def _try_uv_sync(
    agent: Path,
    venv_py: Path,
    venv_dir: Path,
    *,
    on_stream: StreamFn | None,
    run_streamed: Callable[..., subprocess.CompletedProcess[str]] | None,
) -> subprocess.CompletedProcess[str] | None:
    """uv.lock 있으면 uv sync --frozen (Hermes `venv/` 경로 유지). 없으면 None."""
    if not (agent / "uv.lock").is_file():
        return None
    uv = shutil.which("uv")
    if not uv:
        return None
    if on_stream:
        on_stream("uv sync --frozen (lock)…")
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(venv_dir)
    env["UV_PROJECT_ENVIRONMENT"] = str(venv_dir)
    cmd = [
        uv,
        "sync",
        "--frozen",
        "--active",
        "--python",
        str(venv_py),
        "--extra",
        "homeassistant",
        "--extra",
        "mcp",
    ]
    try:
        return _run_pkg_install(cmd, cwd=str(agent), run_streamed=run_streamed, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(cmd, 1, "", str(exc))


def _guard_installed_agent(agent: Path) -> None:
    """우회 설치로 hermes-agent 트리가 생긴 직후 options 가드 1회. 실패해도 설치는 성공."""
    try:
        from iris.system.hermes_ollama_guard import apply_ollama_options_guard

        apply_ollama_options_guard(agent)
    except Exception:
        return


def _swap_staging_into_place(home: Path, staging: Path, agent: Path) -> str | None:
    """staging → hermes-agent rename. 실패 시 메시지."""
    if agent.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        trash = home / f"hermes-agent.trash-{stamp}-swap"
        try:
            agent.rename(trash)
            shutil.rmtree(trash, ignore_errors=True)
        except OSError as exc:
            return f"기존 hermes-agent 교체 실패: {exc}"
    try:
        staging.rename(agent)
    except OSError as exc:
        return f"staging rename 실패: {exc}"
    return None


def install_hermes_with_system_python(
    *,
    command: str = "hermes",
    on_stream: StreamFn | None = None,
    run_streamed: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    should_abort: Callable[[], bool] | None = None,
) -> InstallResult:
    """staging 에 설치하고 import probe 통과 후에만 live 와 교체."""

    def _emit(msg: str) -> None:
        if on_stream:
            on_stream(msg)

    def _fail(kind: str, prefix: str, body: str, log_path: Path | None = None) -> InstallResult:
        path = log_path or write_install_log(body or prefix, prefix="iris-install")
        msg = format_install_failure(prefix, body, path, kind)
        _emit(msg)
        return InstallResult(False, msg, kind, str(path))

    if should_abort and should_abort():
        return InstallResult(False, "사용자가 중단함", "cancel")

    home = gw.hermes_home()
    try:
        with hermes_install_lock(home):
            already, already_detail = gw.probe_hermes_runtime(command=command, timeout_sec=30.0)
            if already:
                return InstallResult(True, f"이미 사용 가능 ({already_detail})", "ok")
            py = ensure_system_python_winget(run_streamed=run_streamed, on_stream=on_stream)
            if py is None:
                return _fail("python", "베이스 Python 없음", "py -3.11..3.13 / winget 3.11 실패")
            _emit(f"우회 설치: 베이스 Python = {py} ({python_version(py)})")
            log = [f"python={py} version={python_version(py)}", f"uv={shutil.which('uv') or '없음'}"]
            git = shutil.which("git")
            if not git:
                return _fail("clone", "git 없음", "git 이 PATH 에 없습니다")
            if should_abort and should_abort():
                return InstallResult(False, "사용자가 중단함", "cancel")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            staging = home / f"hermes-agent.staging-{stamp}"
            _discard_tree(staging)
            _emit("Hermes 저장소 HTTPS clone (staging)…")
            started = time.monotonic()
            clone = _run(
                [git, "-c", "core.longpaths=true", "clone", "--depth", "1", HERMES_REPO_HTTPS, str(staging)],
                timeout=600.0,
            )
            log.append(f"clone rc={clone.returncode} elapsed={time.monotonic() - started:.1f}s")
            log.append(clone.stdout or "")
            log.append(clone.stderr or "")
            if clone.returncode != 0 or not staging.is_dir():
                _discard_tree(staging)
                return _fail("clone", "git clone 실패", "\n".join(log))
            want = hermes_python_range(staging)
            have = python_version(py)
            log.append(f"repo python range={want} chosen={have}")
            if have is None or not (want[0] <= have < want[1]):
                _emit(f"이 Hermes 는 Python {want[0][0]}.{want[0][1]} 이상이 필요해요 — 다시 고릅니다…")
                py = ensure_system_python_winget(run_streamed=run_streamed, on_stream=on_stream, want=want)
                if py is None:
                    _discard_tree(staging)
                    return _fail("python", "맞는 Python 없음", f"필요 범위 {want}: py launcher·winget 실패")
                _emit(f"베이스 Python 다시 고름 = {py} ({python_version(py)})")
                log.append(f"rechosen python={py} version={python_version(py)}")
            return _finish_staged_install(
                staging=staging,
                home=home,
                stamp=stamp,
                py=py,
                uv=shutil.which("uv"),
                command=command,
                log=log,
                emit=_emit,
                fail=_fail,
                run_streamed=run_streamed,
                should_abort=should_abort,
            )
    except InstallBusy as exc:
        return _fail("lock", "설치 잠금", str(exc))



if __name__ == "__main__":
    assert looks_like_uv_python_mount_failure(
        "Failed to create Python minor version link directory\n"
        "cause: 경로에 신뢰할 수 없는 탑재 지점이 포함되어 있습니다. (os error 448)"
    )
    assert looks_like_uv_python_mount_failure("Python 3.11 not available")
    assert not looks_like_uv_python_mount_failure("connection refused")
    sample = "Obtaining file:///x\n" + ("n\n" * 20) + "ERROR: boom\n"
    assert "ERROR:" in error_log_tail(sample)
    assert "Obtaining" not in error_log_tail(sample)
    head = "Obtaining file:///tmp/hermes-agent\nInstalling build dependencies...\n"
    err = "ERROR: Could not find a version that satisfies the requirement missing-pkg\n"
    msg = format_pip_failure(head + ("...\n" * 80) + err, "", log_path="iris-bypass-pip-test.log")
    assert "ERROR:" in msg and "iris-bypass-pip" in msg
    assert not msg.strip().endswith("Obtaining file:///tmp/hermes-agent")
    assert should_skip_official_installer(
        prefer_bypass=False,
        last_error={"kind": "bypass_pip", "tail": "x"},
    )
    assert should_skip_official_installer(prefer_bypass=True, last_error=None)
    assert not should_skip_official_installer(prefer_bypass=False, last_error=None)
    rt = format_runtime_failure("probe timeout", log_path="iris-bypass-pip-rt.log")
    assert "런타임 실패" in rt and "iris-bypass-pip-rt" in rt
    clipped = clip_needs_user_message("line\n" * 40 + ("x" * 900))
    assert len(clipped) <= _NEEDS_USER_MSG_LIMIT
    print("hermes_install helpers ok", find_bootstrap_python())
