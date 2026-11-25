"""Wire-level tool enforcement (``agent.tool_choice: required``).

Vendored from NousResearch/hermes-agent PR #145164 (kfezer/feat/tool-choice-required).
Iris install overlay copies this into hermes-agent/agent/tool_choice.py.

Small local models often answer "I'll install it now" and stop. With ``required`` the
request carries ``tool_choice="required"`` plus a ``respond`` exit tool. A respond-only
reply is unwrapped to plain text at intake.

Iris addition: provider 400 on tool_choice demotes that base_url to auto for later turns
(see ``demote_tool_choice_for_endpoint``) so one bad backend never kills the whole chat.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

RESPOND_TOOL_NAME = "respond"
_SUPPORTED_API_MODES = ("chat_completions",)

RESPOND_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": RESPOND_TOOL_NAME,
        "description": (
            "Send your reply to the user and end your turn. This is the only way to talk to the "
            "user: plain text replies are disabled. Do the work with your other tools first; call "
            "this when the task is done, when you need the user's input, or to report a real "
            "blocker. Never use it to announce work you have not done yet."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The full reply shown to the user (markdown ok).",
                },
            },
            "required": ["message"],
        },
    },
}


def _demotion_path() -> Path:
    home = os.environ.get("HERMES_HOME") or os.environ.get("IRIS_AGENT_HOME")
    if home:
        return Path(home) / "tool_choice_demoted.json"
    return Path.home() / ".iris-light" / "agent" / "tool_choice_demoted.json"


def _endpoint_key(agent: Any) -> str:
    base = str(getattr(agent, "base_url", "") or "").strip().rstrip("/").lower()
    provider = str(getattr(agent, "provider", "") or "").strip().lower()
    return f"{provider}|{base}" if base or provider else ""


def is_endpoint_demoted(agent: Any) -> bool:
    key = _endpoint_key(agent)
    if not key:
        return False
    path = _demotion_path()
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    demoted = data.get("demoted") if isinstance(data, dict) else None
    return isinstance(demoted, list) and key in demoted


def demote_tool_choice_for_endpoint(agent: Any, *, reason: str = "") -> str:
    """Record this endpoint as auto-only after a tool_choice 400. Returns activity line."""
    key = _endpoint_key(agent)
    if not key:
        return ""
    path = _demotion_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {"demoted": []}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("demoted"), list):
                data = loaded
        except (OSError, ValueError, TypeError):
            pass
    demoted = list(data.get("demoted") or [])
    if key not in demoted:
        demoted.append(key)
        data["demoted"] = demoted
        if reason:
            notes = dict(data.get("notes") or {})
            notes[key] = str(reason)[:240]
            data["notes"] = notes
        try:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
    agent._tool_choice = "auto"
    agent._tool_choice_disabled = True
    return f"tool_choice 미지원 → auto 유지 ({key})"


def looks_like_tool_choice_rejection(exc: BaseException | str) -> bool:
    text = str(exc or "").lower()
    if "tool_choice" not in text:
        return False
    return any(
        token in text
        for token in ("400", "unsupported", "invalid", "not support", "must be one of", "unknown")
    )


def tool_choice_required(agent: Any) -> bool:
    """True when ``agent.tool_choice`` is ``required`` for chat_completions and not demoted."""
    if getattr(agent, "_tool_choice_disabled", False) or is_endpoint_demoted(agent):
        return False
    value = getattr(agent, "_tool_choice", "auto") or "auto"
    if isinstance(value, dict):
        value = value.get(getattr(agent, "platform", None) or "cli", value.get("default", "auto"))
    value = str(value or "auto").strip().lower()
    return value == "required" and getattr(agent, "api_mode", None) in _SUPPORTED_API_MODES


def apply_tool_choice(agent: Any, tools_for_api: Optional[list], request_overrides: dict) -> tuple:
    """``(tools, request_overrides)``: respond tool + ``tool_choice=\"required\"`` when enabled."""
    if not tools_for_api or "tool_choice" in request_overrides or not tool_choice_required(agent):
        return tools_for_api, request_overrides
    return with_respond_tool(tools_for_api), {**request_overrides, "tool_choice": "required"}


def with_respond_tool(tools: Optional[list]) -> Optional[list]:
    if not tools:
        return tools
    if any((t.get("function") or {}).get("name") == RESPOND_TOOL_NAME for t in tools):
        return tools
    return [*tools, RESPOND_TOOL_SCHEMA]


def _respond_message(arguments: str) -> str:
    try:
        parsed = json.loads(arguments or "{}")
    except (TypeError, ValueError):
        return str(arguments or "")
    message = parsed.get("message") if isinstance(parsed, dict) else parsed
    if message is None:
        return ""
    return message if isinstance(message, str) else json.dumps(message)


def unwrap_respond_call(assistant_message: Any) -> bool:
    """Turn a ``respond`` call into plain-text; True when it did."""
    tool_calls = getattr(assistant_message, "tool_calls", None) or []
    responds = [tc for tc in tool_calls if getattr(tc, "name", None) == RESPOND_TOOL_NAME]
    if not responds:
        return False
    others = [tc for tc in tool_calls if getattr(tc, "name", None) != RESPOND_TOOL_NAME]
    if others:
        logger.info(
            "tool_choice=required: dropping respond call issued alongside %d tool call(s)",
            len(others),
        )
        assistant_message.tool_calls = others
        return False
    text = "\n\n".join(m for m in (_respond_message(tc.arguments) for tc in responds) if m)
    assistant_message.content = text or assistant_message.content
    assistant_message.tool_calls = None
    assistant_message.finish_reason = "stop"
    return True
