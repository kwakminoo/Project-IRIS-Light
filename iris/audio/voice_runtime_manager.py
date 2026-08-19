from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .voice_runtime_client import VoiceRuntimeClient, VoiceRuntimeError


@dataclass
class VoiceRuntimeStatus:
    running: bool
    mock_mode: bool
    pid: int


def _cancelled(cancel_event: object | None) -> bool:
    check = getattr(cancel_event, "is_set", None)
    return bool(check()) if callable(check) else False


class VoiceRuntimeProcessManager:
    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:18765",
        iris_root: Path,
        venv_rel: str = ".venv-voice",
    ) -> None:
        self._client = VoiceRuntimeClient(base_url=base_url)
        self._iris_root = iris_root
        self._venv_path = iris_root / venv_rel
        self._proc: subprocess.Popen | None = None
        self._base_url = base_url.rstrip("/")
        self._stderr_path: Path | None = None
        self._lifecycle_lock = threading.RLock()

    def set_base_url(self, base_url: str) -> None:
        # Settings changes must not wait behind a model startup loop.  String
        # replacement is atomic here; a cancelled bootstrap will observe the
        # new URL on its next health probe.
        self._base_url = base_url.rstrip("/")
        self._client.set_base_url(self._base_url)

    def _venv_python(self) -> Path:
        return self._venv_path / "Scripts" / "python.exe"

    def is_running(self, *, timeout_sec: float = 1.0) -> bool:
        try:
            h = self._client.health(timeout=max(0.1, float(timeout_sec)))
            return h.status == "ok"
        except Exception:
            return False

    def _read_stderr_tail(self, limit: int = 800) -> str:
        if self._stderr_path is None or not self._stderr_path.is_file():
            return ""
        try:
            raw = self._stderr_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return raw[-limit:].strip()

    def ensure_started(
        self,
        *,
        mock_mode: bool = False,
        timeout_sec: float = 120.0,
        cancel_event: object | None = None,
    ) -> VoiceRuntimeStatus:
        with self._lifecycle_lock:
            return self._ensure_started(
                mock_mode=mock_mode,
                timeout_sec=timeout_sec,
                cancel_event=cancel_event,
            )

    def _ensure_started(
        self,
        *,
        mock_mode: bool = False,
        timeout_sec: float = 120.0,
        cancel_event: object | None = None,
    ) -> VoiceRuntimeStatus:
        if _cancelled(cancel_event):
            raise VoiceRuntimeError("Voice runtime startup cancelled")
        if self.is_running(timeout_sec=1.0):
            h = self._client.health(timeout=1.0)
            if bool(h.mock_mode) == bool(mock_mode):
                return VoiceRuntimeStatus(running=True, mock_mode=h.mock_mode, pid=h.pid)
            # mock↔실모델 전환은 프로세스 환경변수라 재기동이 필요하다
            self.shutdown(timeout_sec=min(10.0, timeout_sec))
            deadline = time.monotonic() + 8.0
            while time.monotonic() < deadline and self.is_running(timeout_sec=1.0):
                if _cancelled(cancel_event):
                    raise VoiceRuntimeError("Voice runtime startup cancelled")
                time.sleep(0.3)

        py = self._venv_python()
        if not py.is_file():
            raise VoiceRuntimeError(
                f"Voice runtime requires venv: {py} not found. Please run scripts/setup_voice_runtime."
            )

        creationflags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

        env = os.environ.copy()
        env["VOICE_RUNTIME_MOCK"] = "1" if mock_mode else "0"

        # stderr를 남겨 조기 종료 원인(포트 충돌·ImportError)을 사용자에게 전달
        err_file = tempfile.NamedTemporaryFile(
            delete=False, suffix=".voice-runtime.err", mode="w", encoding="utf-8"
        )
        self._stderr_path = Path(err_file.name)
        err_file.close()
        err_handle = open(self._stderr_path, "w", encoding="utf-8")  # noqa: SIM115

        cmd = [str(py), "-m", "services.voice_runtime.app"]
        try:
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(self._iris_root),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=err_handle,
                creationflags=creationflags,
            )
        finally:
            try:
                err_handle.close()
            except Exception:
                pass

        deadline = time.monotonic() + float(timeout_sec)
        last_err: Optional[str] = None
        while time.monotonic() < deadline:
            if _cancelled(cancel_event):
                if self._proc is not None and self._proc.poll() is None:
                    self._proc.terminate()
                self._proc = None
                raise VoiceRuntimeError("Voice runtime startup cancelled")
            if self._proc.poll() is not None:
                detail = self._read_stderr_tail()
                hint = detail or "requirements-voice.txt / setup_voice_runtime 설치를 확인하세요."
                if "10048" in hint or "Address already in use" in hint or "address already in use" in hint.lower():
                    hint = (
                        f"포트가 이미 사용 중입니다 ({self._base_url}). "
                        "다른 프로세스를 종료하거나 Runtime URL 포트를 바꾸세요.\n"
                        f"{detail}"
                    )
                raise VoiceRuntimeError(f"Voice runtime process exited early. {hint}")
            try:
                h = self._client.health(timeout=1.0)
                return VoiceRuntimeStatus(running=True, mock_mode=h.mock_mode, pid=h.pid)
            except Exception as e:
                last_err = str(e)
                time.sleep(0.4)

        detail = self._read_stderr_tail()
        raise VoiceRuntimeError(
            f"Voice runtime failed to start: {last_err or ''}"
            + (f"\n{detail}" if detail else "")
        )

    def shutdown(self, *, timeout_sec: float = 10.0) -> None:
        with self._lifecycle_lock:
            self._shutdown(timeout_sec=timeout_sec)

    def _shutdown(self, *, timeout_sec: float = 10.0) -> None:
        try:
            self._client.shutdown()
        except Exception:
            pass
        if self._proc is not None:
            try:
                self._proc.wait(timeout=float(timeout_sec))
            except Exception:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
            self._proc = None
