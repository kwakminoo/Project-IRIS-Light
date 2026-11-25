"""U02 — Trusted Execution Context.

Created only by Agent Runtime / authenticated Control. Model tool args must never
be the authority for session ACL, ownership, or workspace_root path policy.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Mapping

# Keys that invite forgery when accepted from Speak / tool args.
TRUST_FIELD_KEYS = frozenset(
    {
        "session_id",
        "conversation_id",
        "turn_id",
        "tool_call_id",
        "request_id",
        "workspace_id",
        "workspace_root",
        "owner",
        "owner_token",
        "principal",
        "permission_scope",
        "approval_reference",
        "surface",
    }
)

# Telemetry labels on ProcessRecord.owner — never ACL secrets / privilege tokens.
SURFACE_OWNER_LABELS = frozenset({"project.run", "shell.run"})

ADMIN_SCOPES = frozenset({"admin", "unscoped"})


@dataclass(frozen=True)
class ExecutionContext:
    session_id: str = ""
    conversation_id: str = ""
    turn_id: str = ""
    tool_call_id: str = ""
    request_id: str = ""
    workspace_id: str = ""
    workspace_root: str = ""
    surface: str = ""
    principal: str = ""
    permission_scope: str = "session"
    approval_reference: str = ""

    def effective_session_id(self) -> str:
        return str(self.session_id or self.conversation_id or "").strip()

    def is_admin(self) -> bool:
        return str(self.permission_scope or "").strip().lower() in ADMIN_SCOPES


def make_execution_context(**kwargs: Any) -> ExecutionContext:
    """Factory for Control / Agent Runtime. Do not build from model args alone."""
    allowed = {f.name for f in fields(ExecutionContext)}
    clean: dict[str, Any] = {}
    for key, value in kwargs.items():
        if key not in allowed:
            continue
        if key == "permission_scope":
            clean[key] = str(value or "session")
        else:
            clean[key] = str(value or "")
    if "permission_scope" not in clean:
        clean["permission_scope"] = "session"
    return ExecutionContext(**clean)


def execution_context_from_control(
    *,
    session_id: str = "",
    conversation_id: str = "",
    turn_id: str = "",
    tool_call_id: str = "",
    request_id: str = "",
    workspace_id: str = "",
    workspace_root: str = "",
    surface: str = "control",
    principal: str = "iris.control",
    permission_scope: str = "session",
    approval_reference: str = "",
) -> ExecutionContext:
    """Authenticated Control-layer builder (window / agent bindings)."""
    return make_execution_context(
        session_id=session_id,
        conversation_id=conversation_id or session_id,
        turn_id=turn_id,
        tool_call_id=tool_call_id,
        request_id=request_id,
        workspace_id=workspace_id,
        workspace_root=workspace_root,
        surface=surface,
        principal=principal,
        permission_scope=permission_scope,
        approval_reference=approval_reference,
    )


def strip_trust_fields(args: Mapping[str, Any] | None) -> dict[str, Any]:
    """Drop forged trust fields from model / Speak payloads."""
    raw = dict(args or {})
    for key in TRUST_FIELD_KEYS:
        raw.pop(key, None)
    return raw


def owner_is_acl_token(owner: str) -> bool:
    """False for surface telemetry labels; True only for real principal tokens."""
    text = str(owner or "").strip()
    if not text:
        return False
    if text in SURFACE_OWNER_LABELS:
        return False
    return True
