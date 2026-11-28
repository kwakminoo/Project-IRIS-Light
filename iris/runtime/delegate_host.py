"""Host helpers for DelegateSession Speak/Control wire (FFC-03 Unit 4d).

Process-wide registry + production Engine.fork factory. Tests inject fakes.
"""

from __future__ import annotations

import threading
from typing import Any

from iris.runtime.delegate_session import DelegateSessionRegistry, EngineFactory

_lock = threading.RLock()
_registry: DelegateSessionRegistry | None = None


class ForkedEngineHandle:
    """Thin cancel adapter over a real ``Engine.fork()`` result."""

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    def cancel(self) -> None:
        # ponytail: best-effort child shutdown; full sidecar teardown is later.
        shutdown = getattr(self._engine, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown()
            except Exception:
                pass


def production_engine_factory(**_kwargs: Any) -> ForkedEngineHandle:
    """Production path: must call ``shared_engine().fork()`` (not a no-op)."""
    from iris.engine.runtime import shared_engine

    child = shared_engine().fork()
    return ForkedEngineHandle(child)


def shared_delegate_registry(
    *,
    engine_factory: EngineFactory | None = None,
) -> DelegateSessionRegistry:
    """Process-wide DelegateSessionRegistry (inject factory for tests)."""
    global _registry
    with _lock:
        if engine_factory is not None:
            _registry = DelegateSessionRegistry(engine_factory=engine_factory)
            return _registry
        if _registry is None:
            _registry = DelegateSessionRegistry(
                engine_factory=production_engine_factory
            )
        return _registry


def reset_delegate_registry(
    *,
    engine_factory: EngineFactory | None = None,
) -> DelegateSessionRegistry:
    """Test/teardown helper — replace the process registry."""
    global _registry
    with _lock:
        _registry = DelegateSessionRegistry(
            engine_factory=engine_factory or production_engine_factory
        )
        return _registry
