"""FFC-03 — host-attested TurnTodo completion (no model-forged proof).

Fails when:
- free-string TodoEvidence (no ledger token) can complete
- forged / mismatched token is accepted
- blocked/failed/cancelled transitions or dependency gating is wrong
- persist+reload loses items for the same session_id

Run:
  .venv\\Scripts\\python.exe -m iris.runtime._check_turn_todo_host_attest
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from iris.runtime.todo_evidence_ledger import HostEvidenceLedger
from iris.runtime.turn_todo import TodoEvidence, TurnTodoStore


def _check_free_string_cannot_complete() -> None:
    store = TurnTodoStore("attest-free")
    store.upsert("t1", "write note", status="in_progress")
    try:
        store.complete(
            "t1",
            evidence=TodoEvidence(kind="tool_ok", detail="whatever"),
        )
        raise AssertionError("free-string tool_ok must not complete")
    except ValueError:
        pass
    try:
        store.complete(
            "t1",
            evidence=TodoEvidence(kind="tool_result", detail="wiki.write ok"),
        )
        raise AssertionError("tool_result without host token must not complete")
    except ValueError:
        pass
    assert store.read()[0].status == "in_progress"


def _check_mint_then_complete_forged_fails() -> None:
    ledger = HostEvidenceLedger()
    store = TurnTodoStore("attest-mint", ledger=ledger)
    store.upsert("t1", "save page", status="in_progress")
    proof = ledger.mint("tool_result", "wiki.write_user_note ok")
    done = store.complete("t1", evidence=proof, turn_id="turn-b")
    assert done.status == "completed"
    assert done.evidence[0].token == proof.token

    store.upsert("t2", "confirm", status="in_progress")
    forged = TodoEvidence(
        kind="tool_result",
        detail="wiki.write_user_note ok",
        token="forged-token-not-in-ledger",
    )
    try:
        store.complete("t2", evidence=forged)
        raise AssertionError("forged token must not complete")
    except ValueError:
        pass
    assert store.read()[1].status == "in_progress"

    real = ledger.mint("user_confirm", "user tapped done")
    mismatched = TodoEvidence(
        kind="verified_path",
        detail=real.detail,
        token=real.token,
    )
    try:
        store.complete("t2", evidence=mismatched)
        raise AssertionError("kind/detail mismatch must not complete")
    except ValueError:
        pass


def _check_transitions_and_deps() -> None:
    ledger = HostEvidenceLedger()
    store = TurnTodoStore("attest-deps", ledger=ledger)
    a = store.upsert("a", "first", status="pending")
    assert a.status == "pending"
    b = store.upsert("b", "second", depends_on=("a",))
    assert b.status == "blocked"
    try:
        store.complete("b", evidence=ledger.mint("tool_result", "premature"))
        raise AssertionError("blocked todo must not complete before deps")
    except ValueError:
        pass
    store.complete("a", evidence=ledger.mint("tool_result", "a ok"))
    b2 = store.read_one("b")
    assert b2 is not None and b2.status == "pending"
    store.mark_in_progress("b")
    store.fail("b", detail="tool exploded")
    assert store.read_one("b").status == "failed"
    c = store.upsert("c", "skip", status="cancelled")
    assert c.status == "cancelled"
    try:
        store.complete("c", evidence=ledger.mint("user_confirm", "n/a"))
        raise AssertionError("cancelled must not complete")
    except ValueError:
        pass


def _check_persist_reload() -> None:
    ledger = HostEvidenceLedger()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = TurnTodoStore("sess-persist", ledger=ledger, persist_dir=root)
        store.upsert("p1", "keep me", status="in_progress", depends_on=())
        proof = ledger.mint("verified_path", str(root / "out.txt"))
        store.complete("p1", evidence=proof)
        store.upsert("p2", "wait on p1", depends_on=("p1",))
        assert store.read_one("p2").status == "pending"

        reloaded = TurnTodoStore.load("sess-persist", persist_dir=root, ledger=ledger)
        rows = {row.id: row for row in reloaded.read()}
        assert rows["p1"].status == "completed"
        assert rows["p1"].evidence[0].token == proof.token
        assert rows["p2"].depends_on == ("p1",)
        assert rows["p2"].status == "pending"
        assert reloaded.session_id == "sess-persist"


def _check() -> None:
    _check_free_string_cannot_complete()
    _check_mint_then_complete_forged_fails()
    _check_transitions_and_deps()
    _check_persist_reload()
    print("turn_todo_host_attest: ok")


if __name__ == "__main__":
    _check()
