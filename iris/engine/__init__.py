"""IRIS-owned Hermes engine.

Agent-readable:
- Owns: domain types for a sidecar turn and the process engine handle.
- Does not: import Hermes, bind :8642, or talk to Qt.
- Talks to: chat workers via ChatTranscript and StatelessTurn.
- Extend via: public names in types.py and runtime.py. Private names stay off __all__.
"""

from iris.engine.runtime import Engine, shared_engine
from iris.engine.types import (
    CancelToken,
    ChatMessage,
    ChatTranscript,
    ContentDelta,
    EngineEnsureResult,
    EngineError,
    EngineErrorCode,
    EngineFailed,
    EngineHome,
    EnginePython,
    EngineReady,
    EngineSource,
    ExternalGateway,
    GuiPython,
    HermesHome,
    InternalSidecar,
    Role,
    StatelessTurn,
    ToolProgress,
    TurnCancelled,
    TurnEvent,
    TurnFailed,
    TurnFinished,
    UserUtterance,
    parse_engine_source,
)

__all__ = [
    "CancelToken",
    "ChatMessage",
    "ChatTranscript",
    "ContentDelta",
    "Engine",
    "EngineEnsureResult",
    "EngineError",
    "EngineErrorCode",
    "EngineFailed",
    "EngineHome",
    "EnginePython",
    "EngineReady",
    "EngineSource",
    "ExternalGateway",
    "GuiPython",
    "HermesHome",
    "InternalSidecar",
    "Role",
    "StatelessTurn",
    "ToolProgress",
    "TurnCancelled",
    "TurnEvent",
    "TurnFailed",
    "TurnFinished",
    "UserUtterance",
    "parse_engine_source",
    "shared_engine",
]
