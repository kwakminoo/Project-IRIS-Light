"""Host helpers for ClarifyWait Speak/Control wire (FFC-03 Unit 4c).

Session-scoped store registry. One clarify wait per conversation/session.
"""

from __future__ import annotations

import threading

from iris.runtime.clarify_wait import ClarifyWaitStore

_lock = threading.RLock()
_stores: dict[str, ClarifyWaitStore] = {}


def session_clarify_store(session_id: str) -> ClarifyWaitStore:
    """In-process ClarifyWaitStore keyed by conversation/session id."""
    sid = str(session_id or "").strip()
    if not sid:
        raise ValueError("session_id required")
    with _lock:
        store = _stores.get(sid)
        if store is not None:
            return store
        store = ClarifyWaitStore(sid)
        _stores[sid] = store
        return store


def drop_session_clarify_store(session_id: str) -> None:
    """Test/teardown helper — remove one session store from the registry."""
    sid = str(session_id or "").strip()
    if not sid:
        return
    with _lock:
        _stores.pop(sid, None)
