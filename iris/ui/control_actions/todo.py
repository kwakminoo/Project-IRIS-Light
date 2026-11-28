"""Native todo.manage — host-attested TurnTodo (Hermes todo_list absorb)."""

from __future__ import annotations

from typing import Any

from iris.runtime.todo_host import session_todo_store
from iris.runtime.turn_todo import TodoItem
from iris.system.control_surface import ActionRegistry, err_result, ok_result
from iris.system.execution_context import host_execution_context, strip_trust_fields


def _trusted_store():
    context = host_execution_context()
    if context is None:
        raise ValueError("todo.manage requires a trusted host turn")
    sid = context.effective_session_id()
    if not sid:
        raise ValueError("todo.manage requires session scope")
    return session_todo_store(sid), context


def _item_payload(item: TodoItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "content": item.content,
        "status": item.status,
        "depends_on": list(item.depends_on),
        "evidence": [
            {"kind": ev.kind, "detail": ev.detail, "token": ev.token}
            for ev in item.evidence
        ],
        "turn_id": item.turn_id,
        "session_id": item.session_id,
    }


def _deps(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        text = raw.strip()
        return (text,) if text else ()
    if isinstance(raw, (list, tuple)):
        return tuple(str(d or "").strip() for d in raw if str(d or "").strip())
    return ()


def register_todo_actions(registry: ActionRegistry) -> None:
    def manage(args: dict[str, Any]) -> dict[str, Any]:
        raw = strip_trust_fields(args if isinstance(args, dict) else {})
        op = str(raw.get("operation") or "").strip().lower()
        try:
            store, context = _trusted_store()
        except ValueError as exc:
            return err_result("todo.manage", str(exc))

        try:
            if op == "list":
                return ok_result(
                    "todo.manage",
                    {"items": [_item_payload(row) for row in store.read()]},
                )

            if op == "upsert":
                item_id = str(raw.get("id") or raw.get("item_id") or "").strip()
                content = str(raw.get("content") or "").strip()
                if not item_id or not content:
                    return err_result("todo.manage", "upsert requires id and content")
                status = str(raw.get("status") or "pending").strip().lower() or "pending"
                if status == "completed":
                    return err_result(
                        "todo.manage",
                        "use operation=complete with host evidence_token",
                    )
                item = store.upsert(
                    item_id,
                    content,
                    status=status,
                    turn_id=str(context.turn_id or ""),
                    depends_on=_deps(raw.get("depends_on")),
                )
                return ok_result("todo.manage", {"item": _item_payload(item)})

            if op == "cancel":
                item_id = str(raw.get("item_id") or raw.get("id") or "").strip()
                if not item_id:
                    return err_result("todo.manage", "cancel requires item_id")
                item = store.cancel(
                    item_id, detail=str(raw.get("detail") or raw.get("content") or "")
                )
                return ok_result("todo.manage", {"item": _item_payload(item)})

            if op == "fail":
                item_id = str(raw.get("item_id") or raw.get("id") or "").strip()
                if not item_id:
                    return err_result("todo.manage", "fail requires item_id")
                item = store.fail(
                    item_id, detail=str(raw.get("detail") or raw.get("content") or "")
                )
                return ok_result("todo.manage", {"item": _item_payload(item)})

            if op == "complete":
                item_id = str(raw.get("item_id") or raw.get("id") or "").strip()
                token = str(raw.get("evidence_token") or "").strip()
                if not item_id or not token:
                    return err_result(
                        "todo.manage",
                        "complete requires item_id and evidence_token",
                    )
                # Host rebuilds evidence from mint metadata; forged token fails here.
                evidence = store.ledger.resolve_token(token)
                item = store.complete(
                    item_id,
                    evidence=evidence,
                    turn_id=str(context.turn_id or ""),
                )
                return ok_result("todo.manage", {"item": _item_payload(item)})

            return err_result("todo.manage", f"unknown operation: {op or '(empty)'}")
        except (KeyError, ValueError) as exc:
            return err_result("todo.manage", str(exc))

    registry.register(
        "todo.manage",
        manage,
        summary=(
            "Session todo list (list|upsert|cancel|fail|complete). "
            "complete requires host-minted evidence_token; model cannot forge completion."
        ),
        risk="low",
        confirm_required=False,
    )
