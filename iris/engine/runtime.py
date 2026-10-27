"""Process-wide engine handle.

Agent-readable:
- Owns: one child slot, one lock, and the process singleton.
- Does not: spawn a sidecar or import Hermes.
- Talks to: iris.engine.types and iris.engine._home probe.
- Extend via: Engine.ensure_ready / run_turn / shutdown.
"""

from __future__ import annotations

import os
from threading import Lock
from types import SimpleNamespace
from typing import Iterator

from iris.engine._home import probe_engine_python
from iris.engine.types import (
    EngineEnsureResult,
    EngineError,
    EngineErrorCode,
    EngineFailed,
    EngineReady,
    EngineSource,
    ExternalGateway,
    InternalSidecar,
    StatelessTurn,
    TurnCancelled,
    TurnEvent,
    TurnFailed,
    parse_engine_source,
)

_SHARED_LOCK = Lock()
_SHARED: Engine | None = None


def _settings_from_env() -> object:
    return SimpleNamespace(
        hermes_external_gateway=os.environ.get("IRIS_HERMES_EXTERNAL_GATEWAY", ""),
        hermes_base_url=os.environ.get("IRIS_HERMES_BASE_URL", ""),
        hermes_api_key=os.environ.get("IRIS_HERMES_API_KEY", ""),
    )


class Engine:
    """One sidecar, one lock, one home."""

    def __init__(self, source: EngineSource) -> None:
        self._source = source
        self._lock = Lock()
        self._child = None

    def ensure_ready(self) -> EngineEnsureResult:
        try:
            with self._lock:
                if self._child is not None:
                    return EngineReady(self._source, "engine is ready")
                if isinstance(self._source, ExternalGateway):
                    return EngineFailed(
                        EngineError(
                            EngineErrorCode.UNKNOWN,
                            "external Hermes gateway is not wired",
                        )
                    )
                if isinstance(self._source, InternalSidecar):
                    probe = probe_engine_python(self._source.home)
                    if probe is not None:
                        return EngineFailed(probe)
                    return EngineFailed(
                        EngineError(
                            EngineErrorCode.SPAWN_FAILED,
                            "sidecar spawn is not wired",
                        )
                    )
                return EngineFailed(
                    EngineError(
                        EngineErrorCode.NOT_INSTALLED,
                        "engine sidecar is not installed",
                    )
                )
        except Exception as exc:
            return EngineFailed(EngineError(EngineErrorCode.UNKNOWN, str(exc)))

    def run_turn(self, turn: StatelessTurn) -> Iterator[TurnEvent]:
        try:
            if turn.cancel.cancelled():
                yield TurnCancelled()
                return
            ready = self.ensure_ready()
            if isinstance(ready, EngineFailed):
                yield TurnFailed(ready.error)
                return
            yield TurnFailed(
                EngineError(EngineErrorCode.NOT_INSTALLED, "sidecar is not running")
            )
        except Exception as exc:
            yield TurnFailed(EngineError(EngineErrorCode.UNKNOWN, str(exc)))

    def shutdown(self) -> None:
        try:
            with self._lock:
                self._child = None
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
