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
import queue
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from typing import Callable, Iterator

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
    CancelToken,
    StatelessTurn,
    TurnCancelled,
    TurnEvent,
    TurnFailed,
    TurnFinished,
    parse_engine_source,
)
from iris.system.iris_agent_ollama_guard import looks_like_ollama_endpoint
from iris.system.win_subprocess import no_window_kwargs

_SIDECAR_MAIN = Path(__file__).resolve().parent / "_sidecar_main.py"
_HELLO_TIMEOUT_SEC = 5.0
# ponytail: coding turns can stay silent >3m while the model writes tool args (2026-10-30 tetris: 194s). Ceiling: still no sidecar heartbeat; raise again if real gaps exceed this.
_TURN_IDLE_SEC = 600.0
_CANCEL_POLL_SEC = 0.2
_WATCH_LOG = Path.home() / ".iris-light" / "logs" / "turn_end_watch.log"


def _watch_trace(msg: str) -> None:
    # Critical landing lines stay synchronous so measure can see them before exit.
    # Non-critical miss spam stays fire-and-forget to avoid log-lock freezes.
    line = f"pid={os.getpid()} host {msg}\n"
    critical = msg.startswith(("recv ", "read_turn_events", "run_turn started"))
    if not critical:

        def _write() -> None:
            try:
                _WATCH_LOG.parent.mkdir(parents=True, exist_ok=True)
                with _WATCH_LOG.open("a", encoding="utf-8") as fh:
                    fh.write(line)
            except Exception:
                return

        threading.Thread(target=_write, name="iris-host-watch", daemon=True).start()
        return
    try:
        _WATCH_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _WATCH_LOG.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        return


def _terminal_dir() -> Path:
    env = os.environ.get("IRIS_TERMINAL_DIR", "").strip()
    if env:
        return Path(env)
    # TEMP avoids AV/exclusive locks under ~/.iris-light/logs that wedge is_file().
    return Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".") / (
        "iris-sidecar-terminal"
    )


def _read_terminal_file_impl(hello_pid: int | None) -> str:
    """Sidecar writes done/fail here when the stdout pipe EINVAL.

    Open-try only — Path.is_file()/stat can block under Windows Defender while
    the sidecar creates the file, and a timed wrapper that abandons the reader
    then unlinks the only land path.
    """
    if hello_pid is None or hello_pid <= 0:
        return ""
    path = _terminal_dir() / f"{int(hello_pid)}.ndjson"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        return ""
    except OSError:
        return ""
    if not text.strip():
        return ""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    _watch_trace(
        f"recv terminal_file hello_pid={hello_pid} path={path.name} "
        f"chars={len(text.strip())}"
    )
    return text if text.endswith("\n") else text + "\n"


def _read_terminal_file(hello_pid: int | None, *, timeout: float = 0.25) -> str:
    """UI/timer helper. Prefer impl directly — do not abandon a reader mid-unlink."""
    del timeout  # kept for call-site compat; abandoned timed reads lose the file
    try:
        return _read_terminal_file_impl(hello_pid)
    except Exception:
        return ""

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
    # Unit 2: external-gateway env is ignored by parse_engine_source.
    return SimpleNamespace(
        hermes_base_url=os.environ.get("IRIS_HERMES_BASE_URL", ""),
        hermes_api_key=os.environ.get("IRIS_HERMES_API_KEY", ""),
    )


def _sidecar_env(home: EngineHome, python: Path) -> dict[str, str]:
    env = _stripped_probe_env(home=home, python=python)
    for key in _GATEWAY_ENV_KEYS:
        env.pop(key, None)
    env["HERMES_DISABLE_LAZY_INSTALLS"] = "1"
    env["IRIS_ENGINE_GUI_PYTHON"] = sys.executable
    # Unique per spawn so turn-end file poll cannot steal another sidecar's line.
    log_path = Path(home) / "logs" / f"sidecar-{time.time_ns()}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env["IRIS_ENGINE_LOG"] = str(log_path)
    env["PYTHONUNBUFFERED"] = "1"
    # Korean Windows defaults to cp949 for child stdio; parent pipes are utf-8.
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    terminal_dir = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".") / (
        "iris-sidecar-terminal"
    )
    terminal_dir.mkdir(parents=True, exist_ok=True)
    env["IRIS_TERMINAL_DIR"] = str(terminal_dir)
    os.environ["IRIS_TERMINAL_DIR"] = str(terminal_dir)
    return env


def _bind_terminal_udp() -> tuple[socket.socket, int]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(0.5)
    port = int(sock.getsockname()[1])
    return sock, port


def _hello_ok(line: str) -> bool:
    try:
        raw = json.loads(line)
    except json.JSONDecodeError:
        return False
    if not (isinstance(raw, dict) and raw.get("t") == "hello" and bool(raw.get("ok"))):
        return False
    child_pid = raw.get("pid")
    _watch_trace(f"sidecar hello ok child_pid={child_pid}")
    return True


def _hello_pid(line: str) -> int | None:
    try:
        raw = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    try:
        pid = int(raw.get("pid") or 0)
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def _readline_timeout(
    stream: object,
    timeout: float,
    cancel: CancelToken | None = None,
) -> str:
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
    deadline = time.monotonic() + max(0.0, timeout)
    cancelled = False
    while worker.is_alive():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        if cancel is not None and cancel.cancelled():
            cancelled = True
            break
        worker.join(min(_CANCEL_POLL_SEC, remaining))
    if cancelled:
        # Do not abandon a live readline on this stream; caller kills the child
        # next, which unblocks the reader. Join so a later turn cannot race.
        worker.join(2.0)
        return ""
    if worker.is_alive():
        return ""
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


def _sidecar_keep_pids(keep_pid: int | None, hello_pid: int | None = None) -> set[int]:
    """Popen.pid may be a venv stub; the real _sidecar_main is often its child."""
    keep: set[int] = set()
    if keep_pid is not None and keep_pid > 0:
        keep.add(int(keep_pid))
    if hello_pid is not None and hello_pid > 0:
        keep.add(int(hello_pid))
    if not keep:
        return keep
    try:
        import psutil
    except ImportError:
        return keep
    for root_pid in list(keep):
        try:
            root = psutil.Process(root_pid)
            keep.update(int(c.pid) for c in root.children(recursive=True))
        except (psutil.Error, TypeError, ValueError):
            continue
    return keep


def _kill_stray_sidecars(
    *, keep_pid: int | None, hello_pid: int | None = None
) -> None:
    """Reap orphaned _sidecar_main processes so done cannot land on a dead pipe."""
    try:
        import psutil
    except ImportError:
        return
    keep = _sidecar_keep_pids(keep_pid, hello_pid)
    marker = "_sidecar_main.py"
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            pid = int(proc.info.get("pid") or 0)
            if pid in keep:
                continue
            cmd = proc.info.get("cmdline") or []
            if not any(marker in str(part) for part in cmd):
                continue
            _watch_trace(
                f"kill stray sidecar pid={pid} keep={sorted(keep)}"
            )
            proc.kill()
        except (psutil.Error, TypeError, ValueError):
            continue


def _failed(code: EngineErrorCode, detail: str) -> EngineFailed:
    return EngineFailed(EngineError(code, detail))


def _turn_api_key(turn: StatelessTurn) -> str:
    """Hermes `_init_openai_client` only takes the explicit path when both
    api_key and base_url are set. Ollama's OpenAI adapter accepts any token."""
    key = (turn.model.api_key or "").strip()
    if key:
        return key
    if looks_like_ollama_endpoint(turn.model.base_url):
        return "ollama"
    return ""


def _spawn_sidecar(
    home: EngineHome,
) -> EngineFailed | tuple[subprocess.Popen[str], int | None]:
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
        reported = _hello_pid(line)
        _watch_trace(
            f"sidecar spawn popen_pid={proc.pid} hello_pid={reported}"
        )
        return proc, reported
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
        self._child_hello_pid: int | None = None
        # True while a turn owns the child for I/O outside _lock. Shutdown ignores it.
        self._turn_active = False
        self._tool_handler: Callable[[str, dict[str, object]], dict[str, object]] | None = None

    @property
    def source(self) -> EngineSource:
        """Parsed source for this handle. Same object shared_engine() stored."""
        return self._source

    def fork(self) -> Engine:
        """Return an independent sidecar owner for one concurrent chat worker."""
        return Engine(self._source)

    def bind_tool_handler(
        self, handler: Callable[[str, dict[str, object]], dict[str, object]]
    ) -> None:
        self._tool_handler = handler

    def ensure_ready(self) -> EngineEnsureResult:
        try:
            with self._lock:
                if self._child is not None:
                    if self._child.poll() is None:
                        return EngineReady(self._source, "engine is ready")
                    _close_pipes(self._child)
                    self._child = None
                    self._child_hello_pid = None
                home = self._source.home
                probe = probe_engine_python(home)
                if probe is not None and probe.code in (
                    EngineErrorCode.NOT_INSTALLED,
                    EngineErrorCode.WRONG_PYTHON,
                ):
                    install_into(home)
                    probe = probe_engine_python(home)
                if probe is not None:
                    return EngineFailed(probe)
                spawned = _spawn_sidecar(home)
                if isinstance(spawned, EngineFailed):
                    return spawned
                self._child, self._child_hello_pid = spawned
                return EngineReady(self._source, "engine is ready")
        except Exception as exc:
            return EngineFailed(EngineError(EngineErrorCode.UNKNOWN, str(exc)))

    def _forget_child(self) -> None:
        child = self._child
        self._child = None
        self._child_hello_pid = None
        if child is None:
            return
        if child.poll() is None:
            _terminate_child(child)
            return
        _close_pipes(child)

    def _stop_and_forget(self) -> None:
        # Cooperative stdin stop first; _forget_child still taskkills if the turn is stuck.
        # Takes _lock so shutdown can run while another thread is mid-read.
        with self._lock:
            child = self._child
            hello_pid = self._child_hello_pid
            if child is not None:
                _send_stop(child)
            self._forget_child()
        # Popen.pid may be a venv stub; also kill the hello pid that runs _sidecar_main.
        for pid in (hello_pid,):
            if pid is None:
                continue
            try:
                import psutil

                if psutil.pid_exists(int(pid)):
                    psutil.Process(int(pid)).kill()
                    _watch_trace(f"stop killed hello_pid={pid}")
            except Exception:
                pass

    def _forget_if_current(self, child: subprocess.Popen[str]) -> None:
        with self._lock:
            if self._child is child:
                self._forget_child()

    def _write_turn(
        self,
        child: subprocess.Popen[str],
        turn: StatelessTurn,
        *,
        terminal_udp_port: int | None = None,
    ) -> None:
        if child.stdin is None:
            raise OSError("sidecar stdin is missing")
        fields: dict[str, object] = {
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in turn.transcript.messages
            ],
            "model": turn.model.model,
            "provider": turn.model.provider,
            "speak_surface": turn.speak_surface,
        }
        if turn.model.base_url:
            fields["base_url"] = turn.model.base_url
        api_key = _turn_api_key(turn)
        if api_key:
            fields["api_key"] = api_key
        if terminal_udp_port is not None:
            fields["terminal_udp_port"] = int(terminal_udp_port)
        child.stdin.write(encode_host_command("turn", **fields))
        child.stdin.flush()

    def _reply_to_tool_request(
        self, child: subprocess.Popen[str], raw: dict[str, object]
    ) -> None:
        request_id = str(raw.get("id") or "").strip()
        name = str(raw.get("name") or "").strip()
        args = raw.get("args")
        if not isinstance(args, dict):
            args = {}
        if not request_id or not name:
            result: dict[str, object] = {
                "ok": False,
                "error": "invalid native tool request",
            }
        elif self._tool_handler is None:
            result = {"ok": False, "error": "native tool bridge is not bound"}
        else:
            try:
                handled = self._tool_handler(name, args)
                result = handled if isinstance(handled, dict) else {
                    "ok": False,
                    "error": "native tool returned an invalid result",
                }
            except Exception as exc:
                result = {"ok": False, "error": str(exc) or type(exc).__name__}
        if child.stdin is None:
            raise OSError("sidecar stdin is missing")
        child.stdin.write(
            encode_host_command("tool_result", id=request_id, result=result)
        )
        child.stdin.flush()

    def _read_turn_events(
        self,
        child: subprocess.Popen[str],
        cancel: CancelToken,
        *,
        hello_pid: int | None = None,
        udp_sock: socket.socket | None = None,
    ) -> Iterator[TurnEvent]:
        # One reader thread only. Spawning a new readline every poll abandons
        # prior readers on the same Windows pipe and yields OSError 22 on write.
        if hello_pid is None:
            hello_pid = self._child_hello_pid
        lines: queue.Queue[str] = queue.Queue()
        stop_reader = threading.Event()
        _watch_trace(
            f"read_turn_events start hello_pid={hello_pid} "
            f"udp={udp_sock is not None}"
        )

        def _reader() -> None:
            stream = child.stdout
            while not stop_reader.is_set():
                if stream is None:
                    lines.put("")
                    return
                try:
                    line = stream.readline()
                except Exception:
                    line = ""
                if line:
                    lines.put(line)
                    continue
                if child.poll() is not None or stop_reader.is_set():
                    lines.put("")
                    return
                time.sleep(0.05)

        reader = threading.Thread(target=_reader, name="iris-sidecar-stdout", daemon=True)
        reader.start()
        idle_deadline = time.monotonic() + _TURN_IDLE_SEC
        last_miss_log = 0.0
        try:
            while True:
                if cancel.cancelled():
                    self._stop_and_forget()
                    yield TurnCancelled()
                    return
                line = ""
                if udp_sock is not None:
                    try:
                        data, _addr = udp_sock.recvfrom(65535)
                        if data:
                            line = data.decode("utf-8", errors="replace")
                            if not line.endswith("\n"):
                                line += "\n"
                            _watch_trace(f"recv udp bytes={len(data)}")
                    except socket.timeout:
                        pass
                    except OSError as exc:
                        _watch_trace(f"udp recv err {exc!r}")
                if not line:
                    try:
                        line = lines.get_nowait()
                    except queue.Empty:
                        line = ""
                if not line:
                    # UDP can miss on Windows localhost; sidecar also writes the
                    # terminal file. Poll it here so land does not depend on UI.
                    file_line = _read_terminal_file_impl(hello_pid)
                    if file_line:
                        line = file_line
                    else:
                        now = time.monotonic()
                        if now - last_miss_log >= 5.0:
                            last_miss_log = now
                            _watch_trace(f"terminal_udp miss hello_pid={hello_pid}")
                        if cancel.cancelled():
                            self._stop_and_forget()
                            yield TurnCancelled()
                            return
                        if time.monotonic() >= idle_deadline:
                            if child.poll() is None:
                                yield TurnFailed(
                                    EngineError(
                                        EngineErrorCode.TURN_IDLE,
                                        "sidecar event timed out",
                                    )
                                )
                                return
                            self._forget_if_current(child)
                            yield TurnFailed(
                                EngineError(
                                    EngineErrorCode.SPAWN_FAILED,
                                    "sidecar exited during turn",
                                )
                            )
                            return
                        continue
                idle_deadline = time.monotonic() + _TURN_IDLE_SEC
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    _watch_trace(
                        f"json_fail line_len={len(line)} head={line.strip()[:80]!r}"
                    )
                    continue
                if isinstance(raw, dict) and raw.get("t") == "tool_request":
                    try:
                        self._reply_to_tool_request(child, raw)
                    except (OSError, ValueError) as exc:
                        yield TurnFailed(
                            EngineError(
                                EngineErrorCode.TOOL_TRANSPORT,
                                f"native tool bridge failed: {exc}",
                            )
                        )
                        return
                    continue
                event = parse_turn_event(raw)
                if isinstance(event, TurnFinished):
                    _watch_trace(f"recv done text_len={len(event.text or '')}")
                elif isinstance(event, TurnFailed):
                    _watch_trace(
                        f"recv fail code={event.error.code} "
                        f"detail={event.error.detail[:120]!r}"
                    )
                elif isinstance(event, TurnCancelled):
                    _watch_trace("recv cancel")
                yield event
                if isinstance(event, (TurnFinished, TurnFailed, TurnCancelled)):
                    return
        finally:
            stop_reader.set()
            if udp_sock is not None:
                try:
                    udp_sock.close()
                except OSError:
                    pass


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
                if self._turn_active:
                    yield TurnFailed(
                        EngineError(EngineErrorCode.PROTOCOL, "engine turn already in progress")
                    )
                    return
                child = self._child
                if child is None or child.poll() is not None:
                    self._forget_child()
                    yield TurnFailed(
                        EngineError(EngineErrorCode.SPAWN_FAILED, "sidecar child is missing")
                    )
                    return
                keep_pid = int(child.pid) if child.pid else None
                hello_pid = self._child_hello_pid
                try:
                    udp_sock, udp_port = _bind_terminal_udp()
                except OSError as exc:
                    yield TurnFailed(
                        EngineError(
                            EngineErrorCode.SPAWN_FAILED,
                            f"terminal udp bind failed: {exc}",
                        )
                    )
                    return
                try:
                    self._write_turn(child, turn, terminal_udp_port=udp_port)
                except (OSError, ValueError) as exc:
                    try:
                        udp_sock.close()
                    except OSError:
                        pass
                    self._forget_child()
                    yield TurnFailed(
                        EngineError(
                            EngineErrorCode.SPAWN_FAILED,
                            f"sidecar stdin closed: {exc}",
                        )
                    )
                    return
                self._turn_active = True
                _watch_trace(
                    f"run_turn started popen_pid={keep_pid} hello_pid={hello_pid} "
                    f"udp_port={udp_port}"
                )
            # Release before event I/O so shutdown() is not stuck behind a live turn.
            try:
                yield from self._read_turn_events(
                    child,
                    turn.cancel,
                    hello_pid=hello_pid,
                    udp_sock=udp_sock,
                )
            finally:
                with self._lock:
                    self._turn_active = False
        except Exception as exc:
            yield TurnFailed(EngineError(EngineErrorCode.UNKNOWN, str(exc)))

    def shutdown(self) -> None:
        try:
            with self._lock:
                child = self._child
                self._child = None
                self._child_hello_pid = None
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
