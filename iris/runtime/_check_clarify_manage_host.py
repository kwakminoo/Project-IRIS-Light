"""FFC-03 Unit 4c — clarify.manage host wire (open → resume ticket).

Fails when:
- open returns only question text / a done flag instead of awaiting snapshot
- resume does not yield ResumeTicket fields (question_id, answer, snapshot_hash)
- forged resume (wrong fingerprint / wrong question_id / expired) succeeds
- model schema name is not Hermes ``clarify``

Run:
  .venv\\Scripts\\python.exe -m iris.runtime._check_clarify_manage_host
"""

from __future__ import annotations

from iris.infrastructure.speak_capability import (
    PHASE4_ALLOWLIST,
    engine_tool_name,
    engine_tool_schemas,
)
from iris.runtime.clarify_host import drop_session_clarify_store
from iris.runtime.clarify_wait import snapshot_hash, ClarifySnapshot
from iris.system.control_surface import ActionRegistry
from iris.system.execution_context import bind_host_tool_call_meta, make_execution_context
from iris.ui.control_actions.clarify import register_clarify_actions


def _invoke(reg: ActionRegistry, args: dict) -> dict:
    return reg.invoke("clarify.manage", args)


def _check_open_resume_ticket() -> None:
    sid = "clarify-manage-wire-1"
    drop_session_clarify_store(sid)
    ctx = make_execution_context(
        session_id=sid,
        conversation_id=sid,
        turn_id="turn-clarify-1",
        source="desktop",
        principal="iris.desktop",
    )
    reg = ActionRegistry()
    register_clarify_actions(reg)

    with bind_host_tool_call_meta(execution_context=ctx):
        opened = _invoke(
            reg,
            {
                "operation": "open",
                "question_id": "q1",
                "question_text": "Which folder?",
                "original_goal": "open project",
                "progress_note": "need path",
                "permission_fingerprint": "perm-a",
                "ttl_seconds": 120,
            },
        )
        assert opened.get("ok") is True, opened
        snap = opened.get("result") or {}
        assert snap.get("state") == "awaiting", snap
        assert snap.get("question_id") == "q1", snap
        assert snap.get("question_text") == "Which folder?", snap
        assert snap.get("done") is not True, snap
        assert "snapshot_hash" not in snap, snap  # ticket only on resume

        forged_fp = _invoke(
            reg,
            {
                "operation": "resume",
                "question_id": "q1",
                "user_answer": "C:/work",
                "permission_fingerprint": "forged-fp",
            },
        )
        assert forged_fp.get("ok") is False, forged_fp
        assert "fingerprint" in str(forged_fp.get("error") or "").lower(), forged_fp

        forged_qid = _invoke(
            reg,
            {
                "operation": "resume",
                "question_id": "wrong-q",
                "user_answer": "C:/work",
                "permission_fingerprint": "perm-a",
            },
        )
        assert forged_qid.get("ok") is False, forged_qid

        # Still awaiting after forged attempts
        ok = _invoke(
            reg,
            {
                "operation": "resume",
                "question_id": "q1",
                "user_answer": "C:/work",
                "permission_fingerprint": "perm-a",
            },
        )
        assert ok.get("ok") is True, ok
        ticket = ok.get("result") or {}
        assert ticket.get("question_id") == "q1", ticket
        assert ticket.get("answer") == "C:/work", ticket
        assert ticket.get("snapshot_hash"), ticket
        expected = snapshot_hash(
            ClarifySnapshot(
                question_id=str(snap["question_id"]),
                question_text=str(snap["question_text"]),
                original_goal=str(snap.get("original_goal") or ""),
                progress_note=str(snap.get("progress_note") or ""),
                permission_fingerprint=str(snap.get("permission_fingerprint") or ""),
                created_at=float(snap["created_at"]),
                expires_at=float(snap["expires_at"]),
                session_id=str(snap["session_id"]),
                turn_id=str(snap.get("turn_id") or ""),
            )
        )
        assert ticket["snapshot_hash"] == expected, (ticket, expected)

    drop_session_clarify_store(sid)


def _check_cancel_blocks_resume() -> None:
    sid = "clarify-manage-wire-2"
    drop_session_clarify_store(sid)
    ctx = make_execution_context(
        session_id=sid,
        conversation_id=sid,
        turn_id="turn-clarify-2",
        source="desktop",
        principal="iris.desktop",
    )
    reg = ActionRegistry()
    register_clarify_actions(reg)
    with bind_host_tool_call_meta(execution_context=ctx):
        _invoke(
            reg,
            {
                "operation": "open",
                "question_id": "q2",
                "question_text": "Abort?",
                "permission_fingerprint": "p",
            },
        )
        cancelled = _invoke(reg, {"operation": "cancel"})
        assert cancelled.get("ok") is True, cancelled
        assert cancelled.get("result", {}).get("state") == "cancelled"
        bad = _invoke(
            reg,
            {
                "operation": "resume",
                "question_id": "q2",
                "user_answer": "yes",
                "permission_fingerprint": "p",
            },
        )
        assert bad.get("ok") is False, bad
    drop_session_clarify_store(sid)


def _check_schema_absorb() -> None:
    grant = PHASE4_ALLOWLIST.grant("clarify.manage")
    assert grant is not None
    assert engine_tool_name("clarify.manage") == "clarify"
    home = {str(row["name"]) for row in engine_tool_schemas("home")}
    assert "clarify" in home
    assert "clarify_manage" not in home


def main() -> None:
    _check_open_resume_ticket()
    _check_cancel_blocks_resume()
    _check_schema_absorb()
    print("clarify_manage_host: ok schema=clarify")


if __name__ == "__main__":
    main()
