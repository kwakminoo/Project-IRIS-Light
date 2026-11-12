"""App Host ↔ page message helpers (Phase 1 ping/pong)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AppHostPhase(Enum):
    IDLE = "idle"
    LOADING = "loading"
    READY = "ready"
    CLOSED = "closed"


@dataclass(frozen=True)
class AppHostOffer:
    title: str
    html_path: str


@dataclass(frozen=True)
class AppHostMessage:
    method: str
    params: dict[str, Any] = field(default_factory=dict)
    id: str | int | None = None


METHOD_PING = "iris.app/ping"
METHOD_PONG = "iris.app/pong"


def serialize_message(msg: AppHostMessage) -> str:
    payload: dict[str, Any] = {
        "method": str(msg.method or ""),
        "params": dict(msg.params or {}),
    }
    if msg.id is not None:
        payload["id"] = msg.id
    return json.dumps(payload, ensure_ascii=False)


def parse_message(raw: str | bytes | dict[str, Any] | None) -> AppHostMessage | None:
    if raw is None:
        return None
    try:
        if isinstance(raw, dict):
            data = raw
        else:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            text = text.strip()
            if not text:
                return None
            data = json.loads(text)
        if not isinstance(data, dict):
            return None
        method = str(data.get("method") or "").strip()
        if not method:
            return None
        params = data.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return None
        msg_id = data.get("id")
        if msg_id is not None and not isinstance(msg_id, (str, int)):
            msg_id = str(msg_id)
        return AppHostMessage(method=method, params=params, id=msg_id)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def pong_for(ping: AppHostMessage) -> AppHostMessage:
    return AppHostMessage(method=METHOD_PONG, params=dict(ping.params or {}), id=ping.id)
