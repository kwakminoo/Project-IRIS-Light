from __future__ import annotations

import os
import subprocess
import tempfile
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

    def set_base_url(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client.set_base_url(self._base_url)

    def _venv_python(self) -> Path:
        return self._venv_path / "Scripts" / "python.exe"

    def is_running(self) -> bool:
        try:
            h = self._client.health()
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

    def ensure_started(self, *, mock_mode: bool = True, timeout_sec: float = 120.0) -> VoiceRuntimeStatus:
        if self.is_running():
            h = self._client.health()
            return VoiceRuntimeStatus(running=True, mock_mode=h.mock_mode, pid=h.pid)

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
                h = self._client.health()
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
