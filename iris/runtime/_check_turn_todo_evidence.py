"""FRC-03 — Todo completion requires evidence (session-scoped store).

Fails when:
- completed upsert/complete accepts empty evidence
- cancelled item can be completed
- store accepts blank session_id
- revision does not bump on real writes

Run:
  .venv\\Scripts\\python.exe -m iris.runtime._check_turn_todo_evidence
"""

from __future__ import annotations

from iris.runtime.turn_todo import TodoEvidence, TurnTodoStore, require_completion_evidence


def _check_require_gate() -> None:
    try:
        require_completion_evidence(None)
        raise AssertionError("expected ValueError for None evidence")
    except ValueError:
        pass
    try:
        require_completion_evidence(TodoEvidence(kind="tool_ok", detail=""))
        raise AssertionError("expected ValueError for empty detail")
    except ValueError:
        pass
    ok = require_completion_evidence(TodoEvidence(kind="tool_ok", detail="wiki.write ok"))
    assert ok.kind == "tool_ok"
    assert ok.detail == "wiki.write ok"


def _check_store_rejects_blank_session() -> None:
    try:
        TurnTodoStore("")
        raise AssertionError("expected ValueError for blank session_id")
    except ValueError:
        pass


def _check_complete_requires_evidence() -> None:
    store = TurnTodoStore("17")
    store.upsert("t1", "save page", status="in_progress", turn_id="turn-a")
    assert store.revision == 1
    try:
        store.upsert("t1", "save page", status="completed")
        raise AssertionError("completed without evidence must fail")
    except ValueError:
        pass
    assert store.read()[0].status == "in_progress"
    done = store.complete(
        "t1",
        evidence=TodoEvidence(kind="tool_ok", detail="wiki.write_user_note ok"),
        turn_id="turn-b",
    )
    assert done.status == "completed"
    assert done.session_id == "17"
    assert done.turn_id == "turn-b"
    assert done.evidence[0].detail.endswith("ok")
    assert store.revision == 2
    assert store.active() == []


def _check_cancelled_cannot_complete() -> None:
    store = TurnTodoStore("sess")
    store.upsert("x", "skip me", status="cancelled")
    try:
        store.complete(
            "x",
            evidence=TodoEvidence(kind="user_confirm", detail="n/a"),
        )
        raise AssertionError("cancelled must not complete")
    except ValueError:
        pass


def _check() -> None:
    _check_require_gate()
    _check_store_rejects_blank_session()
    _check_complete_requires_evidence()
    _check_cancelled_cannot_complete()
    print("turn_todo_evidence: ok")


if __name__ == "__main__":
    _check()
