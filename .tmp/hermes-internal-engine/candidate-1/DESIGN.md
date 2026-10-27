# Internal engine types

Reference for `iris.engine`. Bodies are not implemented. Callers are specified in `USAGE.md`. If a signature disagrees with that file, change this file.

## Invariants

- The Qt process never imports `run_agent` or `AIAgent`.
- Default transport is a Hermes-venv sidecar. OpenAI HTTP is only the external-gateway adapter.
- Chat history is IRIS SQLite. The sidecar is given a full transcript and must not persist a Hermes session.
- Tools stay three MCP names into Control Surface HTTP. The engine does not call Qt.
- `ensure_ready` and `shutdown` converge. A second call does not spawn or kill twice.
- Exceptions from Hermes stay in the sidecar or in a QThread `run()`. They do not escape into a Qt slot.
- One process owns the sidecar. Workers share `shared_engine()`. They do not each spawn.

## Public types

```python
# iris/engine/types.py

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterator, Literal, NewType, Union

from iris.infrastructure.hermes_client import HermesInferenceTarget

class Role(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


UserUtterance = NewType("UserUtterance", str)
# Last user text of a turn. Not interchangeable with assistant content.


@dataclass(frozen=True)
class ChatTranscript:
    """IRIS history for one send. No Hermes session id exists on this type."""

    messages: tuple[ChatMessage, ...]

    @classmethod
    def parse(cls, raw: list[dict[str, str]]) -> ChatTranscript:
        """Boundary. Reject unknown roles and missing content."""
        raise NotImplementedError

    def split_for_agent(self) -> tuple[tuple[ChatMessage, ...], UserUtterance]:
        """Prior messages plus the trailing user utterance.

        Illegal when the last role is not USER.
        """
        raise NotImplementedError


# Model identity is iris.infrastructure.hermes_client.HermesInferenceTarget.
# Do not add a parallel InferenceTarget.


class CancelToken:
    """Cross-thread cancel flag. The QThread owns the instance. The engine only reads."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def cancelled(self) -> bool:
        return self._cancelled


@dataclass(frozen=True)
class StatelessTurn:
    transcript: ChatTranscript
    model: HermesInferenceTarget
    cancel: CancelToken


class EngineErrorCode(Enum):
    NOT_INSTALLED = "not_installed"
    WRONG_PYTHON = "wrong_python"
    SPAWN_FAILED = "spawn_failed"
    SIDECAR_DIED = "sidecar_died"
    PROTOCOL = "protocol"
    AUTH = "auth"
    CANCELLED = "cancelled"
    NO_USER_UTTERANCE = "no_user_utterance"
    TOOL_TRANSPORT = "tool_transport"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EngineError:
    code: EngineErrorCode
    detail: str

    @property
    def user_message(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class ContentDelta:
    text: str


@dataclass(frozen=True)
class ToolProgress:
    label: str


@dataclass(frozen=True)
class TurnFinished:
    text: str


@dataclass(frozen=True)
class TurnFailed:
    error: EngineError


@dataclass(frozen=True)
class TurnCancelled:
    pass


TurnEvent = Union[ContentDelta, ToolProgress, TurnFinished, TurnFailed, TurnCancelled]


EngineHome = NewType("EngineHome", Path)
# Directory IRIS owns. Default ~/.iris-light/engine. Not %LOCALAPPDATA%\\hermes.


@dataclass(frozen=True)
class InternalSidecar:
    """Default source. shutdown() kills the child."""

    home: EngineHome
    kill_on_shutdown: Literal[True] = True


@dataclass(frozen=True)
class ExternalGateway:
    """Compatibility only. shutdown() disconnects and does not kill."""

    base_url: str
    api_key: str
    kill_on_shutdown: Literal[False] = False


EngineSource = Union[InternalSidecar, ExternalGateway]


def parse_engine_source(settings: object) -> EngineSource:
    """Settings boundary. Default InternalSidecar.

    ExternalGateway only when settings.hermes_external_gateway is true.
    hermes_enabled stays the 'use the engine' flag. It does not mean ':8642 is up'.
    """
    raise NotImplementedError


@dataclass(frozen=True)
class EngineReady:
    source: EngineSource
    summary: str


@dataclass(frozen=True)
class EngineFailed:
    error: EngineError

    @property
    def user_message(self) -> str:
        return self.error.user_message


EngineEnsureResult = Union[EngineReady, EngineFailed]
```

`InternalSidecar` and `ExternalGateway` cannot share a `kill_on_shutdown` boolean that a caller flips. The field is fixed on the type.

`TurnEvent` has no `done: bool` field and no OpenAI `delta.content` key. Those belong in private parsers.

## Public handle

```python
# iris/engine/runtime.py

from __future__ import annotations

from threading import Lock
from typing import Iterator

from iris.engine.types import (
    EngineEnsureResult,
    EngineFailed,
    EngineReady,
    EngineSource,
    StatelessTurn,
    TurnEvent,
)


class Engine:
    """One sidecar, one lock, one home.

    Callers see ensure_ready, run_turn, shutdown. Install, venv, AIAgent,
    NDJSON, MCP sync, and env stripping stay inside this object.
    """

    def __init__(self, source: EngineSource) -> None:
        self._source = source
        self._lock = Lock()
        self._child = None  # _SidecarChild | _CompatClient | None
        # Internal state is private. Callers never read Installing or Starting.

    def ensure_ready(self) -> EngineEnsureResult:
        """Install if missing. Start if stopped. Sync iris-control.

        Already ready returns EngineReady with no spawn.
        Failed install or spawn returns EngineFailed.
        Must not raise to the caller.
        """
        raise NotImplementedError
        # with self._lock:
        #     if self._child is not None and self._child.alive():
        #         return EngineReady(...)
        #     if isinstance(self._source, InternalSidecar):
        #         install_into(self._source.home)   # reuse hermes_install, new home
        #         probe_runtime(self._source.home)  # reuse probe_hermes_runtime
        #         sync_iris_control(home=self._source.home)
        #         self._child = _SidecarChild.spawn(self._source.home)
        #     else:
        #         self._child = _CompatClient.connect(self._source)
        #     return EngineReady(...) or EngineFailed(...)

    def run_turn(self, turn: StatelessTurn) -> Iterator[TurnEvent]:
        """ensure_ready, then one AIAgent turn. Yields until Finished, Failed, or Cancelled.

        Must not raise. Sidecar death becomes TurnFailed(SIDECAR_DIED).
        CancelToken.cancelled() sends an interrupt to the sidecar and yields TurnCancelled.
        """
        raise NotImplementedError
        # ready = self.ensure_ready()
        # if isinstance(ready, EngineFailed):
        #     yield TurnFailed(ready.error)
        #     return
        # history, user = turn.transcript.split_for_agent()
        # for raw in self._child.stream(history, user, turn.model, turn.cancel):
        #     yield parse_turn_event(raw)

    def shutdown(self) -> None:
        """Kill the sidecar, or drop the external HTTP client.

        Already stopped is a no-op. Must not raise.
        """
        raise NotImplementedError


def shared_engine() -> Engine:
    """Process singleton. First call parses settings. Later calls return the same object."""
    raise NotImplementedError
```

`Engine.__init__` is not a caller API. Tests may construct one. Production code uses `shared_engine()`.

## Private types

These names start with `_`. They are omitted from `iris.engine.__all__`. An import from outside `iris.engine` is a layering break.

```python
# iris/engine/_sidecar.py  (Qt-side child, IRIS interpreter)


@dataclass(frozen=True)
class _SidecarRequest:
    op: Literal["turn", "cancel"]
    # turn fields exist only when op == "turn". Do not put them on a shared bag.


@dataclass(frozen=True)
class _TurnRequest:
    op: Literal["turn"] = "turn"
    history: tuple  # already-parsed ChatMessage tuples, dumped at write time
    user: str
    model: str
    provider: str


@dataclass(frozen=True)
class _CancelRequest:
    op: Literal["cancel"] = "cancel"


def _write_request(proc, req: _TurnRequest | _CancelRequest) -> None:
    """One NDJSON line on the child stdin. Not exported."""
    raise NotImplementedError


def parse_turn_event(raw: dict) -> TurnEvent:
    """Sidecar stdout boundary. Unknown event names become TurnFailed(PROTOCOL)."""
    raise NotImplementedError


class _SidecarChild:
    def spawn(home: EngineHome) -> _SidecarChild:
        """Hermes venv python, iris/engine/_sidecar_main.py as a file path.

        Env from existing _gateway_child_env (strip VIRTUAL_ENV / PYTHONPATH).
        HERMES_HOME = home. CREATE_NO_WINDOW. No CREATE_NEW_PROCESS_GROUP.
        The child must not import the iris package.
        """
        raise NotImplementedError

    def alive(self) -> bool:
        raise NotImplementedError

    def stream(self, history, user, model, cancel) -> Iterator[dict]:
        raise NotImplementedError

    def terminate(self) -> None:
        raise NotImplementedError
```

```python
# iris/engine/_sidecar_main.py  (Hermes interpreter only)

def main() -> None:
    """Read NDJSON. Construct AIAgent. Write NDJSON.

    AIAgent(
        skip_memory=True,
        session_db=None,
        load_soul_identity=True,
        # disabled_toolsets come from config.yaml that sync_iris_control wrote.
        # Do not pass a second list here.
        stream_delta_callback=...,
        tool_progress_callback=...,
    )
    agent._persist_disabled = True
    agent.run_conversation(user_message=user, conversation_history=history)

    Cancel line -> agent.hard_interrupt (InterruptControlMixin).
    No iris imports. No OpenAI HTTP server. No bind of :8642.
    """
    raise NotImplementedError
```

```python
# iris/engine/_compat.py


class _CompatClient:
    """Private wrap of HermesClient. Used only when EngineSource is ExternalGateway."""

    def connect(source: ExternalGateway) -> _CompatClient:
        raise NotImplementedError

    def alive(self) -> bool:
        raise NotImplementedError

    def stream(self, history, user, model, cancel) -> Iterator[dict]:
        """POST /v1/chat/completions. Parse SSE into the same dicts parse_turn_event accepts."""
        raise NotImplementedError

    def terminate(self) -> None:
        """Drop the HTTP client. Do not call hermes gateway stop."""
        raise NotImplementedError
```

```python
# iris/engine/_home.py

def default_internal_home() -> EngineHome:
    """Path.home() / '.iris-light' / 'engine'"""
    raise NotImplementedError


def apply_engine_home(home: EngineHome) -> None:
    """Single writer for HERMES_HOME seen by sync_iris_control and credentials.hermes_home()."""
    raise NotImplementedError
```

## Module map

| Module | Owns | Outsiders import |
|---|---|---|
| `iris/engine/__init__.py` | re-exports in `__all__` | yes |
| `iris/engine/types.py` | domain types above | yes, the public names |
| `iris/engine/runtime.py` | `Engine`, `shared_engine` | yes |
| `iris/engine/_sidecar.py` | child process, NDJSON write | no |
| `iris/engine/_sidecar_main.py` | `AIAgent` loop in Hermes venv | no (spawned as a file) |
| `iris/engine/_compat.py` | `HermesClient` for ExternalGateway | no |
| `iris/engine/_home.py` | engine home path | no |

| Existing module | Change |
|---|---|
| `iris/ui/workers/hermes_workers.py` | Health and chat call `shared_engine()`. Chat drops `base_url` / `api_key` / `command`. Signals stay. |
| `iris/ui/window/main_window.py` | `_launch_chat_turn_bound` stops passing URL and key. `closeEvent` calls `shutdown()`. ChatPanel and UserTurn stay. |
| `iris/ui/control_actions/project.py` | `confirm_required=True` on `project.write_file`, `project.run`, `project.rename_file`. |
| `iris/system/hermes_iris_control_sync.py` | `sync_iris_control` takes the engine home from `_home.apply_engine_home`. Tool list stays three names. |
| `iris/system/hermes_install.py` | Reused. Target directory becomes `EngineHome`, not `%LOCALAPPDATA%\hermes`. |
| `iris/system/hermes_gateway.py` | Health, chat, and SetupProtocol stop calling it in the same change. Probe helpers may stay as private support for `_compat.py`. New code calls `Engine`. |
| `iris/infrastructure/hermes_client.py` | Private to `_compat.py`. Workers stop constructing it. |
| `iris/infrastructure/hermes_credentials.py` | `hermes_home()` follows `apply_engine_home` when source is InternalSidecar. |
| `iris/system/setup_protocol.py` | `_step_hermes_install` / `_step_hermes_gateway` call `ensure_ready`. |
| `iris/mcp/iris_control_stdio.py` | Unchanged. |
| `iris/system/control_surface.py` | Unchanged except the three `confirm_required` flags. |
| `iris/browser/session.py` | Unchanged. |
| `iris/storage/conversations.py` | Unchanged. |
| `LICENSE.md` §3.4 | Relationship text becomes sidecar process, Hermes venv. Still unbundled. MIT notice stays with the checkout. |

## Data flow

```
UserTurn (IRIS SQLite messages)
  -> HermesChatWorker  (QThread, same signals)
    -> Engine.run_turn(StatelessTurn)
      -> _SidecarChild  (Hermes venv)
        -> AIAgent.run_conversation(user, conversation_history)
          -> iris-control MCP stdio
            -> Control Surface HTTP  :8765+
              -> ActionRegistry  (HUD if confirm_required)
                -> BrowserSession / IDE / wiki
      <- TurnEvent
    <- content_chunk / tool_progress / finished_ok / failed
  -> append_message SQLite
```

Three processes on the default tool path. IRIS (Qt + Control Surface), sidecar (AIAgent), MCP stdio. Ollama on `:11434` stays the inference backend when the model is local. No `:8642` process.

## State the lock covers

`Engine._child` is the only write target shared by the health worker, the chat worker, and `closeEvent`. The lock lives on `Engine`. Callers do not take it.

`CancelToken` is written only by the chat worker. The engine reads it. The sidecar does not write it.

SQLite `chat_messages` is written only by MainWindow after `finished_ok`. The sidecar has `session_db=None` and `_persist_disabled=True`.

Control Surface action handlers stay the sole writers of browser and IDE state.

## Approval

```python
# iris/ui/control_actions/project.py  (flags only)

reg.register("project.write_file", ..., risk="medium", confirm_required=True)
reg.register("project.rename_file", ..., risk="medium", confirm_required=True)
reg.register("project.run", ..., risk="medium", confirm_required=True)
```

`ActionRegistry.invoke` already pops `args.confirm`, calls `ask_human`, and returns `cancelled` on deny. No new dialog type.

## Lifecycle

```
missing --ensure_ready--> ready
stopped --ensure_ready--> ready
ready   --ensure_ready--> ready      (no spawn)
ready   --shutdown-----> stopped
failed  --ensure_ready--> ready|failed
any     --sidecar death-> failed     (next ensure_ready respawns)
```

Callers see only `EngineReady` and `EngineFailed`. Installing and starting are not public types.

## Qt fatal

| Site | Rule |
|---|---|
| `HermesHealthWorker.run` | `ensure_ready` returns a value. `except` emits `failed`. |
| `HermesChatWorker.run` | `run_turn` yields `TurnFailed`. `except` emits `failed`. |
| `MainWindow.closeEvent` | `shutdown` swallows child errors. |
| Sidecar | Hermes exceptions die in the Hermes venv. They do not enter Qt. |

## What this package does not do

- Reimplement the agent loop
- Import `AIAgent` in the IRIS venv
- Vendor Hermes into the git tree
- Bind an OpenAI server on the default path
- Fall back to `OllamaChatWorker` when the sidecar fails
- Write Hermes session rows the UI can read
- Cancel an in-flight Control Surface handler after `invoke` has started
