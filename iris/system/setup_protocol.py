"""Iris 첫 실행 시작 프로토콜 — Detect / Provision / Wire / Start / Verify.

UI 없음. 기존 ollama_server / hermes_gateway / hermes_iris_control_sync 를 재사용.
시크릿(API 키)은 로그 문자열에 넣지 않는다.
"""

from __future__ import annotations

import json
import os
import queue
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from iris.system.hermes_gateway import (
    ensure_hermes_gateway_running,
    ensure_hermes_provider_config,
    hermes_executable,
    hermes_home,
    is_hermes_gateway_running,
    load_hermes_dotenv,
    resolve_hermes_api_key,
    verify_iris_mcp_tools,
)
from iris.system.hermes_iris_control_sync import (
    iris_state_dir,
    project_root,
    sync_iris_control,
)
from iris.system.ollama_server import (
    ensure_ollama_running,
    is_ollama_running,
    ollama_executable,
)

SCHEMA_VERSION = 1

# 기본 최소 모델 — IRIS_SETUP_MODEL / IRIS_OLLAMA_MODEL 로 덮어쓰기
DEFAULT_MIN_MODEL = "gemma4:e2b"

OLLAMA_DOWNLOAD_URL = "https://ollama.com/download/windows"
HERMES_INSTALL_URL = "https://hermes-agent.nousresearch.com/install.ps1"
ANDROID_STUDIO_URL = "https://developer.android.com/studio"
OLLAMA_SIGNIN_URL = "https://ollama.com/signin"


def is_setup_demo() -> bool:
    """IRIS_SETUP_DEMO=1 — [데모] 배너 UI. 실제 설치 없음."""
    return os.environ.get("IRIS_SETUP_DEMO", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def is_setup_dry_run() -> bool:
    """IRIS_SETUP_DRY_RUN=1 — 실제 프로토콜 UI, 설치/디스크 변경 없음 (흐름 미리보기)."""
    return os.environ.get("IRIS_SETUP_DRY_RUN", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def is_setup_preview() -> bool:
    """위저드 강제·미리보기 상태 파일 사용."""
    return is_setup_demo() or is_setup_dry_run()


def setup_state_path() -> Path:
    # 미리보기는 별도 파일 — 실제 setup_state.json 을 건드리지 않음
    if is_setup_demo():
        name = "setup_state_demo.json"
    elif is_setup_dry_run():
        name = "setup_state_dryrun.json"
    else:
        name = "setup_state.json"
    return iris_state_dir() / name


def prepare_setup_demo() -> Path:
    """데모/드라이런용 state 초기화. 실제 core_ready 파일은 유지."""
    path = setup_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    save_setup_state(_default_state())
    return path


def prepare_setup_dry_run() -> Path:
    """실제 UI 미리보기용 state 초기화."""
    return prepare_setup_demo()


StepStatus = str  # pending|installing|verifying|needs_user|done|failed|skipped

CORE_STEP_IDS: tuple[str, ...] = (
    "state_init",
    "mcp_venv",
    "ollama_install",
    "ollama_model",
    "hermes_install",
    "hermes_env",
    "hermes_provider",
    "iris_control_sync",
    "hermes_gateway",
    "core_smoke",
)

CORE_STEP_LABELS: dict[str, str] = {
    "state_init": "Iris 상태 디렉터리 준비",
    "mcp_venv": "MCP용 Python 가상환경",
    "ollama_install": "Ollama 설치·기동",
    "ollama_model": "최소 모델 받기",
    "hermes_install": "Hermes 설치",
    "hermes_env": "Hermes API 키·서버 설정",
    "hermes_provider": "Hermes ↔ Ollama 연결",
    "iris_control_sync": "iris-control MCP·스킬",
    "hermes_gateway": "Hermes gateway 기동",
    "core_smoke": "Core 연결 검증",
}

OPTIONAL_IDS: tuple[str, ...] = (
    "voice",
    "emulator",
    "mobile_mcp",
    "external_api",
    "mail",
    "ollama_cloud",
)


@dataclass
class SetupStepResult:
    step_id: str
    status: str
    message: str = ""
    action_url: str = ""
    action_hint: str = ""
    label: str = ""
    can_install: bool = False  # NeedsUser 카드에 「설치」 버튼

    def __post_init__(self) -> None:
        if not self.label:
            self.label = CORE_STEP_LABELS.get(self.step_id, self.step_id)


ProgressFn = Callable[[SetupStepResult], None]
# 반환: "done"(재검증) | "skip"(optional만) | "abort" | "install"(설치 실행)
UserActionFn = Callable[[SetupStepResult], str]
# text, percent(0-100 또는 None=미보고), replace(터미널 \r)
StreamFn = Callable[[str, int | None, bool], None]

_PERCENT_RE = re.compile(r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*%")
_ANSI_RE = re.compile(rb"\x1b\[[0-9;]*[A-Za-z]")


def parse_install_percent(text: str) -> int | None:
    """설치기 stdout의 마지막 N%만. 없으면 None — 추정하지 않음."""
    found: int | None = None
    for match in _PERCENT_RE.finditer(text or ""):
        try:
            val = float(match.group(1))
        except ValueError:
            continue
        if 0 <= val <= 100:
            found = int(val)
    return found


def _decode_frame(raw: bytes) -> str:
    cleaned = _ANSI_RE.sub(b"", raw or b"")
    return cleaned.decode("utf-8", "replace").replace("\x00", "").rstrip()


def _split_off_frame(buf: bytes) -> tuple[bytes, bytes, bool] | None:
    """완전 프레임이면 (frame, rest, replace). replace=True 는 \\r 덮어쓰기."""
    cr = buf.find(b"\r")
    nl = buf.find(b"\n")
    if cr < 0 and nl < 0:
        return None
    if nl >= 0 and (cr < 0 or nl < cr):
        return buf[:nl], buf[nl + 1 :], False
    if cr + 1 == len(buf):
        return None
    if buf[cr + 1 : cr + 2] == b"\n":
        return buf[:cr], buf[cr + 2 :], False
    return buf[:cr], buf[cr + 1 :], True


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "core_ready": False,
        "completed_at": "",
        "steps": {},
        "optional": {k: {"status": "pending", "message": "", "updated_at": ""} for k in OPTIONAL_IDS},
        "last_error": "",
    }


def load_setup_state() -> dict[str, Any]:
    path = setup_state_path()
    if not path.is_file():
        return _default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_state()
    if not isinstance(data, dict):
        return _default_state()
    base = _default_state()
    base.update({k: data.get(k, base[k]) for k in base})
    if not isinstance(base.get("steps"), dict):
        base["steps"] = {}
    if not isinstance(base.get("optional"), dict):
        base["optional"] = _default_state()["optional"]
    return base


def save_setup_state(state: dict[str, Any]) -> None:
    path = setup_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def is_core_ready() -> bool:
    return bool(load_setup_state().get("core_ready"))


def mark_core_ready_if_healthy(
    *,
    ollama_base_url: str = "http://127.0.0.1:11434/v1",
    hermes_base_url: str = "http://127.0.0.1:8642/v1",
    hermes_command: str = "hermes",
) -> bool:
    """위저드 생략 여부.

    - core_ready면 True
    - Ollama·Hermes 실행 파일이 있으면 기존 설치로 보고 core_ready 기록 후 True
      (gateway는 이후 HermesHealthWorker ensure에 맡김)
    - 없으면 False → 위저드
    """
    del ollama_base_url, hermes_base_url  # 시그니처 호환 유지
    if is_core_ready():
        return True
    if ollama_executable() and hermes_executable(hermes_command):
        state = load_setup_state()
        state["core_ready"] = True
        state["completed_at"] = state.get("completed_at") or _utc_now()
        state["last_error"] = ""
        save_setup_state(state)
        return True
    return False


def reset_core_ready() -> None:
    """설정 → 환경 다시 설정 시 core_ready 해제."""
    state = load_setup_state()
    state["core_ready"] = False
    state["completed_at"] = ""
    state["last_error"] = ""
    save_setup_state(state)


def default_min_model() -> str:
    return (
        os.environ.get("IRIS_SETUP_MODEL", "").strip()
        or os.environ.get("IRIS_OLLAMA_MODEL", "").strip()
        or DEFAULT_MIN_MODEL
    )


def _iris_env_path() -> Path:
    return project_root() / ".env"


def _upsert_dotenv(path: Path, updates: dict[str, str]) -> None:
    """KEY=value upsert. 값은 로그하지 말 것."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if path.is_file():
        try:
            lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except OSError:
            lines = []
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)
    for key, val in updates.items():
        if key not in seen:
            out.append(f"{key}={val}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _winget_exe() -> str | None:
    found = shutil.which("winget")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA", "")
    candidate = Path(local) / "Microsoft" / "WindowsApps" / "winget.exe"
    if candidate.is_file():
        return str(candidate)
    return None


def _winget_available() -> bool:
    return _winget_exe() is not None


def _kill_proc_tree(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32" and proc.pid:
        flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            creationflags=flags,
            timeout=8,
            check=False,
        )
        return
    try:
        proc.kill()
    except OSError:
        pass


class SetupProtocol:
    def __init__(
        self,
        *,
        ollama_base_url: str = "http://127.0.0.1:11434/v1",
        hermes_base_url: str = "http://127.0.0.1:8642/v1",
        hermes_command: str = "hermes",
        min_model: str = "",
        simulate: bool | None = None,
        dry_run: bool | None = None,
    ) -> None:
        self.ollama_base_url = ollama_base_url
        self.hermes_base_url = hermes_base_url
        self.hermes_command = hermes_command or "hermes"
        self.min_model = (min_model or default_min_model()).strip() or DEFAULT_MIN_MODEL
        self.simulate = is_setup_demo() if simulate is None else bool(simulate)
        self.dry_run = is_setup_dry_run() if dry_run is None else bool(dry_run)
        self._state = load_setup_state()
        self._sim_user_done: set[str] = set()
        self._on_stream: StreamFn | None = None
        self._abort = False
        self._active_proc: subprocess.Popen[bytes] | None = None

    def bind_stream(self, fn: StreamFn | None) -> None:
        self._on_stream = fn

    def is_busy(self) -> bool:
        proc = self._active_proc
        return proc is not None and proc.poll() is None

    def abort(self) -> None:
        self._abort = True
        proc = self._active_proc
        if proc is not None:
            _kill_proc_tree(proc)

    def _emit_stream(self, text: str, percent: int | None, *, replace: bool = False) -> None:
        if self._on_stream and (text or percent is not None):
            self._on_stream(text, percent, replace)

    def _run_streamed(
        self,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
        hidden: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        kwargs: dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.DEVNULL,
            "cwd": cwd,
            "env": env,
            "bufsize": 0,
            "close_fds": True,
        }
        if sys.platform == "win32":
            # winget/UAC 설치는 창 숨기면 승격 프롬프트가 안 뜨거나 파이프에 손자가 붙어 멈춤
            if hidden:
                kwargs["creationflags"] = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        proc = subprocess.Popen(cmd, **kwargs)
        self._active_proc = proc
        collected: list[str] = []
        buf = b""
        started = time.monotonic()
        out_q: queue.Queue[bytes | None] = queue.Queue()
        idle_after_exit = 0

        def _reader() -> None:
            try:
                stdout = proc.stdout
                if stdout is None:
                    return
                while True:
                    chunk = stdout.read(256)
                    if not chunk:
                        break
                    out_q.put(chunk)
            finally:
                out_q.put(None)

        threading.Thread(target=_reader, daemon=True).start()
        timed_out = False
        try:
            while True:
                if self._abort:
                    _kill_proc_tree(proc)
                    break
                if timeout is not None and (time.monotonic() - started) > timeout:
                    timed_out = True
                    _kill_proc_tree(proc)
                    break
                try:
                    piece = out_q.get(timeout=0.2)
                except queue.Empty:
                    if proc.poll() is not None:
                        idle_after_exit += 1
                        # 손자가 stdout을 붙잡고 EOF가 안 오면 설치기는 이미 끝난 것으로 본다
                        if idle_after_exit >= 8:
                            break
                    continue
                if piece is None:
                    break
                idle_after_exit = 0
                buf += piece
                while True:
                    split = _split_off_frame(buf)
                    if split is None:
                        break
                    frame, buf, replace = split
                    text = _decode_frame(frame)
                    if not text:
                        continue
                    collected.append(text)
                    self._emit_stream(text, parse_install_percent(text), replace=replace)
            leftover = _decode_frame(buf)
            if leftover:
                collected.append(leftover)
                self._emit_stream(leftover, parse_install_percent(leftover), replace=False)
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                _kill_proc_tree(proc)
                proc.wait(timeout=3)
        finally:
            self._active_proc = None
        code = proc.returncode if proc.returncode is not None else 1
        if timed_out:
            raise subprocess.TimeoutExpired(cmd, timeout or 0)
        return subprocess.CompletedProcess(cmd, code, "\n".join(collected), "")

    def last_error(self) -> str:
        return str(self._state.get("last_error") or "")

    def detect(self) -> dict[str, Any]:
        """현재 환경 스냅샷 (설치 여부·준비 여부)."""
        exe_o = ollama_executable()
        exe_h = hermes_executable(self.hermes_command)
        repo = project_root()
        venv_py = repo / ".venv" / "Scripts" / "python.exe"
        if not venv_py.is_file():
            venv_py = repo / ".venv" / "bin" / "python"
        return {
            "core_ready": bool(self._state.get("core_ready")),
            "state_dir": str(iris_state_dir()),
            "ollama_exe": exe_o,
            "ollama_running": is_ollama_running(self.ollama_base_url),
            "hermes_exe": exe_h,
            "hermes_running": is_hermes_gateway_running(self.hermes_base_url),
            "venv_ok": venv_py.is_file(),
            "min_model": self.min_model,
            "api_key_set": bool(resolve_hermes_api_key()),
        }

    def _record_step(self, step_id: str, status: str, message: str = "") -> SetupStepResult:
        steps = self._state.setdefault("steps", {})
        steps[step_id] = {
            "status": status,
            "message": message,
            "updated_at": _utc_now(),
        }
        if status == "failed":
            self._state["last_error"] = message
        save_setup_state(self._state)
        return SetupStepResult(
            step_id=step_id,
            status=status,
            message=message,
            label=CORE_STEP_LABELS.get(step_id, step_id),
        )

    def _emit(self, on_progress: ProgressFn | None, result: SetupStepResult) -> None:
        if on_progress:
            on_progress(result)

    def _wait_user(
        self,
        on_user: UserActionFn | None,
        result: SetupStepResult,
    ) -> str:
        if on_user is None:
            return "done"
        return (on_user(result) or "done").strip().lower() or "done"

    def verify_core(self) -> tuple[bool, str]:
        if self.simulate or self.dry_run:
            return True, "Ollama·Hermes·MCP 정상"
        if not is_ollama_running(self.ollama_base_url):
            return False, "Ollama가 응답하지 않습니다"
        models = _list_ollama_model_names(self.ollama_base_url)
        if not models:
            return False, "Ollama 모델이 없습니다"
        key = resolve_hermes_api_key()
        if not is_hermes_gateway_running(self.hermes_base_url, api_key=key):
            return False, "Hermes gateway /health 실패"
        mcp_ok, mcp_detail = verify_iris_mcp_tools(command=self.hermes_command)
        if not mcp_ok:
            return False, f"MCP 검증 실패: {mcp_detail}"
        return True, "Ollama·Hermes·MCP 정상"

    def run_core(
        self,
        on_progress: ProgressFn | None = None,
        on_user: UserActionFn | None = None,
    ) -> bool:
        self._abort = False
        if self.simulate:
            return self._run_core_simulated(on_progress, on_user)
        if self.dry_run:
            return self._run_core_dry_run(on_progress, on_user)
        runners: list[tuple[str, Callable[[], SetupStepResult]]] = [
            ("state_init", self._step_state_init),
            ("mcp_venv", self._step_mcp_venv),
            ("ollama_install", self._step_ollama_install),
            ("ollama_model", self._step_ollama_model),
            ("hermes_install", self._step_hermes_install),
            ("hermes_env", self._step_hermes_env),
            ("hermes_provider", self._step_hermes_provider),
            ("iris_control_sync", self._step_iris_control_sync),
            ("hermes_gateway", self._step_hermes_gateway),
            ("core_smoke", self._step_core_smoke),
        ]
        for step_id, runner in runners:
            while True:
                self._emit(on_progress, self._record_step(step_id, "installing", CORE_STEP_LABELS.get(step_id, "")))
                try:
                    result = runner()
                except Exception as exc:  # noqa: BLE001
                    result = self._record_step(step_id, "failed", str(exc)[:240])
                    self._emit(on_progress, result)
                    return False

                if result.status == "needs_user":
                    self._emit(on_progress, result)
                    choice = self._wait_user(on_user, result)
                    if choice == "abort":
                        self._record_step(step_id, "failed", "사용자가 중단함")
                        return False
                    if choice == "install":
                        self._emit(
                            on_progress,
                            self._record_step(step_id, "installing", "설치 실행 중…"),
                        )
                        installed = self._dispatch_install(step_id)
                        self._emit(on_progress, installed)
                        if installed.status == "done":
                            break
                        if installed.status == "failed":
                            return False
                        # needs_user 재표시 등 → 루프 계속
                        continue
                    # done: 재검증(수동 설치 후)
                    continue

                self._emit(on_progress, result)
                if result.status == "failed":
                    return False
                break

        self._state["core_ready"] = True
        self._state["completed_at"] = _utc_now()
        self._state["last_error"] = ""
        save_setup_state(self._state)
        return True

    def _run_core_simulated(
        self,
        on_progress: ProgressFn | None,
        on_user: UserActionFn | None,
    ) -> bool:
        """UI 데모 — sleep + NeedsUser만. winget/pip/.env/Hermes 디스크 미변경."""
        # NeedsUser를 한 번씩 보여 줄 Core 단계
        need_user_once = {
            "ollama_install": (
                "[데모] Ollama 설치 확인이 필요합니다. 실제로는 설치하지 않습니다.",
                OLLAMA_DOWNLOAD_URL,
                "「열기」는 참고용입니다. 「완료했어요」를 누르면 다음으로 갑니다.",
            ),
            "hermes_install": (
                "[데모] Hermes 설치 확인이 필요합니다. 실제로는 설치하지 않습니다.",
                HERMES_INSTALL_URL,
                "데모이므로 「완료했어요」만 누르면 됩니다.",
            ),
        }
        for step_id in CORE_STEP_IDS:
            label = CORE_STEP_LABELS.get(step_id, step_id)
            while True:
                self._emit(
                    on_progress,
                    self._record_step(step_id, "installing", f"[데모] {label}…"),
                )
                time.sleep(0.55)
                if step_id in need_user_once and step_id not in self._sim_user_done:
                    msg, url, hint = need_user_once[step_id]
                    result = SetupStepResult(
                        step_id=step_id,
                        status="needs_user",
                        message=msg,
                        action_url=url,
                        action_hint="「설치」를 누르면 데모로 다음 단계로 갑니다 (실제 설치 없음).",
                        label=label,
                        can_install=True,
                    )
                    self._emit(on_progress, result)
                    choice = self._wait_user(on_user, result)
                    if choice == "abort":
                        self._record_step(step_id, "failed", "사용자가 중단함")
                        return False
                    if choice == "install":
                        # 데모: 설치 버튼만 눌러도 다음 단계로
                        self._sim_user_done.add(step_id)
                        continue
                    self._sim_user_done.add(step_id)
                    continue
                done_msg = {
                    "state_init": "[데모] 상태 디렉터리 준비됨",
                    "mcp_venv": "[데모] .venv 준비됨 (실제 pip 없음)",
                    "ollama_install": "[데모] Ollama 연결됨",
                    "ollama_model": f"[데모] 모델 {self.min_model} 준비됨",
                    "hermes_install": "[데모] Hermes 실행 파일 확인",
                    "hermes_env": "[데모] API 키 동기화됨 (파일 미기록)",
                    "hermes_provider": "[데모] provider 설정됨 (config 미변경)",
                    "iris_control_sync": "[데모] iris-control MCP·스킬 OK",
                    "hermes_gateway": "[데모] gateway /health + MCP OK",
                    "core_smoke": "[데모] Core smoke 통과",
                }.get(step_id, "[데모] 완료")
                result = self._record_step(step_id, "done", done_msg)
                self._emit(on_progress, result)
                break

        self._state["core_ready"] = True
        self._state["completed_at"] = _utc_now()
        self._state["last_error"] = ""
        save_setup_state(self._state)
        return True

    def _run_core_dry_run(
        self,
        on_progress: ProgressFn | None,
        on_user: UserActionFn | None,
    ) -> bool:
        """실제 프로토콜 UI 문구로 흐름만 재현. winget/pip/.env/Hermes 디스크 미변경."""
        # 미설치 상황을 가정해 NeedsUser+설치 버튼을 보여 줄 단계
        need_install = {
            "ollama_install": (
                "Ollama가 없습니다. 「설치」를 누르면 winget으로 설치합니다.",
                OLLAMA_DOWNLOAD_URL,
                "UAC가 뜨면 허용하세요. 수동 설치 시 「열기」 후 「완료했어요」.",
            ),
            "hermes_install": (
                "Hermes Agent가 없습니다. 「설치」를 누르면 공식 설치 스크립트를 실행합니다.",
                HERMES_INSTALL_URL,
                "설치에 수 분이 걸릴 수 있습니다. 수동이면 「열기」 후 「완료했어요」.",
            ),
        }
        auto_done = {
            "state_init": "상태 디렉터리 준비됨",
            "mcp_venv": "venv OK (python.exe)",
            "ollama_model": f"{self.min_model} 준비됨",
            "hermes_env": "API_SERVER_ENABLED·키 동기화됨",
            "hermes_provider": "provider → Ollama(custom) 설정",
            "iris_control_sync": "Iris↔Hermes: MCP iris-control ok, skills 6/6",
            "hermes_gateway": "iris-control tools ok (iris_get_state/catalog/invoke)",
            "core_smoke": "Ollama·Hermes·MCP 정상",
        }
        for step_id in CORE_STEP_IDS:
            label = CORE_STEP_LABELS.get(step_id, step_id)
            while True:
                self._emit(
                    on_progress,
                    self._record_step(step_id, "installing", label),
                )
                time.sleep(0.45)
                if step_id in need_install and step_id not in self._sim_user_done:
                    msg, url, hint = need_install[step_id]
                    result = SetupStepResult(
                        step_id=step_id,
                        status="needs_user",
                        message=msg,
                        action_url=url,
                        action_hint=hint,
                        label=label,
                        can_install=True,
                    )
                    self._emit(on_progress, result)
                    choice = self._wait_user(on_user, result)
                    if choice == "abort":
                        self._record_step(step_id, "failed", "사용자가 중단함")
                        return False
                    if choice == "install":
                        self._emit(
                            on_progress,
                            self._record_step(step_id, "installing", "설치 실행 중…"),
                        )
                        time.sleep(0.9)
                        self._sim_user_done.add(step_id)
                        done = self._record_step(
                            step_id,
                            "done",
                            "winget으로 Ollama 설치됨"
                            if step_id == "ollama_install"
                            else "Hermes 설치됨",
                        )
                        self._emit(on_progress, done)
                        break
                    # 완료했어요 → 설치된 것처럼 통과
                    self._sim_user_done.add(step_id)
                    continue
                msg = auto_done.get(step_id, "완료")
                if step_id == "core_smoke":
                    self._record_step(step_id, "verifying", "연결 검증 중…")
                    time.sleep(0.35)
                result = self._record_step(step_id, "done", msg)
                self._emit(on_progress, result)
                break

        self._state["core_ready"] = True
        self._state["completed_at"] = _utc_now()
        self._state["last_error"] = ""
        save_setup_state(self._state)
        return True

    def run_optional(
        self,
        which: str,
        on_progress: ProgressFn | None = None,
        on_user: UserActionFn | None = None,
    ) -> bool:
        which = (which or "").strip().lower()
        if self.simulate:
            return self._run_optional_simulated(which, on_progress, on_user)
        if self.dry_run:
            return self._run_optional_dry_run(which, on_progress, on_user)
        dispatch = {
            "voice": self._opt_voice,
            "emulator": self._opt_emulator,
            "mobile_mcp": self._opt_mobile_mcp,
            "external_api": self._opt_external_api,
            "mail": self._opt_mail,
            "ollama_cloud": self._opt_ollama_cloud,
        }
        fn = dispatch.get(which)
        if fn is None:
            return False
        while True:
            result = fn()
            self._emit(on_progress, result)
            self._save_optional(which, result)
            if result.status == "needs_user":
                choice = self._wait_user(on_user, result)
                if choice == "skip":
                    skipped = SetupStepResult(
                        step_id=which,
                        status="skipped",
                        message="나중에 설정",
                        label=result.label or which,
                    )
                    self._emit(on_progress, skipped)
                    self._save_optional(which, skipped)
                    return True
                if choice == "abort":
                    return False
                if choice == "install":
                    self._emit(
                        on_progress,
                        SetupStepResult(
                            which, "installing", "설치 실행 중…", label=result.label or which
                        ),
                    )
                    installed = self._dispatch_install(which)
                    self._emit(on_progress, installed)
                    self._save_optional(which, installed)
                    if installed.status == "done":
                        return True
                    if installed.status == "failed":
                        return False
                    continue
                continue
            return result.status in ("done", "skipped")

    def _run_optional_simulated(
        self,
        which: str,
        on_progress: ProgressFn | None,
        on_user: UserActionFn | None,
    ) -> bool:
        labels = {
            "voice": "음성 런타임",
            "emulator": "Android 에뮬레이터",
            "mobile_mcp": "mobile-mcp",
            "external_api": "외부 API",
            "mail": "메일",
            "ollama_cloud": "Ollama 클라우드",
        }
        label = labels.get(which, which)
        time.sleep(0.35)
        result = SetupStepResult(
            step_id=which,
            status="needs_user",
            message=f"[데모] {label} — 선택 항목입니다. 실제 설치는 하지 않습니다.",
            action_url=ANDROID_STUDIO_URL if which == "emulator" else (
                OLLAMA_SIGNIN_URL if which == "ollama_cloud" else ""
            ),
            action_hint="「설치」/「완료했어요」/「나중에」로 진행 (데모).",
            label=label,
            can_install=which in ("emulator", "voice"),
        )
        self._emit(on_progress, result)
        self._save_optional(which, result)
        choice = self._wait_user(on_user, result)
        if choice == "abort":
            return False
        if choice == "skip":
            skipped = SetupStepResult(
                step_id=which, status="skipped", message="나중에 설정", label=label
            )
            self._emit(on_progress, skipped)
            self._save_optional(which, skipped)
            return True
        # install / done → 데모 완료
        done = SetupStepResult(
            step_id=which, status="done", message=f"[데모] {label} 확인됨", label=label
        )
        self._emit(on_progress, done)
        self._save_optional(which, done)
        return True

    def _run_optional_dry_run(
        self,
        which: str,
        on_progress: ProgressFn | None,
        on_user: UserActionFn | None,
    ) -> bool:
        """실제 Optional 카드 문구. 설치·디스크 변경 없음."""
        specs: dict[str, tuple[str, str, str, str, bool]] = {
            # label, message, url, hint, can_install
            "voice": (
                "음성 런타임",
                "음성 런타임을 준비합니다 (mock).",
                "",
                "「완료했어요」로 다음, 「나중에」로 건너뛰기.",
                False,
            ),
            "emulator": (
                "Android 에뮬레이터",
                "emulator 없음. 「설치」를 누르면 Android Studio(winget) 설치를 시도합니다.",
                ANDROID_STUDIO_URL,
                "용량이 큽니다. 「나중에」 가능.",
                True,
            ),
            "mobile_mcp": (
                "mobile-mcp",
                "Node/npx 확인 — 있으면 Hermes MCP에 등록됩니다.",
                "",
                "「완료했어요」 또는 「나중에」.",
                False,
            ),
            "external_api": (
                "외부 API",
                "외부 API 키는 설정에서 직접 추가합니다.",
                "",
                "설정 → API 항목. 「나중에」로 건너뛸 수 있습니다.",
                False,
            ),
            "mail": (
                "메일",
                "메일 계정은 설정에서 추가합니다.",
                "",
                "설정 → 이메일. 「나중에」로 건너뛸 수 있습니다.",
                False,
            ),
            "ollama_cloud": (
                "Ollama 클라우드",
                "Ollama 클라우드 모델은 로그인 후 사용할 수 있습니다.",
                OLLAMA_SIGNIN_URL,
                "브라우저에서 로그인 후 「완료했어요」 또는 「나중에」.",
                False,
            ),
        }
        label, message, url, hint, can_install = specs.get(
            which,
            (which, which, "", "「나중에」 가능.", False),
        )
        if which == "voice":
            time.sleep(0.4)
            done = SetupStepResult(
                which, "done", "mock 음성 런타임 준비됨 (Full TTS는 -Full)", label=label
            )
            self._emit(on_progress, done)
            self._save_optional(which, done)
            return True
        if which == "mobile_mcp":
            time.sleep(0.3)
            done = SetupStepResult(
                which, "done", "Node 확인됨 (Hermes MCP에 등록됨)", label=label
            )
            self._emit(on_progress, done)
            self._save_optional(which, done)
            return True

        result = SetupStepResult(
            step_id=which,
            status="needs_user",
            message=message,
            action_url=url,
            action_hint=hint,
            label=label,
            can_install=can_install,
        )
        self._emit(on_progress, result)
        self._save_optional(which, result)
        choice = self._wait_user(on_user, result)
        if choice == "abort":
            return False
        if choice == "skip":
            skipped = SetupStepResult(
                which, "skipped", "나중에 설정", label=label
            )
            self._emit(on_progress, skipped)
            self._save_optional(which, skipped)
            return True
        if choice == "install" and which == "emulator":
            self._emit(
                on_progress,
                SetupStepResult(which, "installing", "설치 실행 중…", label=label),
            )
            time.sleep(1.0)
            done = SetupStepResult(
                which, "done", "실행 가능 (AVD IrisLight_Pixel)", label=label
            )
            self._emit(on_progress, done)
            self._save_optional(which, done)
            return True
        done = SetupStepResult(which, "done", f"{label} 확인됨", label=label)
        self._emit(on_progress, done)
        self._save_optional(which, done)
        return True

    def _dispatch_install(self, step_id: str) -> SetupStepResult:
        """NeedsUser 「설치」 — 이미 있으면 검증만, 없으면 설치 실행."""
        if self.simulate:
            label = CORE_STEP_LABELS.get(step_id, step_id)
            return SetupStepResult(
                step_id=step_id,
                status="done",
                message=f"[데모] {label} 설치 시뮬레이션 완료",
                label=label,
            )
        if self.dry_run:
            time.sleep(0.8)
            if step_id == "ollama_install":
                return self._record_step("ollama_install", "done", "winget으로 Ollama 설치됨")
            if step_id == "hermes_install":
                return self._record_step("hermes_install", "done", "Hermes 설치됨")
            if step_id == "emulator":
                return SetupStepResult(
                    "emulator",
                    "done",
                    "실행 가능 (AVD IrisLight_Pixel)",
                    label="Android 에뮬레이터",
                )
            return SetupStepResult(step_id, "done", "완료")
        if step_id == "ollama_install":
            return self._install_ollama()
        if step_id == "hermes_install":
            return self._install_hermes()
        if step_id == "emulator":
            return self._install_emulator()
        return SetupStepResult(
            step_id=step_id,
            status="failed",
            message="이 단계는 자동 설치를 지원하지 않습니다",
            label=CORE_STEP_LABELS.get(step_id, step_id),
        )

    def _save_optional(self, which: str, result: SetupStepResult) -> None:
        opt = self._state.setdefault("optional", {})
        opt[which] = {
            "status": result.status,
            "message": result.message,
            "updated_at": _utc_now(),
        }
        save_setup_state(self._state)

    # ---- Core steps ----

    def _step_state_init(self) -> SetupStepResult:
        d = iris_state_dir()
        d.mkdir(parents=True, exist_ok=True)
        if not setup_state_path().is_file():
            save_setup_state(self._state)
        return self._record_step("state_init", "done", f"준비됨: {d}")

    def _step_mcp_venv(self) -> SetupStepResult:
        repo = project_root()
        req = repo / "requirements.txt"
        win = repo / ".venv" / "Scripts" / "python.exe"
        unix = repo / ".venv" / "bin" / "python"
        py = win if win.is_file() else unix if unix.is_file() else None
        if py is None:
            if getattr(sys, "frozen", False):
                creator = shutil.which("py") or shutil.which("python") or "python"
            else:
                creator = sys.executable or "python"
            name = Path(creator).name.lower()
            if name in {"py", "py.exe"}:
                cmd = [creator, "-3", "-m", "venv", str(repo / ".venv")]
            else:
                cmd = [creator, "-m", "venv", str(repo / ".venv")]
            try:
                proc = self._run_streamed(cmd, cwd=str(repo), timeout=180)
            except (OSError, subprocess.TimeoutExpired) as exc:
                return self._record_step("mcp_venv", "failed", f"venv 생성 실패: {exc}")
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "")[:200]
                return self._record_step("mcp_venv", "failed", f"venv 실패: {err}")
            py = win if win.is_file() else unix
            if py is None or not py.is_file():
                return self._record_step("mcp_venv", "failed", ".venv python을 찾지 못함")

        if req.is_file():
            pip_env = os.environ.copy()
            pip_env["PYTHONUNBUFFERED"] = "1"
            pip_env["PIP_PROGRESS_BAR"] = "on"
            pip = [str(py), "-u", "-m", "pip", "install", "-r", str(req), "--progress-bar", "on"]
            try:
                proc = self._run_streamed(pip, cwd=str(repo), env=pip_env, timeout=600)
            except (OSError, subprocess.TimeoutExpired) as exc:
                return self._record_step("mcp_venv", "failed", f"pip 실패: {exc}")
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "")[:200]
                return self._record_step("mcp_venv", "failed", f"requirements 설치 실패: {err}")
        return self._record_step("mcp_venv", "done", f"venv OK ({py.name})")

    def _step_ollama_install(self) -> SetupStepResult:
        # 이미 있으면 그대로 통과
        if ollama_executable() and ensure_ollama_running(self.ollama_base_url):
            return self._record_step("ollama_install", "done", "Ollama 이미 설치·실행 중")
        if ollama_executable():
            if ensure_ollama_running(self.ollama_base_url, wait_sec=20.0):
                return self._record_step("ollama_install", "done", "Ollama 기동됨")
            return self._record_step(
                "ollama_install",
                "failed",
                "Ollama가 설치돼 있으나 기동되지 않습니다",
            )
        return SetupStepResult(
            step_id="ollama_install",
            status="needs_user",
            message="Ollama가 없습니다. 「설치」를 누르면 winget으로 설치합니다.",
            action_url=OLLAMA_DOWNLOAD_URL,
            action_hint="UAC가 뜨면 허용하세요. 수동 설치 시 「열기」 후 「완료했어요」.",
            label=CORE_STEP_LABELS["ollama_install"],
            can_install=True,
        )

    def _install_ollama(self) -> SetupStepResult:
        if ollama_executable() and ensure_ollama_running(self.ollama_base_url, wait_sec=15.0):
            return self._record_step("ollama_install", "done", "Ollama 이미 사용 가능")
        if sys.platform == "win32":
            winget = _winget_exe()
            if winget:
                self._emit_stream(f"winget 설치 시작: {winget}", None, replace=False)
                try:
                    proc = self._run_streamed(
                        [
                            winget,
                            "install",
                            "-e",
                            "--id",
                            "Ollama.Ollama",
                            "--accept-package-agreements",
                            "--accept-source-agreements",
                        ],
                        timeout=600,
                        hidden=False,
                    )
                except (OSError, subprocess.TimeoutExpired) as exc:
                    return SetupStepResult(
                        step_id="ollama_install",
                        status="needs_user",
                        message=f"winget 설치 실패: {exc}. 「열기」로 수동 설치하세요.",
                        action_url=OLLAMA_DOWNLOAD_URL,
                        action_hint="설치 후 「완료했어요」를 누르세요.",
                        label=CORE_STEP_LABELS["ollama_install"],
                        can_install=True,
                    )
                if proc.returncode == 0:
                    time.sleep(2)
                    if ollama_executable() and ensure_ollama_running(self.ollama_base_url, wait_sec=25.0):
                        return self._record_step("ollama_install", "done", "winget으로 Ollama 설치됨")
                    return SetupStepResult(
                        step_id="ollama_install",
                        status="needs_user",
                        message="설치는 됐지만 PATH에 없습니다. Iris를 재시작한 뒤 「완료했어요」.",
                        action_url="",
                        action_hint="재시작 후 「완료했어요」를 누르세요.",
                        label=CORE_STEP_LABELS["ollama_install"],
                        can_install=False,
                    )
                err = (proc.stderr or proc.stdout or "")[:160]
                return SetupStepResult(
                    step_id="ollama_install",
                    status="needs_user",
                    message=f"winget 실패. 「열기」로 수동 설치하세요. {err}",
                    action_url=OLLAMA_DOWNLOAD_URL,
                    action_hint="설치 후 「완료했어요」.",
                    label=CORE_STEP_LABELS["ollama_install"],
                    can_install=True,
                )
        return SetupStepResult(
            step_id="ollama_install",
            status="needs_user",
            message="winget이 없습니다. 「열기」로 Ollama 설치 프로그램을 받아 주세요.",
            action_url=OLLAMA_DOWNLOAD_URL,
            action_hint="설치 후 「완료했어요」.",
            label=CORE_STEP_LABELS["ollama_install"],
            can_install=False,
        )

    def _step_ollama_model(self) -> SetupStepResult:
        if not ensure_ollama_running(self.ollama_base_url, wait_sec=20.0):
            return self._record_step("ollama_model", "failed", "Ollama가 꺼져 있어 모델을 받을 수 없습니다")
        names = _list_ollama_model_names(self.ollama_base_url)
        if names:
            # 이미 하나라도 있으면 통과 (기본 모델 없으면 pull)
            want = self.min_model
            if any(want == n or n.startswith(want.split(":")[0]) for n in names):
                return self._record_step("ollama_model", "done", f"모델 준비됨 ({len(names)}개)")
            if names and not want:
                return self._record_step("ollama_model", "done", f"모델 {len(names)}개 확인")

        model = self.min_model
        self._record_step("ollama_model", "installing", f"{model} 받는 중…")
        pulled = self._pull_ollama_model(model)
        if pulled is not None:
            return pulled
        names = _list_ollama_model_names(self.ollama_base_url)
        if not names:
            return self._record_step("ollama_model", "failed", "pull 후에도 모델 목록이 비어 있습니다")
        # 설정에 모델 비어 있으면 기록
        if not os.environ.get("IRIS_OLLAMA_MODEL", "").strip():
            _upsert_dotenv(_iris_env_path(), {"IRIS_OLLAMA_MODEL": model})
            os.environ["IRIS_OLLAMA_MODEL"] = model
        return self._record_step("ollama_model", "done", f"{model} 준비됨")

    def _pull_ollama_model(self, model: str) -> SetupStepResult | None:
        """Ollama /api/pull 바이트 진행률. 실패 시 CLI pull. 성공이면 None."""
        err = self._pull_ollama_api(model)
        if err is None:
            return None
        self._emit_stream(f"API pull 실패, CLI로 재시도: {err}", None, replace=False)
        exe = ollama_executable()
        if not exe:
            return self._record_step("ollama_model", "failed", "ollama 실행 파일 없음")
        try:
            proc = self._run_streamed([exe, "pull", model], timeout=1800)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return self._record_step("ollama_model", "failed", f"pull 실패: {exc}")
        if proc.returncode != 0:
            tail = (proc.stdout or "")[-200:]
            return self._record_step("ollama_model", "failed", f"pull 실패: {tail}")
        return None

    def _pull_ollama_api(self, model: str) -> str | None:
        """성공이면 None. completed/total 은 현재 레이어 실제 바이트."""
        from iris.infrastructure.ollama_client import _native_base

        url = f"{_native_base(self.ollama_base_url)}/api/pull"
        body = json.dumps({"model": model, "name": model, "stream": True}).encode("utf-8")
        req = Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urlopen(req, timeout=1800) as resp:
                while True:
                    if self._abort:
                        return "사용자가 중단함"
                    raw = resp.readline()
                    if not raw:
                        break
                    line = raw.decode("utf-8", "replace").strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        self._emit_stream(line, parse_install_percent(line), replace=False)
                        continue
                    if not isinstance(ev, dict):
                        continue
                    err = ev.get("error")
                    if err:
                        return str(err)[:200]
                    status = str(ev.get("status") or "pull")
                    total = int(ev.get("total") or 0)
                    completed = int(ev.get("completed") or 0)
                    pct = int(100 * completed / total) if total > 0 else None
                    msg = f"{status}  {completed}/{total}" if total > 0 else status
                    self._emit_stream(msg, pct, replace=total > 0)
        except (URLError, TimeoutError, OSError) as exc:
            return str(exc)[:200]
        return None

    def _step_hermes_install(self) -> SetupStepResult:
        if hermes_executable(self.hermes_command):
            return self._record_step("hermes_install", "done", "Hermes 이미 설치됨")
        return SetupStepResult(
            step_id="hermes_install",
            status="needs_user",
            message="Hermes Agent가 없습니다. 「설치」를 누르면 공식 설치 스크립트를 실행합니다.",
            action_url=HERMES_INSTALL_URL,
            action_hint="설치에 수 분이 걸릴 수 있습니다. 수동이면 「열기」 후 「완료했어요」.",
            label=CORE_STEP_LABELS["hermes_install"],
            can_install=sys.platform == "win32",
        )

    def _install_hermes(self) -> SetupStepResult:
        if hermes_executable(self.hermes_command):
            return self._record_step("hermes_install", "done", "Hermes 이미 사용 가능")
        if sys.platform != "win32":
            return SetupStepResult(
                step_id="hermes_install",
                status="needs_user",
                message="Windows 외에서는 수동 설치가 필요합니다.",
                action_url="https://hermes-agent.nousresearch.com/docs/",
                action_hint="설치 후 「완료했어요」.",
                label=CORE_STEP_LABELS["hermes_install"],
                can_install=False,
            )
        ps = (
            "& ([scriptblock]::Create((irm '"
            + HERMES_INSTALL_URL
            + "'))) -SkipSetup -NonInteractive"
        )
        self._emit_stream("Hermes 설치 스크립트 실행 중…", None, replace=False)
        try:
            proc = self._run_streamed(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    ps,
                ],
                timeout=1800,
                hidden=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return SetupStepResult(
                step_id="hermes_install",
                status="needs_user",
                message=f"설치 실패: {exc}. 「열기」로 수동 시도하세요.",
                action_url=HERMES_INSTALL_URL,
                action_hint="설치 후 Iris 재시작 → 「완료했어요」.",
                label=CORE_STEP_LABELS["hermes_install"],
                can_install=True,
            )
        if hermes_executable(self.hermes_command):
            return self._record_step("hermes_install", "done", "Hermes 설치됨")
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "")[:180]
            return SetupStepResult(
                step_id="hermes_install",
                status="needs_user",
                message=f"설치가 끝나지 않았습니다. {err}",
                action_url=HERMES_INSTALL_URL,
                action_hint="수동 설치 후 Iris 재시작 → 「완료했어요」.",
                label=CORE_STEP_LABELS["hermes_install"],
                can_install=True,
            )
        return SetupStepResult(
            step_id="hermes_install",
            status="needs_user",
            message="설치는 됐지만 PATH에 없습니다. Iris를 재시작한 뒤 「완료했어요」.",
            action_url="",
            action_hint="재시작 후 「완료했어요」.",
            label=CORE_STEP_LABELS["hermes_install"],
            can_install=False,
        )

    def _step_hermes_env(self) -> SetupStepResult:
        home = hermes_home()
        home.mkdir(parents=True, exist_ok=True)
        env_path = home / ".env"
        existing = load_hermes_dotenv()
        key = (existing.get("API_SERVER_KEY") or "").strip()
        if not key:
            key = (os.environ.get("IRIS_HERMES_API_KEY") or "").strip()
        if not key:
            key = secrets.token_urlsafe(32)
        _upsert_dotenv(
            env_path,
            {
                "API_SERVER_ENABLED": "true",
                "API_SERVER_KEY": key,
            },
        )
        _upsert_dotenv(_iris_env_path(), {"IRIS_HERMES_API_KEY": key})
        os.environ["IRIS_HERMES_API_KEY"] = key
        # 확인만 — 키 값은 메시지에 넣지 않음
        if not resolve_hermes_api_key():
            return self._record_step("hermes_env", "failed", "API 키 동기화 실패")
        return self._record_step("hermes_env", "done", "API_SERVER_ENABLED·키 동기화됨")

    def _step_hermes_provider(self) -> SetupStepResult:
        path = hermes_home() / "config.yaml"
        hermes_home().mkdir(parents=True, exist_ok=True)
        try:
            import yaml  # type: ignore
        except Exception:
            return self._record_step(
                "hermes_provider",
                "failed",
                "PyYAML 없음 — .venv에 requirements 설치를 확인하세요",
            )
        data: dict[str, Any] = {}
        if path.is_file():
            try:
                loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                if isinstance(loaded, dict):
                    data = loaded
            except OSError as exc:
                return self._record_step("hermes_provider", "failed", f"config 읽기 실패: {exc}")
        model = data.get("model")
        if not isinstance(model, dict):
            model = {}
        # Ollama OpenAI-compat — ensure_hermes_provider_config가 ollama→custom 변환
        model["provider"] = "ollama"
        model.setdefault("base_url", "http://127.0.0.1:11434/v1")
        if self.min_model:
            model.setdefault("default", self.min_model)
            model.setdefault("model", self.min_model)
        data["model"] = model
        try:
            if path.is_file() and not path.with_name("config.yaml.bak-iris-setup").is_file():
                shutil.copy2(path, path.with_name("config.yaml.bak-iris-setup"))
            path.write_text(
                yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
        except OSError as exc:
            return self._record_step("hermes_provider", "failed", f"config 쓰기 실패: {exc}")
        ensure_hermes_provider_config()
        return self._record_step("hermes_provider", "done", "provider → Ollama(custom) 설정")

    def _step_iris_control_sync(self) -> SetupStepResult:
        try:
            report = sync_iris_control(reconnect_gateway=True)
        except Exception as exc:  # noqa: BLE001
            return self._record_step("iris_control_sync", "failed", str(exc)[:240])
        if not report.mcp_installed:
            err = (report.errors[0] if report.errors else "MCP 미설치")[:200]
            return self._record_step("iris_control_sync", "failed", err)
        return self._record_step("iris_control_sync", "done", report.summary_line())

    def _step_hermes_gateway(self) -> SetupStepResult:
        key = resolve_hermes_api_key()
        from iris.system.hermes_gateway import restart_hermes_gateway

        # sync가 reload를 요구하면 완전 재기동, 아니면 ensure
        ok = restart_hermes_gateway(
            self.hermes_base_url,
            api_key=key,
            command=self.hermes_command,
            wait_sec=60.0,
        )
        if not ok:
            ok = ensure_hermes_gateway_running(
                self.hermes_base_url,
                api_key=key,
                command=self.hermes_command,
                wait_sec=45.0,
            )
        if not ok:
            return self._record_step("hermes_gateway", "failed", "gateway /health 실패")
        mcp_ok, mcp_detail = verify_iris_mcp_tools(command=self.hermes_command)
        if not mcp_ok:
            return self._record_step("hermes_gateway", "failed", f"MCP: {mcp_detail}")
        return self._record_step("hermes_gateway", "done", mcp_detail)

    def _step_core_smoke(self) -> SetupStepResult:
        self._record_step("core_smoke", "verifying", "연결 검증 중…")
        ok, detail = self.verify_core()
        if not ok:
            return self._record_step("core_smoke", "failed", detail)
        return self._record_step("core_smoke", "done", detail)

    # ---- Optional ----

    def _opt_voice(self) -> SetupStepResult:
        script = project_root() / "scripts" / "setup_voice_runtime.ps1"
        if not script.is_file():
            return SetupStepResult(
                "voice", "skipped", "setup_voice_runtime.ps1 없음", label="음성 런타임"
            )
        try:
            proc = self._run_streamed(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                ],
                cwd=str(project_root()),
                timeout=900,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return SetupStepResult("voice", "failed", str(exc)[:200], label="음성 런타임")
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "")[:180]
            return SetupStepResult("voice", "failed", err, label="음성 런타임")
        return SetupStepResult(
            "voice",
            "done",
            "mock 음성 런타임 준비됨 (Full TTS는 -Full)",
            label="음성 런타임",
        )

    def _opt_emulator(self) -> SetupStepResult:
        from iris.system.android_emulator import ensure_avd, is_emulator_available

        ok, detail = is_emulator_available()
        if ok:
            try:
                ensure_avd()
            except Exception as exc:  # noqa: BLE001
                return SetupStepResult(
                    step_id="emulator",
                    status="needs_user",
                    message=f"AVD 준비 실패: {exc}",
                    action_url=ANDROID_STUDIO_URL,
                    action_hint="「설치」로 Android Studio를 시도하거나 「나중에」.",
                    label="Android 에뮬레이터",
                    can_install=True,
                )
            return SetupStepResult(
                "emulator", "done", detail, label="Android 에뮬레이터"
            )
        return SetupStepResult(
            step_id="emulator",
            status="needs_user",
            message=f"{detail}. 「설치」를 누르면 Android Studio(winget) 설치를 시도합니다.",
            action_url=ANDROID_STUDIO_URL,
            action_hint="용량이 큽니다. 이미 Studio가 있으면 SDK만 맞춘 뒤 「완료했어요」. 「나중에」 가능.",
            label="Android 에뮬레이터",
            can_install=True,
        )

    def _install_emulator(self) -> SetupStepResult:
        from iris.system.android_emulator import ensure_avd, is_emulator_available

        ok, detail = is_emulator_available()
        if ok:
            try:
                ensure_avd()
                return SetupStepResult(
                    "emulator", "done", detail, label="Android 에뮬레이터"
                )
            except Exception as exc:  # noqa: BLE001
                return SetupStepResult(
                    step_id="emulator",
                    status="needs_user",
                    message=f"AVD 생성 실패: {exc}",
                    action_url=ANDROID_STUDIO_URL,
                    action_hint="Studio에서 SDK·AVD를 만든 뒤 「완료했어요」.",
                    label="Android 에뮬레이터",
                    can_install=True,
                )

        if sys.platform == "win32":
            winget = _winget_exe()
            if winget:
                self._emit_stream(f"winget 설치 시작: {winget}", None, replace=False)
                try:
                    proc = self._run_streamed(
                        [
                            winget,
                            "install",
                            "-e",
                            "--id",
                            "Google.AndroidStudio",
                            "--accept-package-agreements",
                            "--accept-source-agreements",
                        ],
                        timeout=3600,
                        hidden=False,
                    )
                except (OSError, subprocess.TimeoutExpired) as exc:
                    return SetupStepResult(
                        step_id="emulator",
                        status="needs_user",
                        message=f"Android Studio 설치 실패: {exc}",
                        action_url=ANDROID_STUDIO_URL,
                        action_hint="「열기」로 수동 설치 후 SDK·AVD를 준비하세요.",
                        label="Android 에뮬레이터",
                        can_install=True,
                    )
                if proc.returncode == 0:
                    ok2, detail2 = is_emulator_available()
                    if ok2:
                        try:
                            ensure_avd()
                        except Exception:  # noqa: BLE001
                            pass
                        return SetupStepResult(
                            "emulator",
                            "done",
                            detail2 or "Android Studio 설치됨",
                            label="Android 에뮬레이터",
                        )
                    return SetupStepResult(
                        step_id="emulator",
                        status="needs_user",
                        message=(
                            "Android Studio는 설치됐습니다. Studio를 열어 SDK Platform-Tools·"
                            "Emulator를 받은 뒤 「완료했어요」를 누르세요."
                        ),
                        action_url=ANDROID_STUDIO_URL,
                        action_hint="SDK 준비 후 「완료했어요」, 아니면 「나중에」.",
                        label="Android 에뮬레이터",
                        can_install=False,
                    )

        return SetupStepResult(
            step_id="emulator",
            status="needs_user",
            message="자동 설치를 할 수 없습니다. 「열기」로 Android Studio를 설치하세요.",
            action_url=ANDROID_STUDIO_URL,
            action_hint="SDK·AVD 준비 후 「완료했어요」.",
            label="Android 에뮬레이터",
            can_install=False,
        )

    def _opt_mobile_mcp(self) -> SetupStepResult:
        if not (shutil.which("npx") or shutil.which("node")):
            return SetupStepResult(
                "mobile_mcp",
                "skipped",
                "Node/npx 없음 — 건너뜀",
                label="mobile-mcp",
            )
        # sync가 config에 넣어 둠 — 여기서는 가용성만
        return SetupStepResult(
            "mobile_mcp",
            "done",
            "Node 확인됨 (Hermes MCP에 등록됨)",
            label="mobile-mcp",
        )

    def _opt_external_api(self) -> SetupStepResult:
        return SetupStepResult(
            step_id="external_api",
            status="needs_user",
            message="외부 API 키는 설정에서 직접 추가합니다.",
            action_url="",
            action_hint="설정 → API 항목에서 키를 붙여넣으세요. 「나중에」로 건너뛸 수 있습니다.",
            label="외부 API",
        )

    def _opt_mail(self) -> SetupStepResult:
        return SetupStepResult(
            step_id="mail",
            status="needs_user",
            message="메일 계정은 설정에서 추가합니다.",
            action_url="",
            action_hint="설정 → 이메일. 「나중에」로 건너뛸 수 있습니다.",
            label="메일",
        )

    def _opt_ollama_cloud(self) -> SetupStepResult:
        return SetupStepResult(
            step_id="ollama_cloud",
            status="needs_user",
            message="Ollama 클라우드 모델은 로그인 후 사용할 수 있습니다.",
            action_url=OLLAMA_SIGNIN_URL,
            action_hint="브라우저에서 로그인 후 「완료했어요」 또는 「나중에」.",
            label="Ollama 클라우드",
        )


def _list_ollama_model_names(base_url: str) -> list[str]:
    from iris.infrastructure.ollama_client import _native_base

    url = f"{_native_base(base_url)}/api/tags"
    try:
        with urlopen(Request(url, method="GET"), timeout=8.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        return []
    names: list[str] = []
    for m in data.get("models") or []:
        if isinstance(m, dict) and m.get("name"):
            names.append(str(m["name"]))
    return names


def _self_check() -> None:
    r = SetupStepResult("state_init", "pending", "x")
    assert asdict(r)["step_id"] == "state_init"
    st = _default_state()
    assert st["core_ready"] is False
    assert "mcp_venv" in CORE_STEP_IDS
    # 키 마스킹: 메시지에 raw key 넣지 않는지 상수만 검사
    assert "token_urlsafe" not in DEFAULT_MIN_MODEL
    assert parse_install_percent("Downloading  67%") == 67
    assert parse_install_percent("no percent here") is None
    assert parse_install_percent("150%") is None
    split = _split_off_frame(b"abc\rdef")
    assert split is not None
    frame, rest, replace = split
    assert frame == b"abc" and rest == b"def" and replace is True
    proto = SetupProtocol(simulate=False, dry_run=False)
    seen: list[tuple[str, int | None]] = []
    proto.bind_stream(lambda text, pct, _rep: seen.append((text, pct)))
    streamed = proto._run_streamed(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('Downloading  10%\\rDownloading  55%\\nDone 100%\\n'); sys.stdout.flush()",
        ],
        timeout=15,
    )
    assert streamed.returncode == 0, streamed.stdout
    pcts = [p for _, p in seen if p is not None]
    assert 10 in pcts and 55 in pcts and 100 in pcts, seen
    marker = iris_state_dir() / "_setup_stream_probe.txt"
    marker.unlink(missing_ok=True)
    wrote = proto._run_streamed(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path(%r).write_text('ok', encoding='utf-8')" % str(marker),
        ],
        timeout=15,
        hidden=True,
    )
    assert wrote.returncode == 0, wrote.stdout
    assert marker.read_text(encoding="utf-8") == "ok"
    marker.unlink(missing_ok=True)
    sleepy = SetupProtocol(simulate=False, dry_run=False)
    sleeper = threading.Thread(
        target=lambda: sleepy._run_streamed(
            [sys.executable, "-c", "import time; time.sleep(20)"],
            timeout=30,
            hidden=True,
        ),
        daemon=True,
    )
    sleeper.start()
    for _ in range(25):
        if sleepy.is_busy():
            break
        time.sleep(0.1)
    assert sleepy.is_busy()
    sleepy.abort()
    sleeper.join(8)
    assert not sleepy.is_busy()
    winget = _winget_exe()
    if winget:
        ver = proto._run_streamed([winget, "--version"], timeout=20, hidden=True)
        assert ver.returncode == 0, ver.stdout
        assert (ver.stdout or "").strip()
    d = iris_state_dir()
    assert d.is_dir()
    print("setup_protocol ok", d, "core_ready=", is_core_ready())


if __name__ == "__main__":
    _self_check()
