# Hosted engine types

Bodies are not implemented. A reader should follow a turn from `ensure` to a `TurnEvent` by reading these types alone.

## Module map

```
iris/engine/__init__.py          public: shared_engine, EngineHandle, EngineFailure, TurnEvent types
iris/engine/_supervisor.py       one writer of host process, phase, and pipe
iris/engine/_hosted.py           framed stdin/stdout protocol + Popen
iris/engine/_compat.py           wraps HermesClient + ensure_hermes_gateway_running
iris/engine/host_main.py         entry of the host process (Hermes venv only)

existing, unchanged callers
  iris/ui/workers/hermes_workers.py   HermesChatWorker / HermesHealthWorker (bodies only)
  iris/ui/window/main_window.py       _launch_chat_turn_bound, closeEvent one extra line
  iris/system/control_surface.py      ActionRegistry.invoke, ask_human
  iris/browser/session.py             BrowserSession
  iris/storage/conversations.py       history_dicts

existing, hosted path stops calling
  iris/infrastructure/hermes_client.py          Compat only
  iris/system/hermes_gateway.py                 Compat only
  iris/system/hermes_iris_control_sync.py       Compat only
  iris/mcp/iris_control_stdio.py                Compat only
```

Public `__all__` is `shared_engine`, `EngineSupervisor`, `EngineHandle`, `EngineFailure`, `ContentDelta`, `ToolProgress`, `TurnDone`, `TurnFailed`, `IRIS_ENGINE_TOOLS`. An import of `iris.engine._hosted` from app code is a lint failure.

Call chain for one turn is three files. `HermesChatWorker.run` → `EngineHandle.stream_turn` → `_hosted` or `_compat`.

## Domain types

```python
from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal, NewType, Union


class EnginePhase(Enum):
    """Single source of truth for lifecycle. Booleans such as started+ready are illegal."""

    ABSENT = "absent"
    INSTALLING = "installing"
    STARTING = "starting"
    READY = "ready"
    COMPAT = "compat"
    STOPPING = "stopping"
    FAILED = "failed"


EngineHome = NewType("EngineHome", Path)
"""IRIS-owned tree: ~/.iris-light/engine . Hosted install and SOUL.md live here."""

HermesHome = NewType("HermesHome", Path)
"""User Hermes tree: %LOCALAPPDATA%/hermes . Compat only. Not interchangeable with EngineHome."""

EnginePython = NewType("EnginePython", Path)
"""CPython that can import hermes_cli, aiohttp, mcp, ruamel.yaml. Never sys.executable of the GUI."""

GuiPython = NewType("GuiPython", Path)
"""IRIS .venv interpreter. May import PyQt6. Must not import run_agent."""


class ConversationId(int):
    """IRIS SQLite conversations.id. Never passed to AIAgent as session_id."""


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class ModelRef:
    """Already resolved on the UI thread by resolve_hermes_inference. Host does not read settings."""

    name: str
    provider: str
    ollama_base_url: str


@dataclass(frozen=True)
class ContentDelta:
    text: str


@dataclass(frozen=True)
class ToolProgress:
    line: str


@dataclass(frozen=True)
class TurnDone:
    pass


class EngineFailureCode(Enum):
    MISSING_TREE = "missing_tree"
    PYTHON_RANGE = "python_range"
    HOST_EXIT = "host_exit"
    HOST_TIMEOUT = "host_timeout"
    PROTOCOL = "protocol"
    COMPAT_UNREACHABLE = "compat_unreachable"
    COMPAT_AUTH = "compat_auth"


@dataclass(frozen=True)
class EngineFailure:
    code: EngineFailureCode
    detail: str

    def user_message(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class TurnFailed:
    code: EngineFailureCode
    detail: str

    def user_message(self) -> str:
        raise NotImplementedError


TurnEvent = Union[ContentDelta, ToolProgress, TurnDone, TurnFailed]


@dataclass(frozen=True)
class _TurnRequest:
    """Private parse of one ChatAttempt. No session_id field. Full transcript every time.
    Not in iris.engine.__all__. Callers pass ChatAttempt into stream_turn.
    """

    messages: tuple[ChatMessage, ...]
    model: ModelRef


IRIS_ENGINE_TOOLS: tuple[str, ...] = (
    "iris_get_state",
    "iris_get_catalog",
    "iris_invoke",
)
"""The only tool names the hosted host registers. Sent in the hello line.
iris_control_stdio must advertise this same tuple (compat). A boot check
compares the stdio catalog to this tuple and fails if they differ.
"""


class _Mint:
    __slots__ = ()


_MINT = _Mint()
```

`_TurnRequest` has no optional session field. A Hermes session id cannot be smuggled in. `EngineHome` and `HermesHome` are different NewTypes so a compat path cannot write the hosted tree by accident.

## Supervisor and handle

```python
class EngineHandle:
    """Capability to stream. Cannot spawn, install, or bind a port.

    Constructed only by EngineSupervisor with _MINT. App code that calls the
    constructor with any other object raises TypeError.
    """

    def __init__(self, mint: _Mint, mode: Literal["hosted", "compat"], session: object) -> None:
        if mint is not _MINT:
            raise TypeError("EngineHandle is minted only by EngineSupervisor")
        self._mode = mode
        self._session = session

    def display_host(self) -> str:
        """Label for the connecting signal. Hosted returns 'IRIS'. Compat returns the URL host."""
        raise NotImplementedError

    def stream_turn(
        self,
        attempt: object,
        *,
        should_cancel: Callable[[], bool],
    ) -> Iterator[TurnEvent]:
        """One ChatAttempt. Parse attempt.messages and attempt.target into _TurnRequest
        here. Yield domain events. Do not take a session_id.
        """
        raise NotImplementedError


class EngineSupervisor:
    """Only writer of phase, Popen, and the pipe. Health and chat workers call this. They do not spawn."""

    def ensure(self) -> EngineHandle | EngineFailure:
        """Converge to READY. Already READY returns the live handle. FAILED retries from disk facts."""
        raise NotImplementedError
        # TODO: read EngineHome + host pid/exit
        # TODO: if ABSENT, install into EngineHome (clone + venv), then STARTING
        # TODO: if tree present and python probe fails, return PYTHON_RANGE (do not spawn)
        # TODO: if host alive and protocol Hello ok, return minted hosted handle
        # TODO: spawn host_main with EnginePython, HERMES_HOME=EngineHome, stripped env
        # TODO: wait for Hello on stdout. Timeout -> HOST_TIMEOUT and STOPPING

    def attach_compat(self, *, base_url: str, api_key: str) -> EngineHandle | EngineFailure:
        """Converge to COMPAT. Hosted host is shut down first. One mode at a time."""
        raise NotImplementedError

    def shutdown(self) -> None:
        """Converge to ABSENT process (tree on disk stays). Safe if never started."""
        raise NotImplementedError
        # TODO: send Bye, close stdin, wait, terminate, wait, kill
        # TODO: phase STOPPING then ABSENT. Second call is no-op

    def _phase(self) -> EnginePhase:
        """Tests and the supervisor only. App callers use ensure() return type."""
        raise NotImplementedError


def shared_engine() -> EngineSupervisor:
    """Process singleton. GUI thread may call shutdown. Workers may call ensure and stream_turn."""
    raise NotImplementedError
```

`ensure` and `shutdown` answer the idempotent test from disk and pid facts, not from "what the last call meant to do." Two workers may call `ensure` together. The supervisor serializes those calls on one lock because one Popen is a real shared writer. They do not each write a pid file.

`attach_compat` stops a hosted host before it returns a compat handle. `READY` and `COMPAT` cannot be true together. That is the `EnginePhase` invariant.

## Hosted process (private)

The host is a hidden child. `CREATE_NO_WINDOW` only. No `CREATE_NEW_PROCESS_GROUP`. No `--replace`. No listening socket.

```python
@dataclass(frozen=True)
class HostSpec:
    python: EnginePython
    home: EngineHome
    entry: Path  # iris/engine/host_main.py
    log_path: Path  # ~/.iris-light/engine/logs/host.log


def spawn_host(spec: HostSpec) -> object:
    """Popen stdin/stdout pipes. Child env is a copy of os.environ with VIRTUAL_ENV,
    PYTHONPATH, uv, and conda keys stripped, then HERMES_HOME=home,
    HERMES_ACCEPT_HOOKS=1, HERMES_DISABLE_LAZY_INSTALLS=1. Stderr and logging go
    to log_path. Stdout is protocol only.
    """
    raise NotImplementedError


# Protocol lines, host stdout / IRIS stdin. Not part of iris.engine public API.

# IRIS -> host
# {"v":1,"t":"hello","tools":["iris_get_state","iris_get_catalog","iris_invoke"]}
# {"v":1,"t":"turn","messages":[...],"model":{"name":"...","provider":"...","ollama_base_url":"..."}}
# {"v":1,"t":"tool_result","id":"...","ok":true,"payload":{...}}
# {"v":1,"t":"cancel"}
# {"v":1,"t":"bye"}

# host -> IRIS
# {"v":1,"t":"hello","ok":true}
# {"v":1,"t":"delta","text":"..."}
# {"v":1,"t":"tool_progress","line":"..."}
# {"v":1,"t":"tool_call","id":"...","name":"iris_invoke","args":{"action":"project.write_file","args":{...}}}
# {"v":1,"t":"done"}
# {"v":1,"t":"fail","code":"host_exit","detail":"..."}


def parse_host_line(raw: str) -> TurnEvent | object:
    """Boundary parse. Unknown t or missing v is PROTOCOL, never a raw dict to the worker."""
    raise NotImplementedError
```

`host_main.py` runs under `EnginePython` only.

```python
def main() -> None:
    """Refuse to start if this interpreter is the IRIS GUI venv.

    Import AIAgent from the EngineHome checkout (run_agent). Construct with
    session persistence off, terminal and browser toolsets disabled.     Register
    the tool names from the hello line (IRIS_ENGINE_TOOLS) whose
    bodies write tool_call on stdout and wait for tool_result on stdin.
    Map stream_delta_callback to delta lines and tool_progress_callback to
    tool_progress lines. Do not start the aiohttp gateway. Do not spawn MCP.
    """
    raise NotImplementedError
    # TODO: if sys.executable resolves to GuiPython, sys.exit(2)
    # TODO: logging.basicConfig(filename=log_path) before importing run_agent
    # TODO: agent = AIAgent(..., session_id=None, persist=False, disabled toolsets)
    # TODO: agent.run_conversation is driven per turn from the turn line, with
    #       the IRIS messages as the conversation input. Do not open Hermes SQLite.
```

The agent loop stays in upstream `AIAgent`. IRIS does not reimplement it.

The host does not load `config.yaml` MCP servers and does not hardcode tool names. IRIS sends `IRIS_ENGINE_TOOLS` in hello. A tool call is an IPC line. IRIS runs `call_registered(surface, action, args)`. That is the same function the Control Surface HTTP path uses today. Browser, YouTube, wiki, and IDE actions do not get a second invoke.

## Approval

```python
DANGEROUS_ACTIONS: frozenset[str] = frozenset(
    {
        "project.write_file",
        "project.run",
        "project.rename_file",
        "project.create_scaffold",
    }
)


def assert_dangerous_actions_confirm(registry: object) -> None:
    """Boot check. Every name in DANGEROUS_ACTIONS has confirm_required=True.
    Existing high-risk actions (email.send, chat.clear_history, …) already set
    the flag. This set is the extra file and terminal list. One list. The
    registry is derived. A missing flag fails startup, not a later turn.
    """
    raise NotImplementedError
```

`ActionRegistry.invoke` already calls `ask_human` when `confirm_required` is set. The hosted tool path reuses that. The HUD is the approval UI. There is no second confirm prompt in the engine package.

A denied confirm returns `ok: false` to the host as `tool_result`. It is not a Qt exception.

`status=timeout` on `call_registered` still does not cancel queued UI work. That contract stays. Cancel of a turn sends a `cancel` line to the host. An in-flight `project.run` may finish. The worker still ends the SSE-equivalent iterator.

## Compat adapter (private)

```python
class CompatSession:
    def stream_turn(self, request: _TurnRequest, should_cancel: Callable[[], bool]) -> Iterator[TurnEvent]:
        """HermesClient.stream_chat. Parse SSE dicts into TurnEvent here. Do not
        yield ev.get('content') to the worker.
        """
        raise NotImplementedError
        # TODO: ensure_hermes_gateway_running(...)
        # TODO: sync_iris_control + iris-control MCP stay on this path only
```

`HermesClient`, `:8642`, Bearer `API_SERVER_KEY`, and `iris_control_stdio` exist only inside `_compat.py`. The worker never constructs `HermesClient`.

## Qt and crash domain

A ruff or import-linter rule rejects `run_agent`, `hermes_cli`, and `iris.engine.host_main` from `iris.ui` and from any module imported by `MainWindow`. The rule is the guard. A comment list is not.

`HermesChatWorker.run` and `HermesHealthWorker.run` stay the only threads that call `ensure` and `stream_turn`. They already wrap `run` in `try/except` and `failed.emit`. A host crash is `TurnFailed(HOST_EXIT)` or `EngineFailure(HOST_EXIT)`. The supervisor may restart on the next `ensure`. The GUI process does not import Hermes, so a native fault in Hermes deps cannot become `0xC0000409` through a Qt slot.

The GUI process still runs `ActionRegistry` handlers. Those already marshal through `MainThreadInvoker`. That path is unchanged.

## Env and license

Hosted install clones the MIT tree into `EngineHome` (`~/.iris-light/engine/hermes-agent`), not into the IRIS repo. `LICENSE.md` §3.4 stays unbundled. The notice stays in the cloned tree. The §3.4 row changes "HTTP 호출" to "IPC 호출" and drops the `:8642` wording for the default product. Compat still uses HTTP.

`probe` of `EnginePython` imports `hermes_cli, aiohttp, mcp, ruamel.yaml, dotenv` in that interpreter before spawn. A 3.11 tree that "installed" but cannot import `aiohttp` is `PYTHON_RANGE`, not a later host crash.

Ollama stays a fourth process on `:11434` when the model is local. It is the inference backend. It is not the agent.

## Settings

```python
class EngineMode(Enum):
    HOSTED = "hosted"
    COMPAT = "compat"
```

One field. Default `HOSTED`. `hermes_enabled` remains True and remains un-settable to False, so `_use_hermes_backend()` and `hermes_owns_local_intents` do not need a rewrite. `hermes_base_url` is a compat input.

After the migrate, delete public `ensure_hermes_gateway_running` from chat and health workers in the same change. Compat imports it privately.
