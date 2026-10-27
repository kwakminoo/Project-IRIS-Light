"""Qt-side sidecar protocol parse.

Agent-readable:
- Owns: host-line dicts into TurnEvent, and host command lines out.
- Does not: spawn a child or import Hermes.
- Talks to: iris.engine.types.
- Extend via: add a parser in _PARSERS. Keep unknown names as PROTOCOL.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from iris.engine.types import (
    ContentDelta,
    EngineError,
    EngineErrorCode,
    ToolProgress,
    TurnCancelled,
    TurnEvent,
    TurnFailed,
    TurnFinished,
)


def _text(raw: dict, key: str) -> str:
    value = raw.get(key, "")
    if value is None:
        return ""
    return str(value)


def _error_code(raw: object) -> EngineErrorCode:
    try:
        return EngineErrorCode(str(raw))
    except ValueError:
        return EngineErrorCode.UNKNOWN


def _protocol(detail: str) -> TurnFailed:
    return TurnFailed(EngineError(EngineErrorCode.PROTOCOL, detail))


def _parse_delta(raw: dict) -> TurnEvent:
    return ContentDelta(text=_text(raw, "text"))


def _parse_tool(raw: dict) -> TurnEvent:
    return ToolProgress(label=_text(raw, "label"))


def _parse_done(raw: dict) -> TurnEvent:
    return TurnFinished(text=_text(raw, "text"))


def _parse_fail(raw: dict) -> TurnEvent:
    return TurnFailed(EngineError(_error_code(raw.get("code")), _text(raw, "detail")))


def _parse_cancel(_raw: dict) -> TurnEvent:
    return TurnCancelled()


_PARSERS: dict[str, Callable[[dict], TurnEvent]] = {
    "delta": _parse_delta,
    "tool": _parse_tool,
    "tool_progress": _parse_tool,
    "done": _parse_done,
    "fail": _parse_fail,
    "cancel": _parse_cancel,
}


def encode_host_command(kind: str, **fields: object) -> str:
    """One NDJSON line for the child stdin."""
    payload = {"t": kind, **fields}
    return json.dumps(payload, ensure_ascii=False) + "\n"


def parse_turn_event(raw: dict) -> TurnEvent:
    """Sidecar stdout boundary. Unknown event names become TurnFailed(PROTOCOL)."""
    try:
        if not isinstance(raw, dict):
            return _protocol("event must be a dict")
        kind = raw.get("t")
        parser = _PARSERS.get(kind) if isinstance(kind, str) else None
        if parser is None:
            return _protocol(f"unknown event: {kind!r}")
        return parser(raw)
    except Exception as exc:
        return _protocol(str(exc))
