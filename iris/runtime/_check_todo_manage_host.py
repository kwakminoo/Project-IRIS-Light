"""FFC-03 Unit 4b — todo.manage host wire (upsert → mint → complete).

Fails when:
- forged evidence_token completes a todo
- mint_tool_result + complete path does not land completed
- list omits statuses
- model schema name is not Hermes ``todo_list``

Run:
  .venv\\Scripts\\python.exe -m iris.runtime._check_todo_manage_host
"""

from __future__ import annotations

from iris.infrastructure.speak_capability import (
    PHASE4_ALLOWLIST,
    engine_tool_name,
    engine_tool_schemas,
)
from iris.runtime.todo_host import (
    drop_session_todo_store,
    mint_tool_result,
    session_todo_store,
)
from iris.system.control_surface import ActionRegistry
from iris.system.execution_context import bind_host_tool_call_meta, make_execution_context
from iris.ui.control_actions.todo import register_todo_actions


def _invoke(reg: ActionRegistry, args: dict) -> dict:
    return reg.invoke("todo.manage", args)


def _check_manage_path() -> None:
    sid = "todo-manage-wire-1"
    drop_session_todo_store(sid)
    ctx = make_execution_context(
        session_id=sid,
        conversation_id=sid,
        turn_id="turn-todo-1",
        source="desktop",
        principal="iris.desktop",
    )
    reg = ActionRegistry()
    register_todo_actions(reg)

    with bind_host_tool_call_meta(execution_context=ctx):
        up = _invoke(
            reg,
            {
                "operation": "upsert",
                "id": "t1",
                "content": "write note",
                "status": "in_progress",
            },
        )
        assert up.get("ok") is True, up
        assert up.get("result", {}).get("item", {}).get("status") == "in_progress", up

        forged = _invoke(
            reg,
            {
                "operation": "complete",
                "item_id": "t1",
                "evidence_token": "forged-not-minted",
            },
        )
        assert forged.get("ok") is False, forged
        assert "attested" in str(forged.get("error") or "").lower() or "token" in str(
            forged.get("error") or ""
        ).lower(), forged

        store = session_todo_store(sid)
        proof = mint_tool_result(
            store.ledger,
            call_id_or_run_id="call-wiki-1",
            tool_name="wiki.write_user_note",
            ok=True,
        )
        assert proof.kind == "tool_result"
        assert proof.token

        done = _invoke(
            reg,
            {
                "operation": "complete",
                "item_id": "t1",
                "evidence_token": proof.token,
            },
        )
        assert done.get("ok") is True, done
        assert done.get("result", {}).get("item", {}).get("status") == "completed", done

        listed = _invoke(reg, {"operation": "list"})
        assert listed.get("ok") is True, listed
        items = listed.get("result", {}).get("items") or []
        by_id = {row["id"]: row for row in items}
        assert by_id["t1"]["status"] == "completed", by_id

        up2 = _invoke(
            reg,
            {"operation": "upsert", "id": "t2", "content": "next", "status": "pending"},
        )
        assert up2.get("ok") is True, up2
        listed2 = _invoke(reg, {"operation": "list"})
        statuses = {
            row["id"]: row["status"]
            for row in (listed2.get("result", {}).get("items") or [])
        }
        assert statuses["t1"] == "completed", statuses
        assert statuses["t2"] == "pending", statuses

    drop_session_todo_store(sid)


def _check_schema_absorb() -> None:
    grant = PHASE4_ALLOWLIST.grant("todo.manage")
    assert grant is not None
    assert engine_tool_name("todo.manage") == "todo_list"
    home = {str(row["name"]) for row in engine_tool_schemas("home")}
    assert "todo_list" in home
    assert "todo_manage" not in home


def main() -> None:
    _check_manage_path()
    _check_schema_absorb()
    print("todo_manage_host: ok schema=todo_list")


if __name__ == "__main__":
    main()
