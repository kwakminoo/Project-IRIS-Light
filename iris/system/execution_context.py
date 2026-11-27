"""U02 — Trusted Execution Context.

Created only by Agent Runtime / authenticated Control. Model tool args must never
be the authority for session ACL, ownership, or workspace_root path policy.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, fields, replace
from typing import Any, Callable, Iterator, Mapping

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
        "schema_fingerprint",
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
    source: str = ""
    run_id: str = ""
    schema_fingerprint: str = ""

    def effective_session_id(self) -> str:
        return str(self.session_id or self.conversation_id or "").strip()

    def is_admin(self) -> bool:
        return str(self.permission_scope or "").strip().lower() in ADMIN_SCOPES


@dataclass(frozen=True)
class _HostToolCall:
    tool_call_id: str
    request_id: str
    context: ExecutionContext | None
    cancelled: Callable[[], bool] | None


_HOST_TOOL_CALL_META: ContextVar[_HostToolCall | None] = ContextVar("iris_host_tool_call_meta", default=None)


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


@contextmanager
def bind_host_tool_call_meta(
    *, tool_call_id: str = "", request_id: str = "",
    execution_context: ExecutionContext | None = None,
    run_id: str = "", schema_fingerprint: str = "",
    cancelled: Callable[[], bool] | None = None,
) -> Iterator[None]:
    """Scope one host-validated invocation across native dispatch and UI policy."""
    tid = str(tool_call_id or "").strip()
    rid = str(request_id or "").strip()
    if execution_context is not None:
        execution_context = replace(
            execution_context, tool_call_id=tid, request_id=rid,
            run_id=run_id, schema_fingerprint=schema_fingerprint,
        )
    token = _HOST_TOOL_CALL_META.set(_HostToolCall(tid, rid, execution_context, cancelled))
    try:
        yield
    finally:
        _HOST_TOOL_CALL_META.reset(token)


def host_tool_call_meta() -> tuple[str, str]:
    """Return (tool_call_id, request_id) bound by Host for this call, else empty."""
    meta = _HOST_TOOL_CALL_META.get()
    if not meta:
        return "", ""
    return meta.tool_call_id, meta.request_id


def host_execution_context() -> ExecutionContext | None:
    meta = _HOST_TOOL_CALL_META.get()
    return meta.context if meta else None


def host_tool_cancelled() -> bool:
    meta = _HOST_TOOL_CALL_META.get()
    return bool(meta is not None and meta.cancelled is not None and meta.cancelled())


def with_host_tool_call_meta(ctx: ExecutionContext) -> ExecutionContext:
    """Overlay Host-verified call ids onto a trusted ctx (never from model args)."""
    tid, rid = host_tool_call_meta()
    if not tid and not rid:
        return ctx
    return replace(ctx, tool_call_id=tid or ctx.tool_call_id, request_id=rid or ctx.request_id)


def active_turn_id(window: Any) -> str:
    """Turn id from ChatTurnGate when present."""
    gate = getattr(window, "_turn_gate", None)
    if gate is None:
        return ""
    return str(getattr(gate, "active_id", "") or "").strip()


def frozen_turn_execution_context(window: Any) -> ExecutionContext | None:
    """Prefer turn-scoped snapshot on window._turn_execution_meta[active_id]."""
    tid = active_turn_id(window)
    if not tid:
        return None
    meta = getattr(window, "_turn_execution_meta", None)
    if not isinstance(meta, dict):
        return None
    ctx = meta.get(tid)
    return ctx if isinstance(ctx, ExecutionContext) else None


def store_turn_execution_context(
    window: Any, turn_id: str, ctx: ExecutionContext
) -> ExecutionContext:
    """Freeze ctx for this turn_id (fills turn_id when blank/mismatched)."""
    tid = str(turn_id or "").strip()
    if not tid:
        raise ValueError("turn_id required to freeze ExecutionContext")
    if str(ctx.turn_id or "").strip() != tid:
        ctx = replace(ctx, turn_id=tid)
    meta = getattr(window, "_turn_execution_meta", None)
    if not isinstance(meta, dict):
        meta = {}
        setattr(window, "_turn_execution_meta", meta)
    meta[tid] = ctx
    return ctx


def clear_turn_execution_context(window: Any, turn_id: str | None) -> None:
    tid = str(turn_id or "").strip()
    if not tid:
        return
    meta = getattr(window, "_turn_execution_meta", None)
    if isinstance(meta, dict):
        meta.pop(tid, None)


def owner_is_acl_token(owner: str) -> bool:
    """False for surface telemetry labels; True only for real principal tokens."""
    text = str(owner or "").strip()
    if not text:
        return False
    if text in SURFACE_OWNER_LABELS:
        return False
    return True
