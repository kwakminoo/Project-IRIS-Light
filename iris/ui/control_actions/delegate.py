"""Native delegate.manage — host DelegateSessionRegistry (Hermes delegate_task).

spawn builds ParentCtx from host session + current Speak grants.
Child grants must be a subset (domain rejects escalation).
"""

from __future__ import annotations

from typing import Any

from iris.infrastructure.speak_capability import (
    PHASE4_ALLOWLIST,
    current_speak_surface,
    grants_for_surface,
)
from iris.runtime.delegate_host import shared_delegate_registry
from iris.runtime.delegate_session import (
    ChildAggregate,
    DelegateBudget,
    DelegateChild,
    ParentCtx,
)
from iris.system.control_surface import ActionRegistry, err_result, ok_result
from iris.system.execution_context import host_execution_context, strip_trust_fields


def _trusted_parent() -> tuple[str, frozenset[str]]:
    context = host_execution_context()
    if context is None:
        raise ValueError("delegate.manage requires a trusted host turn")
    sid = context.effective_session_id()
    if not sid:
        raise ValueError("delegate.manage requires session scope")
    surface = current_speak_surface()
    grants = frozenset(
        str(g.action) for g in grants_for_surface(PHASE4_ALLOWLIST, surface)
    )
    return sid, grants


def _parse_grants(raw: Any, *, parent_grants: frozenset[str]) -> frozenset[str]:
    if raw is None:
        return parent_grants
    if isinstance(raw, str):
        text = raw.strip()
        return frozenset({text}) if text else frozenset()
    if isinstance(raw, (list, tuple, set, frozenset)):
        return frozenset(str(g).strip() for g in raw if str(g).strip())
    raise ValueError("grants must be a list of action ids")


def _budget_from_args(raw: dict[str, Any]) -> DelegateBudget:
    return DelegateBudget(
        max_tokens=int(raw.get("max_tokens", 1024)),
        max_seconds=float(raw.get("max_seconds", 30.0)),
        max_children=int(raw.get("max_children", 2)),
        max_depth=int(raw.get("max_depth", 2)),
    )


def _child_payload(child: DelegateChild) -> dict[str, Any]:
    return {
        "child_id": child.child_id,
        "parent_session_id": child.parent_session_id,
        "status": child.status,
        "task": child.task,
        "depth": child.depth,
        "grants": sorted(child.grants_intersection),
        "orphan_guard": bool(child.orphan_guard),
        "result": child.result,
    }


def _agg_payload(row: ChildAggregate) -> dict[str, Any]:
    return {
        "child_id": row.child_id,
        "status": row.status,
        "result": row.result,
    }


def register_delegate_actions(registry: ActionRegistry) -> None:
    def manage(args: dict[str, Any]) -> dict[str, Any]:
        raw = strip_trust_fields(args if isinstance(args, dict) else {})
        op = str(raw.get("operation") or raw.get("action") or "").strip().lower()
        try:
            session_id, parent_grants = _trusted_parent()
        except ValueError as exc:
            return err_result("delegate.manage", str(exc))

        reg = shared_delegate_registry()
        try:
            if op == "spawn":
                task = str(raw.get("task") or "").strip()
                if not task:
                    return err_result("delegate.manage", "spawn requires task")
                try:
                    grants = _parse_grants(raw.get("grants"), parent_grants=parent_grants)
                    budget = _budget_from_args(raw)
                    depth = int(raw.get("depth", 0))
                except (TypeError, ValueError) as exc:
                    return err_result("delegate.manage", str(exc))
                parent = ParentCtx(session_id=session_id, grants=parent_grants)
                child = reg.spawn(
                    parent,
                    task,
                    grants=grants,
                    budget=budget,
                    depth=depth,
                )
                return ok_result("delegate.manage", _child_payload(child))

            if op == "cancel":
                child_id = str(raw.get("child_id") or "").strip()
                if not child_id:
                    return err_result("delegate.manage", "cancel requires child_id")
                existing = reg.get(child_id)
                if existing is None:
                    return err_result("delegate.manage", f"unknown child_id: {child_id!r}")
                if existing.parent_session_id != session_id:
                    return err_result("delegate.manage", "foreign session rejected")
                child = reg.cancel(child_id)
                return ok_result("delegate.manage", _child_payload(child))

            if op == "aggregate":
                rows = reg.aggregate(session_id)
                return ok_result(
                    "delegate.manage",
                    {"children": [_agg_payload(row) for row in rows]},
                )

            if op == "finish":
                child_id = str(raw.get("child_id") or "").strip()
                status = str(raw.get("status") or "").strip().lower()
                if not child_id or not status:
                    return err_result(
                        "delegate.manage",
                        "finish requires child_id and status",
                    )
                child = reg.finish(
                    child_id,
                    status=status,
                    result=raw.get("result"),
                    parent_session_id=session_id,
                )
                return ok_result("delegate.manage", _child_payload(child))

            return err_result(
                "delegate.manage",
                f"unknown operation: {op or '(empty)'}",
            )
        except PermissionError as exc:
            return err_result("delegate.manage", str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            return err_result("delegate.manage", str(exc))

    registry.register(
        "delegate.manage",
        manage,
        summary=(
            "Delegate a child task via Engine.fork (spawn|cancel|aggregate|finish). "
            "Child grants must be a subset of the parent's current Speak grants. "
            "Does not use the Hermes registry."
        ),
        risk="medium",
        confirm_required=False,
    )
