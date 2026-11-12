"""Hermes-interpreter sidecar entry.

Agent-readable:
- Owns: logging reservation, the GuiPython refuse check, the stdin loop, and one AIAgent turn.
- Does not: import iris, PyQt6, or run_agent before logging. Does not bind :8642.
- Talks to: the host through NDJSON on stdout. Inbound commands are turn and stop.
- Extend via: cancel interrupt and tool callbacks. Persist stays off.
"""

from __future__ import annotations

import os
import sys

# File-path spawn puts this directory on sys.path[0]. iris/engine/types.py then
# shadows the stdlib types module. Strip it before any other import.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path = [
    part
    for part in sys.path
    if os.path.normcase(os.path.abspath(part or ".")) != os.path.normcase(_SCRIPT_DIR)
]
# File-path spawn uses EngineHome as cwd, so project root is not on sys.path.
_REPO_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
if _REPO_ROOT and os.path.normcase(_REPO_ROOT) not in {
    os.path.normcase(os.path.abspath(part or ".")) for part in sys.path
}:
    sys.path.insert(0, _REPO_ROOT)

import importlib
import importlib.util
import inspect
import json
import logging
import threading
import time
from pathlib import Path


def _load_local_helper(name: str):
    """Load pure sidecar helpers without importing the Qt-facing iris.engine package."""
    module_name = f"_iris_sidecar_{name}"
    spec = importlib.util.spec_from_file_location(
        module_name, Path(_SCRIPT_DIR) / f"{name}.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError(name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


emit_app_ui_payload = _load_local_helper("app_ui").emit_app_ui_payload
ToolErrorBudget = _load_local_helper("tool_error_budget").ToolErrorBudget
_diagram_nudge_mod = _load_local_helper("diagram_tool_nudge")
DiagramToolNudge = _diagram_nudge_mod.DiagramToolNudge
append_hint_to_last_tool_result = _diagram_nudge_mod.append_hint_to_last_tool_result


def _force_utf8_stdio() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            continue


_force_utf8_stdio()
_HOST_STDOUT = sys.stdout
try:
    _HOST_OUT_FD = os.dup(sys.stdout.fileno())
except OSError:
    _HOST_OUT_FD = -1
def _terminal_dir() -> Path:
    env = os.environ.get("IRIS_TERMINAL_DIR", "").strip()
    if env:
        return Path(env)
    return Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".") / (
        "iris-sidecar-terminal"
    )


def _configure_logging() -> None:
    kwargs = {
        "level": logging.INFO,
        "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        "force": True,
    }
    log_path = os.environ.get("IRIS_ENGINE_LOG", "").strip()
    if log_path:
        logging.basicConfig(filename=log_path, **kwargs)
        return
    logging.basicConfig(stream=sys.stderr, **kwargs)


def _is_gui_python() -> bool:
    if "--refuse-gui" in sys.argv:
        return True
    marked = os.environ.get("IRIS_ENGINE_GUI_PYTHON", "").strip()
    if not marked:
        return False
    return Path(sys.executable).resolve() == Path(marked).resolve()


_EMIT_LOCK = threading.Lock()
_WATCH_LOG = Path.home() / ".iris-light" / "logs" / "turn_end_watch.log"


def _watch_trace(msg: str) -> None:
    line = f"pid={os.getpid()} {msg}\n"

    def _write() -> None:
        try:
            _WATCH_LOG.parent.mkdir(parents=True, exist_ok=True)
            with _WATCH_LOG.open("a", encoding="utf-8") as fh:
                fh.write(line)
        except Exception:
            return

    threading.Thread(target=_write, name="iris-side-watch", daemon=True).start()


def _write_terminal_file(payload: dict) -> None:
    """Pipe-independent done/fail so the host can land when stdout EINVAL."""
    kind = payload.get("t")
    if kind not in ("done", "fail"):
        return
    try:
        terminal_dir = _terminal_dir()
        terminal_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        path = terminal_dir / f"{os.getpid()}.ndjson"
        path.write_text(line, encoding="utf-8")
        _watch_trace(f"terminal_file {kind} path={path} dir={terminal_dir}")
    except Exception as exc:
        _watch_trace(f"terminal_file fail {exc!r}")


def _host_fds() -> list[int]:
    raw_fds: list[int] = []
    if _HOST_OUT_FD >= 0:
        raw_fds.append(_HOST_OUT_FD)
    try:
        raw_fds.append(int(_HOST_STDOUT.fileno()))
    except Exception:
        pass
    seen: set[int] = set()
    out: list[int] = []
    for fd in raw_fds:
        if fd < 0 or fd in seen:
            continue
        seen.add(fd)
        out.append(fd)
    return out


def _write_host_bytes(fd: int, data: bytes) -> None:
    """Non-blocking when possible so a full pipe cannot wedge done/fail forever."""
    try:
        os.set_blocking(fd, False)
    except (OSError, AttributeError, ValueError):
        pass
    offset = 0
    stall = 0
    while offset < len(data):
        try:
            written = os.write(fd, data[offset:])
        except BlockingIOError:
            stall += 1
            if stall > 50:
                raise OSError(22, "host stdout write would block")
            time.sleep(0.02)
            continue
        if written <= 0:
            raise OSError(22, "short write to host stdout")
        offset += written
        stall = 0


def _emit_terminal_via_udp(payload: dict) -> None:
    """done/fail over localhost UDP — survives wedged stdout/stderr/file on Windows."""
    import socket

    port_raw = os.environ.get("IRIS_TERMINAL_UDP_PORT", "").strip()
    if not port_raw:
        raise OSError("IRIS_TERMINAL_UDP_PORT missing")
    port = int(port_raw)
    data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(data, ("127.0.0.1", port))
    finally:
        sock.close()
    _watch_trace(f"emit {payload.get('t')} udp ok bytes={len(data)} port={port}")


def _emit(payload: dict) -> None:
    # Defer callers off logging.Handler.emit.
    # done/fail: UDP (+ file backup). stdout/stderr terminal paths wedge the host.
    kind = payload.get("t")
    if kind in ("done", "fail"):
        blob = payload.get("text") or payload.get("detail") or ""
        _watch_trace(f"emit {kind} text_len={len(str(blob))}")
        # UDP only — terminal files can freeze the Qt UI thread if polled there.
        try:
            _emit_terminal_via_udp(payload)
        except Exception as exc:
            _watch_trace(f"emit {kind} udp failed {exc!r}")
            _write_terminal_file(payload)
        return
    data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    last: OSError | None = None
    uniq_fds = _host_fds()
    for attempt in range(5):
        for fd in uniq_fds:
            try:
                with _EMIT_LOCK:
                    _write_host_bytes(fd, data)
                return
            except OSError as exc:
                last = exc
        time.sleep(0.02 * (attempt + 1))
    assert last is not None
    raise last



def _fail(code: str, detail: str) -> None:
    _emit({"t": "fail", "code": code, "detail": detail})


def _request_native_tool(name: str, args: dict) -> str:
    """Execute one Iris-owned tool through the parent process and return JSON."""
    import uuid

    request_id = uuid.uuid4().hex
    _emit({"t": "tool_request", "id": request_id, "name": name, "args": args})
    line = sys.stdin.readline()
    if not line:
        return json.dumps({"ok": False, "error": "native tool bridge closed"})
    try:
        reply = json.loads(line)
        if not isinstance(reply, dict) or reply.get("t") != "tool_result":
            raise ValueError("unexpected native tool response")
        if str(reply.get("id") or "") != request_id:
            raise ValueError("native tool response id mismatch")
        result = reply.get("result")
        if not isinstance(result, dict):
            raise ValueError("native tool result must be an object")
        return json.dumps(result, ensure_ascii=False)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


def _install_iris_engine_tools(
    agent: object, *, surface: object = "home"
) -> tuple[str, ...]:
    """Register Iris schemas in Hermes and expose them on this AIAgent instance."""
    from iris.infrastructure.speak_capability import (
        engine_tool_action,
        engine_tool_schemas,
        normalize_speak_surface,
    )
    from tools.registry import registry

    schemas = engine_tool_schemas(surface=normalize_speak_surface(surface))
    tools = list(getattr(agent, "tools", None) or [])
    existing = {
        str(row.get("function", {}).get("name") or "")
        for row in tools
        if isinstance(row, dict) and isinstance(row.get("function"), dict)
    }
    for schema in schemas:
        name = str(schema["name"])
        action = engine_tool_action(name)
        registry.register(
            name=name,
            toolset="iris",
            schema={
                "description": schema["description"],
                "parameters": schema["parameters"],
            },
            handler=lambda args, _action=action, **_kwargs: _request_native_tool(
                _action, dict(args or {})
            ),
        )
        if name not in existing:
            tools.append({"type": "function", "function": dict(schema)})
    agent.tools = tools
    agent.valid_tool_names = {
        str(row.get("function", {}).get("name") or "")
        for row in tools
        if isinstance(row, dict) and isinstance(row.get("function"), dict)
    }
    return tuple(str(schema["name"]) for schema in schemas)


_AGENT_CLS: type | None = None
_AGENT_MISSING = False


def _import_agent_class() -> type:
    name = os.environ.get("IRIS_ENGINE_AGENT_MODULE", "").strip() or "run_agent"
    module = importlib.import_module(name)
    cls = getattr(module, "AIAgent", None)
    if cls is None:
        raise ImportError("AIAgent is missing")
    return cls


def _agent_class() -> type | None:
    global _AGENT_CLS, _AGENT_MISSING
    if _AGENT_MISSING:
        return None
    if _AGENT_CLS is not None:
        return _AGENT_CLS
    try:
        _AGENT_CLS = _import_agent_class()
        return _AGENT_CLS
    except ImportError:
        _AGENT_MISSING = True
        return None


def _init_kwargs(cls: type, wanted: dict) -> dict:
    try:
        params = inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):
        return wanted
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return wanted
    return {key: value for key, value in wanted.items() if key in params}


def _split_for_agent(raw: object) -> tuple[list, str] | None:
    if not isinstance(raw, list) or not raw:
        _fail("no_user_utterance", "last message must be a user utterance")
        return None
    last = raw[-1]
    if not isinstance(last, dict) or last.get("role") != "user":
        _fail("no_user_utterance", "last message must be a user utterance")
        return None
    content = last.get("content")
    user = "" if content is None else str(content)
    history = [row for row in raw[:-1] if isinstance(row, dict)]
    return history, user


def _on_delta(text: object) -> None:
    if text is None:
        return
    chunk = str(text)
    if not chunk:
        return
    _emit({"t": "delta", "text": chunk})


_TOOL_EVENT_KINDS = frozenset({"tool.started", "tool.completed", "tool.progress"})
_NOT_A_TOOL_NAME = frozenset(
    {
        "",
        "tool.started",
        "tool.completed",
        "tool.progress",
        "reasoning.available",
        "_thinking",
    }
)


_reasoning_streamed = False


def tool_use_label(kind: object, name: object = None) -> str | None:
    """Live-activity line for one tool callback. None when it is not a tool name."""
    if str(kind or "") not in _TOOL_EVENT_KINDS:
        return None
    tool = "" if name is None else str(name).strip()
    if tool in _NOT_A_TOOL_NAME:
        return None
    return f"[IRIS tool use: {tool}]"


def _coerce_tool_result_bag(raw: object) -> dict | None:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text.startswith("{"):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _emit_app_ui_from_tool(
    kind: object,
    name: object,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> None:
    if str(kind or "") != "tool.completed":
        return
    bags: list[dict] = []
    for key in ("result", "data"):
        bag = _coerce_tool_result_bag(kwargs.get(key))
        if bag is not None:
            bags.append(bag)
    if isinstance(kwargs.get("_meta"), dict):
        bags.append(kwargs)
    for arg in args[1:]:
        bag = _coerce_tool_result_bag(arg)
        if bag is not None:
            bags.append(bag)
    title = "" if name is None else str(name).strip()
    default_title = title or "앱"
    for bag in bags:
        payload = emit_app_ui_payload(bag, default_title=default_title)
        if payload is not None:
            _emit(payload)
            return


def _on_tool(kind: object = None, *args: object, **kwargs: object) -> None:
    if kind is None and args:
        kind = args[0]
        args = args[1:]
    if kind is None:
        kind = kwargs.get("label", "")
    name = args[0] if args else kwargs.get("name")
    label = tool_use_label(kind, name)
    if label:
        _emit({"t": "tool", "label": label})
    _emit_app_ui_from_tool(kind, name, args, kwargs)
    if label:
        return
    kind_text = "" if kind is None else str(kind)
    if kind_text == "reasoning.available":
        _emit_reasoning_fallback(args, kwargs)
        return
    if kind_text in _NOT_A_TOOL_NAME:
        return
    if kind_text:
        _emit({"t": "tool", "label": kind_text})


def _on_reasoning(text: object) -> None:
    global _reasoning_streamed
    if text is None:
        return
    chunk = str(text)
    if not chunk:
        return
    _reasoning_streamed = True
    _emit({"t": "think", "text": chunk})


def _emit_reasoning_fallback(args: tuple[object, ...], kwargs: dict[str, object]) -> None:
    if _reasoning_streamed:
        return
    preview = args[1] if len(args) > 1 else kwargs.get("preview")
    if preview is None:
        return
    chunk = str(preview)
    if chunk:
        _emit({"t": "think", "text": chunk})


def _done_text(result: object) -> str:
    if isinstance(result, dict):
        return str(result.get("final_response") or "")
    if result is None:
        return ""
    return str(result)


_BILLING_HINTS = ("402", "credits", "billing", "entitlement")

# Hermes can wedge after the "Turn ended" log before run_conversation returns
# (agent/turn_liveness.py #131740). Land as soon as we have text; otherwise wait
# briefly for return, then emit whatever we have.
_TURN_ENDED_LOG_PREFIX = "Turn ended:"
_POST_TURN_END_GRACE_SEC = 5.0
_TURN_ENDED_LOG_POLL_SEC = 0.25


def agent_result_fail(result: object) -> tuple[str, str] | None:
    """Map a Hermes agent result to fail (code, detail), or None for done."""
    if not isinstance(result, dict):
        return None
    reason = str(result.get("failure_reason") or "").strip()
    detail = str(
        result.get("final_response")
        or result.get("error")
        or reason
        or "agent failed"
    )
    reason_l = reason.lower()
    reason_billing = reason_l == "billing" or any(h in reason_l for h in _BILLING_HINTS)
    if not bool(result.get("failed")) and not reason_billing:
        return None
    blob = f"{reason}\n{detail}".lower()
    if reason_billing or any(h in blob for h in _BILLING_HINTS):
        return ("billing", detail)
    return (reason_l or "unknown", detail)


def _assistant_text_from_agent(agent: object) -> str:
    streamed = getattr(agent, "_current_streamed_assistant_text", None)
    if isinstance(streamed, str) and streamed.strip():
        return streamed
    messages = getattr(agent, "_session_messages", None)
    if not isinstance(messages, list):
        return ""
    for row in reversed(messages):
        if not isinstance(row, dict) or row.get("role") != "assistant":
            continue
        content = row.get("content")
        if content is None:
            return ""
        return str(content)
    return ""


def _run_turn_ended_cb(callback: object) -> None:
    try:
        if callable(callback):
            callback()
    except Exception:
        logging.getLogger(__name__).exception("turn-ended done emit failed")


class _TurnEndedLogHandler(logging.Handler):
    """Fires once when Hermes logs the conversation-loop Turn ended line."""

    def __init__(self, on_turn_ended: object) -> None:
        super().__init__(level=logging.INFO)
        self._on_turn_ended = on_turn_ended
        self._fired = False

    def emit(self, record: logging.LogRecord) -> None:
        if self._fired:
            return
        try:
            message = record.getMessage()
        except Exception:
            return
        # Hermes may wrap the line with a session prefix in getMessage().
        if _TURN_ENDED_LOG_PREFIX not in message:
            return
        self._fired = True
        _watch_trace(f"handler Turn ended msg={message[:120]!r}")
        # Never _emit on this stack: Windows pipe flush inside Handler.emit
        # raises OSError 22 and leaves the host without done.
        threading.Thread(
            target=_run_turn_ended_cb,
            args=(self._on_turn_ended,),
            name="iris-turn-ended",
            daemon=True,
        ).start()


def _turn_ended_log_paths() -> list[Path]:
    """Per-sidecar host log only. Shared agent.log cross-fires other sidecars."""
    env = os.environ.get("IRIS_ENGINE_LOG", "").strip()
    if not env:
        return []
    return [Path(env)]


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _poll_turn_ended_logs(
    paths: list[Path],
    start_offsets: dict[str, int],
    stop: threading.Event,
    on_hit: object,
) -> None:
    """Watch log files from turn-start offsets; fire when Turn ended appears."""
    offsets = dict(start_offsets)
    while not stop.wait(_TURN_ENDED_LOG_POLL_SEC):
        for path in paths:
            key = os.path.normcase(str(path))
            size = _file_size(path)
            offset = offsets.get(key, 0)
            if size < offset:
                offset = 0
            if size <= offset:
                offsets[key] = size
                continue
            try:
                with path.open("rb") as fh:
                    fh.seek(offset)
                    chunk = fh.read(size - offset)
            except OSError:
                continue
            offsets[key] = size
            text = chunk.decode("utf-8", errors="replace")
            if _TURN_ENDED_LOG_PREFIX not in text:
                continue
            try:
                on_hit()
            except Exception:
                logging.getLogger(__name__).exception("turn-ended log poll failed")
                continue
            return


def _emit_turn_terminal_once(
    gate: threading.Event,
    lock: threading.Lock,
    *,
    fail: tuple[str, str] | None = None,
    text: str = "",
) -> bool:
    with lock:
        if gate.is_set():
            return False
        try:
            if fail is not None:
                _fail(fail[0], fail[1])
            else:
                _emit({"t": "done", "text": text})
        except OSError as exc:
            _watch_trace(f"emit terminal failed {exc!r}")
            return False
        gate.set()
        return True


def _run_agent_turn(cls: type, history: list, user: str, raw: dict) -> None:
    global _reasoning_streamed
    _reasoning_streamed = False
    streamed_parts: list[str] = []
    returned = threading.Event()
    release = threading.Event()
    terminal = threading.Event()
    terminal_lock = threading.Lock()
    armed = threading.Event()
    stop_poll = threading.Event()
    outcome: dict[str, object] = {}
    budget = ToolErrorBudget()
    diagram_nudge = DiagramToolNudge()
    agent_ref: dict[str, object] = {}

    def on_delta(text: object) -> None:
        if text is None:
            return
        chunk = str(text)
        if not chunk:
            return
        streamed_parts.append(chunk)
        _emit({"t": "delta", "text": chunk})

    def on_turn_ended() -> None:
        # Handler + file poll share one arm. Prefer landing immediately when
        # stream already has text. If not, wait briefly for return.
        if armed.is_set():
            return
        armed.set()
        try:
            if budget.reason:
                _emit_turn_terminal_once(
                    terminal,
                    terminal_lock,
                    fail=("tool_error_budget", budget.reason),
                )
                stop_poll.set()
                release.set()
                return
            text = "".join(streamed_parts).strip() or _assistant_text_from_agent(agent)
            if text:
                for attempt in range(5):
                    if _emit_turn_terminal_once(
                        terminal, terminal_lock, text=text
                    ):
                        stop_poll.set()
                        release.set()
                        return
                    time.sleep(0.05 * (attempt + 1))
                # Leave terminal clear so the worker-return path retries emit.
                stop_poll.set()
                return

            stop_poll.set()

            def _watch() -> None:
                if returned.wait(_POST_TURN_END_GRACE_SEC):
                    return
                late = "".join(streamed_parts).strip() or _assistant_text_from_agent(
                    agent
                )
                if late:
                    _emit_turn_terminal_once(terminal, terminal_lock, text=late)
                else:
                    _emit_turn_terminal_once(
                        terminal,
                        terminal_lock,
                        fail=(
                            "turn_end_stall",
                            "turn ended but run_conversation did not return",
                        ),
                    )
                release.set()

            threading.Thread(
                target=_watch,
                name="iris-post-turn-end",
                daemon=True,
            ).start()
        except Exception:
            armed.clear()
            raise

    def on_tool_complete(
        _call_id: object,
        name: object,
        args: object,
        result: object,
    ) -> None:
        tool_name = str(name or "tool")
        hint = diagram_nudge.observe(tool_name, args, result)
        if hint:
            active = agent_ref.get("agent")
            appended = append_hint_to_last_tool_result(active, hint)
            _watch_trace(
                f"diagram_tool_nudge appended={appended} {hint[:160]}"
            )
        reason = budget.observe(tool_name, args, result)
        if not reason:
            return
        _watch_trace(f"tool_error_budget {reason[:240]}")
        active = agent_ref.get("agent")
        interrupt = getattr(active, "interrupt", None)
        if callable(interrupt):
            interrupt(hard_cancel=True, tool_reason="tool_error_budget")

    wanted = {
        "skip_memory": True,
        "skip_background_review": True,
        "session_db": None,
        "load_soul_identity": True,
        "stream_delta_callback": on_delta,
        "tool_progress_callback": _on_tool,
        "tool_complete_callback": on_tool_complete,
        "reasoning_callback": _on_reasoning,
        "quiet_mode": True,
    }
    model = raw.get("model")
    if isinstance(model, str) and model:
        wanted["model"] = model
    provider = raw.get("provider")
    if isinstance(provider, str) and provider:
        wanted["provider"] = provider
    base_url = raw.get("base_url")
    if isinstance(base_url, str) and base_url:
        wanted["base_url"] = base_url
    api_key = raw.get("api_key")
    if isinstance(api_key, str) and api_key:
        wanted["api_key"] = api_key
    agent = cls(**_init_kwargs(cls, wanted))
    agent_ref["agent"] = agent
    _install_iris_engine_tools(agent, surface=raw.get("speak_surface"))
    agent._persist_disabled = True
    handler = _TurnEndedLogHandler(on_turn_ended)
    # turn_finalizer logs via agent.conversation_loop; also watch parent.
    # Do not attach to the root logger: every agent line would enter Handler.emit.
    watched = (
        logging.getLogger("agent.conversation_loop"),
        logging.getLogger("agent"),
    )
    previous_levels = [(log, log.level) for log in watched]
    for log in watched:
        log.setLevel(logging.INFO)
        log.addHandler(handler)

    log_paths = _turn_ended_log_paths()
    log_offsets = {
        os.path.normcase(str(path)): _file_size(path) for path in log_paths
    }
    if log_paths:
        threading.Thread(
            target=_poll_turn_ended_logs,
            args=(log_paths, log_offsets, stop_poll, on_turn_ended),
            name="iris-turn-end-log-poll",
            daemon=True,
        ).start()

    def worker() -> None:
        try:
            outcome["result"] = agent.run_conversation(
                user_message=user,
                conversation_history=history,
            )
        except Exception as exc:
            outcome["exc"] = exc
        finally:
            returned.set()
            stop_poll.set()
            for log, level in previous_levels:
                log.removeHandler(handler)
                log.setLevel(level)
            result = outcome.get("result")
            text_len = len(_done_text(result)) if result is not None else 0
            _watch_trace(
                f"worker returned text_len={text_len} terminal={terminal.is_set()}"
            )
            release.set()

    threading.Thread(
        target=worker,
        name="iris-agent-turn",
        daemon=True,
    ).start()
    release.wait()
    stop_poll.set()
    if terminal.is_set():
        return
    exc = outcome.get("exc")
    if isinstance(exc, BaseException):
        raise exc
    result = outcome.get("result")
    fail = (
        ("tool_error_budget", budget.reason)
        if budget.reason
        else agent_result_fail(result)
    )
    for attempt in range(5):
        if terminal.is_set():
            return
        if fail is not None:
            if _emit_turn_terminal_once(terminal, terminal_lock, fail=fail):
                return
        elif _emit_turn_terminal_once(
            terminal, terminal_lock, text=_done_text(result)
        ):
            return
        time.sleep(0.05 * (attempt + 1))
    if not terminal.is_set():
        _watch_trace("emit terminal exhausted after worker return")


def _handle_turn(raw: dict) -> bool:
    cls = _agent_class()
    if cls is None:
        _fail("unknown", "agent loop is not wired")
        return True
    split = _split_for_agent(raw.get("messages"))
    if split is None:
        return True
    history, user = split
    port = raw.get("terminal_udp_port")
    if port is not None:
        try:
            os.environ["IRIS_TERMINAL_UDP_PORT"] = str(int(port))
        except (TypeError, ValueError):
            os.environ.pop("IRIS_TERMINAL_UDP_PORT", None)
    try:
        _run_agent_turn(cls, history, user, raw)
    except Exception as exc:
        _fail("unknown", str(exc) or "agent loop failed")
    return True


def _handle_stop(_raw: dict) -> bool:
    return False


_COMMANDS = {
    "turn": _handle_turn,
    "stop": _handle_stop,
}


def _handle_line(line: str) -> bool:
    text = line.strip()
    if not text:
        return True
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        _fail("protocol", "command must be JSON")
        return True
    if not isinstance(raw, dict):
        _fail("protocol", "command must be a dict")
        return True
    kind = raw.get("t")
    handler = _COMMANDS.get(kind) if isinstance(kind, str) else None
    if handler is None:
        _fail("protocol", f"unknown command: {kind!r}")
        return True
    return handler(raw)


def _serve() -> None:
    while True:
        line = sys.stdin.readline()
        if line == "":
            return
        if not _handle_line(line):
            return


def main() -> None:
    _configure_logging()
    if _is_gui_python():
        logging.warning("refusing to start under GuiPython")
        raise SystemExit(2)
    _watch_trace(f"sidecar hello pid={os.getpid()}")
    _emit({"t": "hello", "ok": True, "pid": os.getpid()})
    if sys.stderr is not None:
        sys.stdout = sys.stderr
    _serve()


if __name__ == "__main__":
    main()
