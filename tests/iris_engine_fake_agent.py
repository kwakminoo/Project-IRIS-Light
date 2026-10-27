"""In-process stand-in for Hermes AIAgent. Used only by sidecar spawn tests."""

from __future__ import annotations

import json
import os

_CTORS: list[dict] = []
_RUNS: list[dict] = []


def _record_path() -> str:
    return os.environ.get("IRIS_ENGINE_AGENT_RECORD", "").strip()


def _flush() -> None:
    path = _record_path()
    if not path:
        return
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"ctors": _CTORS, "runs": _RUNS}, handle)


class AIAgent:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.stream_delta_callback = kwargs.get("stream_delta_callback")
        self._persist_disabled = False
        recorded = {
            key: value
            for key, value in kwargs.items()
            if key not in {"stream_delta_callback", "tool_progress_callback"}
        }
        _CTORS.append(recorded)
        _flush()

    def run_conversation(self, user_message=None, conversation_history=None, **kwargs):
        _RUNS.append(
            {
                "user_message": user_message,
                "conversation_history": conversation_history,
                "persist_disabled": bool(getattr(self, "_persist_disabled", False)),
                **kwargs,
            }
        )
        _flush()
        callback = self.stream_delta_callback
        if callback is not None:
            callback("Hel")
            callback("lo")
        return {"final_response": "Hello"}
