from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
import venv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .voice_runtime_client import VoiceRuntimeClient, VoiceRuntimeError

log = logging.getLogger("iris.audio.voice_runtime")


@dataclass
class VoiceRuntimeStatus:
    running: bool
    mock_mode: bool
    pid: int


def _cancelled(cancel_event: object | None) -> bool:
    check = getattr(cancel_event, "is_set", None)
    return bool(check()) if callable(check) else False


def _no_window_kwargs() -> dict:
    from iris.system.win_subprocess import no_window_kwargs

    return no_window_kwargs()


class VoiceRuntimeProcessManager:
    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:18765",
        iris_root: Path,
        venv_rel: str = ".venv-voice",
    ) -> None:
        self._client = VoiceRuntimeClient(base_url=base_url)
        self._iris_root = Path(iris_root)
        self._venv_path = self._iris_root / venv_rel
        self._proc: subprocess.Popen | None = None
        self._base_url = base_url.rstrip("/")
        self._stderr_path: Path | None = None
        self._lifecycle_lock = threading.RLock()
        self._bootstrap_lock = threading.Lock()

    def set_base_url(self, base_url: str) -> None:
        # Settings changes must not wait behind a model startup loop.  String
        # replacement is atomic here; a cancelled bootstrap will observe the
        # new URL on its next health probe.
        self._base_url = base_url.rstrip("/")
        self._client.set_base_url(self._base_url)

    def _venv_python(self) -> Path | None:
        """`.venv-voice` 인터프리터 — Windows Scripts / Unix bin 모두 허용."""
        candidates = (
            self._venv_path / "Scripts" / "python.exe",
            self._venv_path / "bin" / "python",
            self._venv_path / "bin" / "python3",
        )
        for path in candidates:
            if path.is_file():
                return path
        return None

    def _host_can_run_mock(self) -> bool:
        try:
            import importlib.util

            return (
                importlib.util.find_spec("fastapi") is not None
                and importlib.util.find_spec("uvicorn") is not None
            )
        except Exception:
            return False

    def _bootstrap_venv(self, *, include_stt: bool) -> Path:
        """없으면 .venv-voice 생성 후 mock(+STT) 의존성 설치.

        마이크/설정에서 런타임을 켤 때 venv가 없으면 한 번 자동 구성해서
        'setup_voice_runtime 미실행'으로 활성화가 막히는 일을 막는다.
        """
        with self._bootstrap_lock:
            existing = self._venv_python()
            if existing is not None:
                return existing

            log.info("Bootstrapping voice runtime venv at %s", self._venv_path)
            self._venv_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                venv.EnvBuilder(with_pip=True).create(str(self._venv_path))
            except Exception as exc:  # noqa: BLE001
                raise VoiceRuntimeError(
                    f"Voice runtime venv create failed ({self._venv_path}): {exc}"
                ) from exc
            py = self._venv_python()
            if py is None:
                raise VoiceRuntimeError(
                    f"Voice runtime venv create failed: python missing under {self._venv_path}"
                )

            kw = _no_window_kwargs()
            subprocess.run(
                [str(py), "-m", "pip", "install", "--upgrade", "pip"],
                check=False,
                capture_output=True,
                timeout=300,
                **kw,
            )
            req_dir = self._iris_root / "services" / "voice_runtime"
            req_files = [req_dir / "requirements-voice-mock.txt"]
            if include_stt:
                req_files.append(req_dir / "requirements-voice.txt")
            for req in req_files:
                if not req.is_file():
                    continue
                proc = subprocess.run(
                    [str(py), "-m", "pip", "install", "-r", str(req)],
                    capture_output=True,
                    text=True,
                    timeout=1800 if include_stt else 600,
                    **kw,
                )
                if proc.returncode != 0:
                    detail = (proc.stderr or proc.stdout or "pip failed")[-500:]
                    raise VoiceRuntimeError(
                        f"Voice runtime 의존성 설치 실패 ({req.name}): {detail}"
                    )
            return py

    def _resolve_python(self, *, mock_mode: bool) -> Path:
        py = self._venv_python()
        if py is not None:
            return py

        if mock_mode and self._host_can_run_mock():
            # CI/개발: 메인 인터프리터에 fastapi가 있으면 mock 런타임으로 바로 기동
            return Path(sys.executable)

        try:
            return self._bootstrap_venv(include_stt=not mock_mode)
        except VoiceRuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise VoiceRuntimeError(
                f"Voice runtime requires venv: {self._venv_path} not found ({exc}). "
                "Please run scripts/setup_voice_runtime."
            ) from exc

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

        py = self._resolve_python(mock_mode=mock_mode)

        popen_kwargs: dict = {
            "cwd": str(self._iris_root),
            "stdout": subprocess.DEVNULL,
        }
        env = os.environ.copy()
        env["VOICE_RUNTIME_MOCK"] = "1" if mock_mode else "0"
        popen_kwargs["env"] = env

        # stderr를 남겨 조기 종료 원인(포트 충돌·ImportError)을 사용자에게 전달
        err_file = tempfile.NamedTemporaryFile(
            delete=False, suffix=".voice-runtime.err", mode="w", encoding="utf-8"
        )
        self._stderr_path = Path(err_file.name)
        err_file.close()
        err_handle = open(self._stderr_path, "w", encoding="utf-8")  # noqa: SIM115
        popen_kwargs["stderr"] = err_handle

        # 콘솔 창 없이 기동 (Windows)
        popen_kwargs.update(_no_window_kwargs())

        cmd = [str(py), "-m", "services.voice_runtime.app"]
        try:
            self._proc = subprocess.Popen(cmd, **popen_kwargs)
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
