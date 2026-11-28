"""Host helpers for TurnTodo Speak/Control wire (FFC-03 Unit 4b).

Session-scoped store registry + mint helpers. Model never mints tokens.
"""

from __future__ import annotations

import threading
from pathlib import Path

from iris.runtime.todo_evidence_ledger import HostEvidenceLedger
from iris.runtime.turn_todo import TodoEvidence, TurnTodoStore

_lock = threading.RLock()
_stores: dict[str, TurnTodoStore] = {}


def mint_tool_result(
    ledger: HostEvidenceLedger,
    *,
    call_id_or_run_id: str,
    tool_name: str,
    ok: bool,
) -> TodoEvidence:
    """Host-only proof that a tool call finished (kind=tool_result)."""
    call = str(call_id_or_run_id or "").strip() or "unknown"
    name = str(tool_name or "").strip() or "tool"
    status = "ok" if ok else "fail"
    return ledger.mint("tool_result", f"{name} {status} call={call}")


def session_todo_store(
    session_id: str,
    *,
    persist_dir: Path | str | None = None,
) -> TurnTodoStore:
    """In-process TurnTodoStore keyed by conversation/session id."""
    sid = str(session_id or "").strip()
    if not sid:
        raise ValueError("session_id required")
    with _lock:
        store = _stores.get(sid)
        if store is not None:
            return store
        store = TurnTodoStore(sid, ledger=HostEvidenceLedger(), persist_dir=persist_dir)
        _stores[sid] = store
        return store


def drop_session_todo_store(session_id: str) -> None:
    """Test/teardown helper — remove one session store from the registry."""
    sid = str(session_id or "").strip()
    if not sid:
        return
    with _lock:
        _stores.pop(sid, None)
