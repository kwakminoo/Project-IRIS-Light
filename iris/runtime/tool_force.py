"""ToolForcePolicy helpers — respond unwrap recognition + thin side-effect honesty.

Hermes (PR #145164 overlay) owns wire ``tool_choice=required`` + ``respond``.
Iris only recognizes exit tools and refuses side-effect success when real tools
did not run.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from iris.ui.chat.file_write_claim import CHAT_ONLY, file_create_goal

EXIT_TOOL_NAMES = frozenset({"respond", "chat_only"})
RESPOND_OK_ACTIVITY = "respond ok"

# Thin side-effect branch: create (existing) OR run/install. No keyword sprawl.
_RUN_INSTALL_RE = re.compile(
    r"실행|돌려|run\b|install|설치|pip\s+install|project\.run",
    re.I,
)


@dataclass(frozen=True)
class RespondUnwrap:
    plain_text: str
    was_respond: bool


@dataclass(frozen=True)
class ToolActivity:
    name: str
    record: str
    exit_tool: bool
    count_ok: bool


def tool_activity(message: str) -> ToolActivity | None:
    """Normalize a sidecar tool label without treating tool use as success."""
    text = (message or "").strip()
    if not text:
        return None
    prefix = "[IRIS tool use:"
    if text.startswith(prefix) and text.endswith("]"):
        name = text[len(prefix) : -1].strip().lower()
    else:
        name = text.split(maxsplit=1)[0].strip().lower()
    if not name:
        return None
    exit_tool = is_exit_tool_name(name)
    record = RESPOND_OK_ACTIVITY if exit_tool else text
    from iris.runtime.turn_followthrough import counts_as_tool_ok

    return ToolActivity(name, record, exit_tool, counts_as_tool_ok(record))


def is_exit_tool_name(name: str) -> bool:
    return str(name or "").strip().lower() in EXIT_TOOL_NAMES


def side_effect_goal(goal: str) -> bool:
    """File create OR run/install. Joins VerifyTurn without a second keyword catalog."""
    if file_create_goal(goal).matched:
        return True
    return bool(_RUN_INSTALL_RE.search(goal or ""))


def unwrap_respond_payload(name: str, arguments: str | dict | None) -> RespondUnwrap:
    """Iris recognition of respond/chat_only → plain assistant text."""
    if not is_exit_tool_name(name):
        return RespondUnwrap("", False)
    if isinstance(arguments, dict):
        message = arguments.get("message")
        if message is None and name.lower() == "chat_only":
            message = arguments.get("text") or arguments.get("content")
        text = message if isinstance(message, str) else (json.dumps(message) if message is not None else "")
        return RespondUnwrap(text, True)
    raw = arguments if isinstance(arguments, str) else ""
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return RespondUnwrap(str(raw or ""), True)
    if isinstance(parsed, dict):
        message = parsed.get("message")
        if message is None and name.lower() == "chat_only":
            message = parsed.get("text") or parsed.get("content")
        text = message if isinstance(message, str) else (json.dumps(message) if message is not None else "")
        return RespondUnwrap(text, True)
    return RespondUnwrap(str(parsed), True)


def exit_tool_only(*, tool_ok_count: int, exit_tool_seen: bool) -> bool:
    """True when the turn's only tool activity was respond/chat_only (or none)."""
    return int(tool_ok_count or 0) == 0 and bool(exit_tool_seen)


def honesty_rejects_side_effect_success(
    *,
    goal: str,
    tool_ok_count: int,
    exit_tool_seen: bool = False,
    display: str = "",
) -> bool:
    """Side-effect goal + no real tool ok + exit_tool only (or CHAT_ONLY) → not success."""
    if not side_effect_goal(goal):
        return False
    if int(tool_ok_count or 0) > 0:
        return False
    if exit_tool_seen:
        return True
    return CHAT_ONLY in (display or "")
