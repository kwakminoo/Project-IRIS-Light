"""Native clarify.manage — host ClarifyWait (Hermes clarify absorb).

open returns an awaiting snapshot (not done). resume returns ResumeTicket fields.
"""

from __future__ import annotations

from typing import Any

from iris.runtime.clarify_host import session_clarify_store
from iris.runtime.clarify_wait import ClarifySnapshot, ResumeTicket
from iris.system.control_surface import ActionRegistry, err_result, ok_result
from iris.system.execution_context import host_execution_context, strip_trust_fields


def _trusted_store():
    context = host_execution_context()
    if context is None:
        raise ValueError("clarify.manage requires a trusted host turn")
    sid = context.effective_session_id()
    if not sid:
        raise ValueError("clarify.manage requires session scope")
    return session_clarify_store(sid), context


def _snap_payload(snap: ClarifySnapshot, *, state: str) -> dict[str, Any]:
    return {
        "state": state,
        "question_id": snap.question_id,
        "question_text": snap.question_text,
        "original_goal": snap.original_goal,
        "progress_note": snap.progress_note,
        "permission_fingerprint": snap.permission_fingerprint,
        "created_at": snap.created_at,
        "expires_at": snap.expires_at,
        "session_id": snap.session_id,
        "turn_id": snap.turn_id,
    }


def _ticket_payload(ticket: ResumeTicket) -> dict[str, Any]:
    return {
        "question_id": ticket.question_id,
        "answer": ticket.answer,
        "snapshot_hash": ticket.snapshot_hash,
    }


def register_clarify_actions(registry: ActionRegistry) -> None:
    def manage(args: dict[str, Any]) -> dict[str, Any]:
        raw = strip_trust_fields(args if isinstance(args, dict) else {})
        op = str(raw.get("operation") or raw.get("action") or "").strip().lower()
        try:
            store, context = _trusted_store()
        except ValueError as exc:
            return err_result("clarify.manage", str(exc))

        try:
            if op == "open":
                qid = str(raw.get("question_id") or "").strip()
                text = str(raw.get("question_text") or "").strip()
                if not qid or not text:
                    return err_result(
                        "clarify.manage",
                        "open requires question_id and question_text",
                    )
                ttl_raw = raw.get("ttl_seconds", raw.get("ttl", 300.0))
                try:
                    ttl = float(ttl_raw)
                except (TypeError, ValueError):
                    return err_result("clarify.manage", "ttl_seconds must be a number")
                snap = store.open(
                    qid,
                    text,
                    original_goal=str(raw.get("original_goal") or ""),
                    progress_note=str(raw.get("progress_note") or ""),
                    permission_fingerprint=str(
                        raw.get("permission_fingerprint") or ""
                    ),
                    ttl_seconds=ttl,
                    turn_id=str(context.turn_id or raw.get("turn_id") or ""),
                )
                return ok_result(
                    "clarify.manage",
                    _snap_payload(snap, state="awaiting"),
                )

            if op == "resume":
                qid = str(raw.get("question_id") or "").strip()
                answer = str(raw.get("user_answer") or raw.get("answer") or "").strip()
                if not qid or not answer:
                    return err_result(
                        "clarify.manage",
                        "resume requires question_id and user_answer",
                    )
                current_fp = str(raw.get("permission_fingerprint") or "").strip()
                ticket = store.resume(
                    qid,
                    answer,
                    revalidate_permissions=lambda: current_fp,
                )
                return ok_result("clarify.manage", _ticket_payload(ticket))

            if op == "cancel":
                snap = store.cancel()
                return ok_result(
                    "clarify.manage",
                    _snap_payload(snap, state="cancelled"),
                )

            if op == "expire":
                snap = store.expire()
                return ok_result(
                    "clarify.manage",
                    _snap_payload(snap, state="expired"),
                )

            return err_result(
                "clarify.manage",
                f"unknown operation: {op or '(empty)'}",
            )
        except ValueError as exc:
            return err_result("clarify.manage", str(exc))

    registry.register(
        "clarify.manage",
        manage,
        summary=(
            "Clarify await/resume (open|resume|cancel|expire). "
            "open returns awaiting snapshot; resume returns ResumeTicket "
            "(question_id, answer, snapshot_hash). Question text alone is not success."
        ),
        risk="low",
        confirm_required=False,
    )
