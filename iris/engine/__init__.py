"""IRIS-owned Hermes engine.

Agent-readable:
- Owns: domain types for a sidecar turn.
- Does not: spawn the sidecar, import Hermes, or talk to Qt.
- Talks to: chat workers via ChatTranscript and StatelessTurn.
- Extend via: public names in types.py. Private names stay off __all__.
"""

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
]
