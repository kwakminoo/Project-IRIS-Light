"""Install the bundled Iris Agent Core and atomically select a verified slot.

Each slot keeps its absolute virtualenv paths. The prior selection remains
available for recovery. Older checkout helpers remain for compatibility.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from iris.infrastructure.agent_runtime import (
    ENGINE_SELECTION_FILE,
    IRIS_AGENT_CHECKOUT_NAME,
    apply_iris_agent_baseline_overlays,
    engine_slot_path,
    ensure_iris_agent_home,
    iris_agent_repo_dir,
    load_pinned_sha,
    load_upstream_url,
    read_engine_selection,
)
from iris.system import iris_agent_gateway as gw

HERMES_REPO_HTTPS = load_upstream_url()
StreamFn = Callable[[str], None]
_HERMES_PYTHON_MIN = (3, 11)
_HERMES_PYTHON_MAX_EXCLUSIVE = (3, 14)
_PY_LAUNCHER_FLAGS = ("-3.11", "-3.12", "-3.13")
_WANTED_EXTRAS = ("homeassistant", "mcp")
_PIP_FALLBACK_LIMIT = (
    "pip 폴백은 uv.lock pin을 재현하지 않습니다. "
    "선언된 extras 만 설치하며 requirements.txt 는 사용하지 않습니다."
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


def vendor_iris_agent_core_root() -> Path:
    """워크스페이스 vendor/iris-agent-core (owned frozen tree)."""
    return Path(__file__).resolve().parents[2] / "vendor" / "iris-agent-core"


def verify_owned_core_source(root: Path, *, bundled: bool = False) -> dict:
    """Check the shipped source identity and the inputs used for installation."""
    manifest = json.loads((root / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    if (
        manifest["package"] != "iris-agent-core"
        or manifest["package"] != project["name"]
        or manifest["version"] != project["version"]
        or manifest["entry_point"] != project["scripts"]["iris-agent"]
        or manifest["upstream_revision"] != _vendor_baseline_sha(root)
        or (bundled and manifest["upstream_revision"] != load_pinned_sha())
    ):
        raise ValueError("Iris Agent source identity does not match its manifest")
    required = {
        ".iris-agent-baseline", "LICENSE", "PROVENANCE.md", "iris_agent_cli/main.py",
        "pyproject.toml", "run_agent.py", "setup.py", "uv.lock",
    }
    hashes = manifest["sha256"]
    if not required.issubset(hashes):
        raise ValueError("Iris Agent manifest is missing required files")
    for name, digest in hashes.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError(f"Iris Agent manifest path is outside the source tree: {name}")
        content = path.read_text(encoding="utf-8").encode("utf-8")
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError(f"Iris Agent source integrity check failed: {name}")
    return manifest


def _vendor_baseline_sha(vendor: Path) -> str:
    """`.iris-agent-baseline` 또는 PROVENANCE 에서 pin SHA."""
    bas = vendor / ".iris-agent-baseline"
    if bas.is_file():
        try:
            lines = bas.read_text(encoding="utf-8").strip().splitlines()
        except OSError:
            lines = []
        if lines:
            sha = lines[0].strip().split()[0]
            if len(sha) >= 7 and all(c in "0123456789abcdefABCDEF" for c in sha):
                return sha
    prov = vendor / "PROVENANCE.md"
    if prov.is_file():
        try:
            text = prov.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        m = re.search(r"(?i)Pin SHA\s*[|:]\s*`?([0-9a-fA-F]{7,})`?", text)
        if m:
            return m.group(1)
    return ""


def _materialize_owned_core(staging: Path) -> subprocess.CompletedProcess[str]:
    """vendor/iris-agent-core → staging 복사. git/Nous fetch 불필요."""
    src = vendor_iris_agent_core_root()
    cmd = ["materialize", str(src), str(staging)]
    if not src.is_dir():
        return subprocess.CompletedProcess(cmd, 1, "", f"vendor missing: {src}")
    if not (src / "run_agent.py").is_file():
        return subprocess.CompletedProcess(cmd, 1, "", "run_agent.py missing in vendor")
    if not ((src / "iris_agent_cli").is_dir() or (src / "hermes_cli").is_dir()):
        return subprocess.CompletedProcess(
            cmd, 1, "", "neither iris_agent_cli nor hermes_cli in vendor"
        )
    pin = load_pinned_sha()
    bas = _vendor_baseline_sha(src)
    if bas and bas.lower() != pin.lower():
        return subprocess.CompletedProcess(
            cmd, 1, "", f"baseline stamp mismatch want={pin} got={bas}"
        )
    try:
        verify_owned_core_source(src, bundled=True)
        shutil.copytree(
            src,
            staging,
            ignore=shutil.ignore_patterns(
                "venv", ".venv", ".git", "__pycache__", "*.pyc", ".pytest_cache", "*.egg-info", ".env"
            ),
        )
        verify_owned_core_source(staging)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return subprocess.CompletedProcess(cmd, 1, "", str(exc))
    return subprocess.CompletedProcess(
        cmd, 0, f"materialized from vendor_iris_agent_core ({src}) pin={pin}", ""
    )


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


def iris_agent_python_range(repo: Path) -> PyRange:
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
        from iris.system.iris_agent_control_sync import project_root

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


def _checkout_artifact_prefix(name: str, *, keep_staging: str | None) -> bool:
    """iris-agent / hermes-agent 의 broken·trash·staging 잔존 여부 (live hermes-agent 제외)."""
    for base in (IRIS_AGENT_CHECKOUT_NAME, "hermes-agent"):
        if name.startswith(f"{base}.broken-") or name.startswith(f"{base}.trash-"):
            return True
        if name.startswith(f"{base}.staging-") and name != (keep_staging or ""):
            return True
        if name.startswith(f"{base}.prev-") or name.startswith(f"{base}.failed-"):
            return True
    return False


def force_retire_iris_agent(
    *,
    command: str = "hermes",
    keep_staging: str | None = None,
) -> str:
    """잠긴 iris-agent / .broken-* / staging-* 를 rename 으로 치우고 삭제 시도.

    keep_staging: 진행 중 staging 디렉터리명(예: iris-agent.staging-…)만 보존.
    레거시 hermes-agent live(Reference) 는 삭제하지 않는다.
    """
    home = gw.iris_agent_home()
    home.mkdir(parents=True, exist_ok=True)
    try:
        gw.stop_hermes_gateway(command, wait_sec=6.0)
    except Exception:  # noqa: BLE001
        pass

    notes: list[str] = []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    # live 는 제품 checkout(iris-agent)만. hermes-agent Reference 유지.
    targets = [home / IRIS_AGENT_CHECKOUT_NAME]
    try:
        targets.extend(
            sorted(
                p
                for p in home.iterdir()
                if p.is_dir() and _checkout_artifact_prefix(p.name, keep_staging=keep_staging)
            )
        )
    except OSError:
        pass

    for path in targets:
        if not path.exists():
            continue
        _kill_hermes_tree_holders(path)
        trash = home / f"{IRIS_AGENT_CHECKOUT_NAME}.trash-{stamp}-{path.name[-8:]}"
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
            p
            for p in home.iterdir()
            if p.is_dir()
            and (
                p.name.startswith(f"{IRIS_AGENT_CHECKOUT_NAME}.trash-")
                or p.name.startswith("hermes-agent.trash-")
            )
        )
        for old in trashes[:-_MAX_TRASH_KEEP]:
            shutil.rmtree(old, ignore_errors=True)
        for st in home.iterdir():
            if not st.is_dir() or st.name == (keep_staging or ""):
                continue
            if st.name.startswith(f"{IRIS_AGENT_CHECKOUT_NAME}.staging-") or st.name.startswith(
                "hermes-agent.staging-"
            ):
                shutil.rmtree(st, ignore_errors=True)
    except OSError:
        pass
    return "; ".join(notes) if notes else f"정리할 {IRIS_AGENT_CHECKOUT_NAME} 없음"


def _user_path_prepend(scripts: Path) -> None:
    if sys.platform != "win32" or not scripts.is_dir():
        return
    s = str(scripts)
    path = os.environ.get("PATH", "")
    if s.lower() not in path.lower():
        os.environ["PATH"] = s + os.pathsep + path
    # 제품 홈(또는 IRIS_AGENT_HOME) 아래 Scripts 만 레지스트리에 남긴다.
    real = gw.iris_agent_home()
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


def write_install_log(body: str, *, prefix: str = "iris-install", home: Path | None = None) -> Path:
    log_dir = (home if home is not None else gw.iris_agent_home()) / "logs"
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


@contextmanager
def iris_agent_install_lock(home: Path) -> Iterator[Path]:
    home.mkdir(parents=True, exist_ok=True)
    path = home / "iris-engine.lock"
    with path.open("a+b") as stream:
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise InstallBusy("다른 Iris Agent 설치 또는 복구가 진행 중입니다") from exc
        yield path


def _timeout_kind(exc: BaseException) -> str:
    kind = getattr(exc, "kind", "")
    return str(kind) if kind in ("idle", "hard") else "hard"


def _declared_optional_extras(pyproject: Path) -> frozenset[str]:
    if not pyproject.is_file():
        return frozenset()
    try:
        import tomllib

        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    optional = data.get("project", {}).get("optional-dependencies")
    if not isinstance(optional, dict):
        return frozenset()
    return frozenset(str(name) for name in optional)


def _wanted_extras(agent: Path) -> tuple[str, ...]:
    declared = _declared_optional_extras(agent / "pyproject.toml")
    return tuple(name for name in _WANTED_EXTRAS if name in declared)


def _uv_extra_args(extras: tuple[str, ...]) -> list[str]:
    args: list[str] = []
    for name in extras:
        args.extend(("--extra", name))
    return args


def _pip_editable_spec(extras: tuple[str, ...]) -> str:
    if not extras:
        return "."
    return ".[" + ",".join(extras) + "]"


_PROBE_PINS = (
    "aiohttp==3.14.3",
    "mcp==2.0.0",
    "httpx2==2.7.0",
    "starlette==1.3.1",
    "python-dotenv==1.2.2",
    "ruamel.yaml==0.18.16",
)


def _boost_probe_deps(venv_py: Path) -> subprocess.CompletedProcess[str]:
    return _run([str(venv_py), "-m", "pip", "install", *_PROBE_PINS], timeout=300.0)


def _probe_venv(venv_py: Path) -> tuple[bool, str]:
    probe = (
        "import importlib\n"
        "cli=None\n"
        "for _n in ('iris_agent_cli','hermes_cli'):\n"
        "    try:\n"
        "        cli=importlib.import_module(_n); break\n"
        "    except ImportError:\n"
        "        pass\n"
        "assert cli is not None\n"
        "import aiohttp, mcp\n"
        "print('ok')\n"
    )
    try:
        proc = _run(
            [str(venv_py), "-c", probe],
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
    live = home / IRIS_AGENT_CHECKOUT_NAME
    backup = home / f"{IRIS_AGENT_CHECKOUT_NAME}.prev-{stamp}"
    failed = home / f"{IRIS_AGENT_CHECKOUT_NAME}.failed-{stamp}"
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


def _activate_staged(home: Path, staging: Path) -> tuple[bool, str]:
    """Select a verified stable slot, retaining the previous active engine."""
    # ponytail: Keep older slots until cleanup can verify their sidecars have exited.
    try:
        current = iris_agent_repo_dir(home)
        _, last_previous = read_engine_selection(home)
        previous = current if current.is_dir() else last_previous
        _write_engine_selection(home, staging, previous if previous and previous.is_dir() else None)
    except (OSError, ValueError) as exc:
        return False, f"Iris Agent 전환 실패: {exc}"
    return True, staging.name


def _write_engine_selection(home: Path, active: Path, previous: Path | None) -> None:
    for slot in (active, previous):
        if slot is not None and (engine_slot_path(home, slot.name) != slot or not slot.is_dir()):
            raise ValueError(f"Iris Agent engine slot is unavailable: {slot}")
    config = {"active": active.name, "previous": previous.name if previous else None}
    pending = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=home, delete=False) as stream:
            pending = Path(stream.name)
            json.dump(config, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, home / ENGINE_SELECTION_FILE)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def rollback_iris_agent(home: Path) -> str:
    """Probe the recovery slot and select it without moving either installation."""
    from iris.engine._home import _probe_imports, checkout_python

    with iris_agent_install_lock(home):
        current, previous = read_engine_selection(home)
        if current is None or previous is None:
            raise RuntimeError("Iris Agent recovery slot is unavailable")
        if (previous / "SOURCE_MANIFEST.json").is_file():
            ok, detail = _probe_owned_slot(previous, home)
        else:
            python = checkout_python(previous)
            with tempfile.TemporaryDirectory(prefix="iris-recovery-", dir=home) as tmp:
                error = _probe_imports(Path(python), home=Path(tmp)) if python else None
            ok, detail = python is not None and error is None, str(error or "Recovery Python missing")
        if not ok:
            raise RuntimeError(f"Iris Agent recovery slot failed: {detail}")
        _write_engine_selection(home, previous, current if current.is_dir() else None)
        return previous.name


def _swap_in_staging(home: Path, staging: Path, stamp: str) -> tuple[bool, str]:
    live = home / IRIS_AGENT_CHECKOUT_NAME
    backup = home / f"{IRIS_AGENT_CHECKOUT_NAME}.prev-{stamp}"
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
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """pip/uv 는 무출력만으로 죽이지 않는다. 전체 시간 제한과 취소는 유지."""
    if run_streamed is not None:
        return run_streamed(
            cmd, cwd=cwd, timeout=None, hard_timeout=hard, hidden=True, env=env
        )
    return _run(cmd, cwd=cwd, timeout=hard, env=env)


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
    py: Path,
    uv: str | None,
    log: list[str],
    emit: Callable[[str], None],
    fail: Callable[..., InstallResult],
    run_streamed: Callable[..., subprocess.CompletedProcess[str]] | None,
    should_abort: Callable[[], bool] | None,
    model_check: Callable[[Path], None] | None = None,
) -> InstallResult:
    from iris.engine._home import _stripped_probe_env

    if not uv or not (staging / "uv.lock").is_file():
        _discard_tree(staging)
        return fail("lock", "Iris Agent 설치에 uv와 동봉된 uv.lock이 필요합니다", "Run IRIS Setup again to restore the bundled engine and uv.")
    venv = staging / "venv"
    env = _stripped_probe_env(home=None, python=py)
    env.pop("VIRTUAL_ENV", None)
    env["UV_PROJECT_ENVIRONMENT"] = str(venv)
    env["UV_LINK_MODE"] = "copy"
    cmd = [
        uv, "sync", "--locked", "--no-dev", "--no-python-downloads",
        *_uv_extra_args(_wanted_extras(staging)), "--python", str(py),
    ]
    emit("Iris Agent 잠금 의존성 설치 (uv sync --locked)…")
    try:
        proc = _run_dep(cmd, cwd=str(staging), run_streamed=run_streamed, hard=2400.0, env=env)
    except subprocess.TimeoutExpired as exc:
        _discard_tree(staging)
        return fail(_timeout_kind(exc), "uv sync 시간 초과", str(exc))
    except OSError as exc:
        _discard_tree(staging)
        return fail("exit", "uv 실행 실패", str(exc))
    log.extend((proc.stdout or "", proc.stderr or ""))
    if proc.returncode != 0:
        _discard_tree(staging)
        return fail("lock", "잠금 의존성 설치 실패", "\n".join(log))
    if should_abort and should_abort():
        _discard_tree(staging)
        return InstallResult(False, "사용자가 중단함", "cancel")

    ok, detail = _probe_owned_slot(staging, home)
    log.append(detail)
    if not ok:
        _discard_tree(staging)
        return fail("probe", "Iris Agent 실행 검증 실패", "\n".join(log))
    if model_check is not None:
        try:
            model_check(staging)
        except (OSError, RuntimeError, ValueError) as exc:
            _discard_tree(staging)
            return fail("probe", "Iris Agent 모델 호환성 검사 실패", str(exc))
    if should_abort and should_abort():
        _discard_tree(staging)
        return InstallResult(False, "사용자가 중단함", "cancel")
    ok, detail = _activate_staged(home, staging)
    if not ok:
        log.append(detail)
        return fail("probe", "최종 경로 실행 검증 실패", "\n".join(log))
    return InstallResult(True, f"Iris Agent 설치 성공 ({detail})", "ok")


def _probe_owned_slot(staging: Path, home: Path) -> tuple[bool, str]:
    from iris.engine._home import _stripped_probe_env
    from iris.engine.runtime import _SIDECAR_MAIN, _hello_ok

    try:
        manifest = verify_owned_core_source(staging)
        python = staging / ("venv/Scripts/python.exe" if sys.platform == "win32" else "venv/bin/python")
        check_imports = (
            "from importlib.metadata import version; from pathlib import Path; import sys; "
            "import run_agent, iris_agent_cli, mcp, openai; "
            "from run_agent import AIAgent; "
            "root = Path(sys.argv[1]); "
            "assert Path(run_agent.__file__).resolve() == root / 'run_agent.py'; "
            "assert Path(iris_agent_cli.__file__).resolve().is_relative_to(root); "
            "assert Path(sys.prefix).resolve() == root / 'venv'; "
            "assert version('iris-agent-core') == sys.argv[2]; "
            "print('iris-agent-core ' + version('iris-agent-core'))"
        )
        with tempfile.TemporaryDirectory(prefix="iris-ready-", dir=home) as tmp:
            probe_home = Path(tmp)
            env = _stripped_probe_env(home=probe_home, python=python)
            env.pop("IRIS_ENGINE_AGENT_MODULE", None)
            env["HERMES_DISABLE_LAZY_INSTALLS"] = "1"
            env["IRIS_ENGINE_GUI_PYTHON"] = sys.executable
            env["IRIS_ENGINE_LOG"] = str(probe_home / "sidecar.log")
            command = [str(python), "-I", "-c", check_imports, str(staging.resolve()), manifest["version"]]
            imported = _run(command, cwd=tmp, env=env, timeout=60)
            if imported.returncode != 0:
                return False, imported.stderr or imported.stdout or "AIAgent import failed"
            sidecar = subprocess.run(
                [str(python), "-I", str(_SIDECAR_MAIN)], input='{"t":"stop"}\n',
                cwd=tmp, env=env, capture_output=True, encoding="utf-8", errors="replace",
                timeout=30, **_no_window(),
            )
            if sidecar.returncode != 0 or not any(_hello_ok(line) for line in sidecar.stdout.splitlines()):
                return False, sidecar.stderr or sidecar.stdout or "Sidecar ready probe failed"
            return True, imported.stdout.strip()
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def combined_install_log_tail(*parts: str, limit: int = 1200) -> str:
    blob = "\n".join(p for p in parts if p)
    if len(blob) <= limit:
        return blob
    return blob[-limit:]


def last_bypass_log_path() -> str:
    return _LAST_BYPASS_LOG


def new_bypass_pip_log_path() -> Path:
    logs = gw.iris_agent_home() / "logs"
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
    extras = _wanted_extras(agent)
    cmd = [
        uv,
        "sync",
        "--frozen",
        "--active",
        "--python",
        str(venv_py),
        *_uv_extra_args(extras),
    ]
    try:
        return _run_pkg_install(cmd, cwd=str(agent), run_streamed=run_streamed, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(cmd, 1, "", str(exc))


def _guard_installed_agent(agent: Path) -> None:
    """우회 설치 직후 Iris Agent baseline overlay 1회. 실패해도 설치는 성공."""
    try:
        apply_iris_agent_baseline_overlays(agent)
    except Exception:
        return


def _checkout_pinned_sha(git: str, staging: Path, pin: str) -> subprocess.CompletedProcess[str]:
    """shallow clone 대신 init+fetch+checkout 으로 pin 만 받는다."""
    init = _run([git, "-c", "core.longpaths=true", "init", str(staging)], timeout=60.0)
    if init.returncode != 0:
        return init
    remote = _run(
        [git, "-C", str(staging), "remote", "add", "origin", HERMES_REPO_HTTPS],
        timeout=30.0,
    )
    if remote.returncode != 0:
        return remote
    fetch = _run(
        [
            git,
            "-c",
            "core.longpaths=true",
            "-C",
            str(staging),
            "fetch",
            "--depth",
            "1",
            "origin",
            pin,
        ],
        timeout=600.0,
    )
    if fetch.returncode != 0:
        return fetch
    return _run(
        [git, "-C", str(staging), "checkout", "--force", "FETCH_HEAD"],
        timeout=120.0,
    )


def _swap_staging_into_place(home: Path, staging: Path, agent: Path) -> str | None:
    """staging → iris-agent rename. 실패 시 메시지."""
    if agent.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        trash = home / f"{IRIS_AGENT_CHECKOUT_NAME}.trash-{stamp}-swap"
        try:
            agent.rename(trash)
            shutil.rmtree(trash, ignore_errors=True)
        except OSError as exc:
            return f"기존 {IRIS_AGENT_CHECKOUT_NAME} 교체 실패: {exc}"
    try:
        staging.rename(agent)
    except OSError as exc:
        return f"staging rename 실패: {exc}"
    return None


def install_iris_agent_with_system_python(
    *,
    command: str = "iris-agent",
    on_stream: StreamFn | None = None,
    run_streamed: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    should_abort: Callable[[], bool] | None = None,
    home: Path | None = None,
    sha: str | None = None,
    update: bool = False,
    model_check: Callable[[Path], None] | None = None,
) -> InstallResult:
    """Install the packaged Iris engine into a stable slot, then select it."""
    from iris.engine._home import probe_engine_python
    from iris.engine.types import EngineHome

    home = (Path(home) if home is not None else ensure_iris_agent_home()).resolve()

    def emit(msg: str) -> None:
        if on_stream:
            on_stream(msg)

    def fail(kind: str, prefix: str, body: str) -> InstallResult:
        path = write_install_log(body or prefix, prefix="iris-install", home=home)
        msg = format_install_failure(prefix, body, path, kind)
        emit(msg)
        return InstallResult(False, msg, kind, str(path))

    if should_abort and should_abort():
        return InstallResult(False, "사용자가 중단함", "cancel")
    try:
        with iris_agent_install_lock(home):
            current = iris_agent_repo_dir(home)
            if not update and probe_engine_python(EngineHome(home)) is None:
                return InstallResult(True, f"Iris Agent 사용 가능 ({current.name})")
            vendor = vendor_iris_agent_core_root()
            try:
                manifest = verify_owned_core_source(vendor, bundled=True)
                if sha is not None and sha.strip() != manifest["upstream_revision"]:
                    raise ValueError("Requested source revision does not match the bundle")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                return fail("source", "동봉된 Iris Agent 소스를 복구해야 합니다", f"{exc}\nRun IRIS Setup with a verified bundle.")
            replacing_reference = current.is_dir() and not (current / "SOURCE_MANIFEST.json").is_file()
            if replacing_reference and manifest.get("legacy_migration_approved") is not True:
                return fail("gate", "기존 Iris Agent 엔진 유지", "Owned engine is awaiting full product parity. The current installation remains selected.")
            if current.is_dir() and (update or replacing_reference) and model_check is None:
                return fail("probe", "Iris Agent 모델 검증이 필요합니다", "Select a model before updating the active engine.")
            want = iris_agent_python_range(vendor)
            py = ensure_system_python_winget(run_streamed=run_streamed, on_stream=on_stream, want=want)
            if py is None:
                return fail("python", "Iris Agent용 Python 없음", f"필요 범위: {manifest['python']}")
            scripts = Path(sys.executable).parent
            bundled_uv = scripts / ("uv.exe" if sys.platform == "win32" else "uv")
            uv = str(bundled_uv) if bundled_uv.is_file() else shutil.which("uv")
            if not uv:
                return fail("lock", "Iris Agent용 uv 없음", "Run IRIS Setup to install the packaged uv dependency.")
            staging = home / f"{IRIS_AGENT_CHECKOUT_NAME}.slot-{uuid.uuid4().hex[:16]}"
            emit(f"Iris Agent {manifest['version']} 설치 준비…")
            materialize = _materialize_owned_core(staging)
            if materialize.returncode != 0:
                _discard_tree(staging)
                return fail("source", "동봉된 Iris Agent 소스 준비 실패", materialize.stderr)
            log = [f"python={py}", f"uv={uv}", materialize.stdout]
            return _finish_staged_install(
                staging=staging, home=home, py=py, uv=uv, log=log, emit=emit,
                fail=fail, run_streamed=run_streamed, should_abort=should_abort, model_check=model_check,
            )
    except InstallBusy as exc:
        return fail("lock", "설치 잠금", str(exc))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return fail("exit", "Iris Agent 설치 실패", str(exc))


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
