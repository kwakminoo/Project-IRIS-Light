"""UI-slot boundary helper for Iris Agent workers (Qt abort guard)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])
_log = logging.getLogger(__name__)


def safe_agent_ui_slot(fn: _F) -> _F:
    """Wrap slots that receive Iris Agent worker signals.

    Uncaught exceptions leaving a MainWindow slot abort Iris (0xC0000409).
    Agent→UI path must stay signal-only; this wrapper is the thin UI boundary.
    """

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — slot boundary; never re-raise
            _log.exception("agent UI slot contained: %s", exc)
            return None

    return wrapper  # type: ignore[return-value]
