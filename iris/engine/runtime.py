"""Process-wide engine handle.

Agent-readable:
- Owns: one child slot, one lock, and the process singleton.
- Does not: import Hermes or bind :8642.
- Talks to: iris.engine.types, the EnginePython probe, and _sidecar_main.py stdin/stdout.
- Extend via: Engine.ensure_ready / run_turn / shutdown.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from typing import Iterator

from iris.engine._home import (
    _stripped_probe_env,
    engine_python,
    install_into,
    probe_engine_python,
)
from iris.engine._sidecar import encode_host_command, parse_turn_event
from iris.engine.types import (
    EngineEnsureResult,
    EngineError,
    EngineErrorCode,
    EngineFailed,
    EngineHome,
    EngineReady,
    EngineSource,
    ExternalGateway,
    InternalSidecar,
    StatelessTurn,
    TurnCancelled,
    TurnEvent,
    TurnFailed,
    TurnFinished,
    parse_engine_source,
)
from iris.system.win_subprocess import no_window_kwargs

_SIDECAR_MAIN = Path(__file__).resolve().parent / "_sidecar_main.py"
_HELLO_TIMEOUT_SEC = 5.0
_TURN_TIMEOUT_SEC = 10.0
_STOP_TIMEOUT_SEC = 5.0
_GATEWAY_ENV_KEYS = (
    "API_SERVER_PORT",
    "API_SERVER_ENABLED",
    "API_SERVER_HOST",
    "API_SERVER_KEY",
)

_SHARED_LOCK = Lock()
_SHARED: Engine | None = None


def _settings_from_env() -> object:
    return SimpleNamespace(
        hermes_external_gateway=os.environ.get("IRIS_HERMES_EXTERNAL_GATEWAY", ""),
        hermes_base_url=os.environ.get("IRIS_HERMES_BASE_URL", ""),
        hermes_api_key=os.environ.get("IRIS_HERMES_API_KEY", ""),
    )


def _sidecar_env(home: EngineHome, python: Path) -> dict[str, str]:
    env = _stripped_probe_env(home=home, python=python)
    for key in _GATEWAY_ENV_KEYS:
        env.pop(key, None)
    env["HERMES_DISABLE_LAZY_INSTALLS"] = "1"
    env["IRIS_ENGINE_GUI_PYTHON"] = sys.executable
    log_path = Path(home) / "logs" / "host.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env["IRIS_ENGINE_LOG"] = str(log_path)
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _hello_ok(line: str) -> bool:
    try:
        raw = json.loads(line)
    except json.JSONDecodeError:
        return False
    return isinstance(raw, dict) and raw.get("t") == "hello" and bool(raw.get("ok"))


def _readline_timeout(stream: object, timeout: float) -> str:
    if stream is None:
        return ""
    box: list[str] = []

    def _read() -> None:
        try:
            box.append(stream.readline())  # type: ignore[union-attr]
        except Exception:
            box.append("")

    worker = threading.Thread(target=_read, daemon=True)
    worker.start()
    worker.join(timeout)
    if not box:
        return ""
    return box[0]


def _close_pipes(proc: subprocess.Popen[str]) -> None:
    for stream in (proc.stdin, proc.stdout, proc.stderr):
        if stream is None:
            continue
        try:
            stream.close()
        except OSError:
            continue


def _send_stop(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None or proc.stdin is None:
        return
    try:
        proc.stdin.write(encode_host_command("stop"))
        proc.stdin.flush()
    except OSError:
        return


def _terminate_child(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=_STOP_TIMEOUT_SEC,
                    **no_window_kwargs(),
                )
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()
        else:
            proc.terminate()
        try:
            proc.wait(timeout=_STOP_TIMEOUT_SEC)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=_STOP_TIMEOUT_SEC)
            except subprocess.TimeoutExpired:
                pass
    _close_pipes(proc)


def _failed(code: EngineErrorCode, detail: str) -> EngineFailed:
    return EngineFailed(EngineError(code, detail))


def _spawn_sidecar(home: EngineHome) -> EngineFailed | subprocess.Popen[str]:
    python = engine_python(home)
    if python is None:
        return _failed(EngineErrorCode.NOT_INSTALLED, "engine python is not installed")
    python_path = Path(python)
    try:
        proc = subprocess.Popen(
            [str(python_path), str(_SIDECAR_MAIN)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_sidecar_env(home, python_path),
            cwd=str(home),
            **no_window_kwargs(),
        )
    except OSError as exc:
        return _failed(EngineErrorCode.SPAWN_FAILED, f"sidecar spawn failed: {exc}")
    line = _readline_timeout(proc.stdout, _HELLO_TIMEOUT_SEC)
    if _hello_ok(line):
        return proc
    try:
        proc.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        pass
    code = proc.poll()
    _terminate_child(proc)
    if code == 2:
        return _failed(EngineErrorCode.WRONG_PYTHON, "sidecar refused this interpreter")
    if not line.strip():
        return _failed(EngineErrorCode.SPAWN_FAILED, "sidecar hello timed out or was empty")
    return _failed(EngineErrorCode.SPAWN_FAILED, f"sidecar hello was not valid: {line.strip()[:200]}")


class Engine:
    """One sidecar, one lock, one home."""

    def __init__(self, source: EngineSource) -> None:
        self._source = source
        self._lock = Lock()
        self._child: subprocess.Popen[str] | None = None

    @property
    def source(self) -> EngineSource:
        """Parsed source for this handle. Same object shared_engine() stored."""
        return self._source

    def ensure_ready(self) -> EngineEnsureResult:
        try:
            with self._lock:
                if self._child is not None:
                    if self._child.poll() is None:
                        return EngineReady(self._source, "engine is ready")
                    _close_pipes(self._child)
                    self._child = None
                if isinstance(self._source, ExternalGateway):
                    return EngineFailed(
                        EngineError(
                            EngineErrorCode.UNKNOWN,
                            "external Hermes gateway is not wired",
                        )
                    )
                if isinstance(self._source, InternalSidecar):
                    home = self._source.home
                    probe = probe_engine_python(home)
                    if probe is not None and (
                        probe.code == EngineErrorCode.NOT_INSTALLED
                        or engine_python(home) is None
                    ):
                        install_into(home)
                        probe = probe_engine_python(home)
                    if probe is not None:
                        return EngineFailed(probe)
                    spawned = _spawn_sidecar(home)
                    if isinstance(spawned, EngineFailed):
                        return spawned
                    self._child = spawned
                    return EngineReady(self._source, "engine is ready")
                return EngineFailed(
                    EngineError(
                        EngineErrorCode.NOT_INSTALLED,
                        "engine sidecar is not installed",
                    )
                )
        except Exception as exc:
            return EngineFailed(EngineError(EngineErrorCode.UNKNOWN, str(exc)))

    def _forget_child(self) -> None:
        child = self._child
        self._child = None
        if child is None:
            return
        if child.poll() is None:
            _terminate_child(child)
            return
        _close_pipes(child)

    def _write_turn(self, child: subprocess.Popen[str], turn: StatelessTurn) -> None:
        if child.stdin is None:
            raise OSError("sidecar stdin is missing")
        child.stdin.write(
            encode_host_command(
                "turn",
                messages=[
                    {"role": message.role.value, "content": message.content}
                    for message in turn.transcript.messages
                ],
                model=turn.model.model,
                provider=turn.model.provider,
            )
        )
        child.stdin.flush()

    def _read_turn_events(self, child: subprocess.Popen[str]) -> Iterator[TurnEvent]:
        while True:
            line = _readline_timeout(child.stdout, _TURN_TIMEOUT_SEC)
            if not line:
                if child.poll() is None:
                    yield TurnFailed(
                        EngineError(EngineErrorCode.PROTOCOL, "sidecar event timed out")
                    )
                    return
                self._forget_child()
                yield TurnFailed(
                    EngineError(EngineErrorCode.SPAWN_FAILED, "sidecar exited during turn")
                )
                return
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                yield TurnFailed(
                    EngineError(
                        EngineErrorCode.PROTOCOL,
                        f"sidecar event was not valid JSON: {line.strip()[:200]}",
                    )
                )
                return
            event = parse_turn_event(raw)
            yield event
            if isinstance(event, (TurnFinished, TurnFailed, TurnCancelled)):
                return

    def run_turn(self, turn: StatelessTurn) -> Iterator[TurnEvent]:
        try:
            if turn.cancel.cancelled():
                yield TurnCancelled()
                return
            ready = self.ensure_ready()
            if isinstance(ready, EngineFailed):
                yield TurnFailed(ready.error)
                return
            with self._lock:
                child = self._child
                if child is None or child.poll() is not None:
                    self._forget_child()
                    yield TurnFailed(
                        EngineError(EngineErrorCode.SPAWN_FAILED, "sidecar child is missing")
                    )
                    return
                try:
                    self._write_turn(child, turn)
                except (OSError, ValueError) as exc:
                    self._forget_child()
                    yield TurnFailed(
                        EngineError(
                            EngineErrorCode.SPAWN_FAILED,
                            f"sidecar stdin closed: {exc}",
                        )
                    )
                    return
                yield from self._read_turn_events(child)
        except Exception as exc:
            yield TurnFailed(EngineError(EngineErrorCode.UNKNOWN, str(exc)))

    def shutdown(self) -> None:
        try:
            with self._lock:
                child = self._child
                self._child = None
                if child is not None:
                    _send_stop(child)
                    _terminate_child(child)
        except Exception:
            return


def shared_engine() -> Engine:
    """Process singleton. First call parses settings. Later calls return the same object."""
    global _SHARED
    with _SHARED_LOCK:
        if _SHARED is None:
            _SHARED = Engine(parse_engine_source(_settings_from_env()))
        return _SHARED


def reset_shared_engine() -> None:
    global _SHARED
    with _SHARED_LOCK:
        engine = _SHARED
        _SHARED = None
    if engine is not None:
        engine.shutdown()
