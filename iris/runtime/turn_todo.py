"""FRC-03 — session-scoped todo list with completion evidence.

Model claims are not completion. A todo may move to ``completed`` only with
non-empty evidence (tool ok line, verified path, user confirm, etc.).
No Speak/UI wire here — domain + check only.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

VALID_STATUSES = frozenset({"pending", "in_progress", "completed", "cancelled"})
_ACTIVE = frozenset({"pending", "in_progress"})


@dataclass(frozen=True)
class TodoEvidence:
    """One proof that a todo finished (or was cancelled with a note)."""

    kind: str
    detail: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", str(self.kind or "").strip())
        object.__setattr__(self, "detail", str(self.detail or "").strip())


@dataclass(frozen=True)
class TodoItem:
    id: str
    content: str
    status: str = "pending"
    evidence: tuple[TodoEvidence, ...] = ()
    turn_id: str = ""
    session_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", str(self.id or "").strip())
        object.__setattr__(self, "content", str(self.content or "").strip())
        status = str(self.status or "pending").strip().lower()
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid todo status: {self.status!r}")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "turn_id", str(self.turn_id or "").strip())
        object.__setattr__(self, "session_id", str(self.session_id or "").strip())
        if not self.id:
            raise ValueError("todo id required")
        if not self.content:
            raise ValueError("todo content required")


def require_completion_evidence(evidence: TodoEvidence | None) -> TodoEvidence:
    """Gate for completed status. Empty kind/detail is rejected."""
    if evidence is None:
        raise ValueError("completed requires evidence")
    if not evidence.kind or not evidence.detail:
        raise ValueError("completed requires non-empty evidence kind and detail")
    return evidence


class TurnTodoStore:
    """One in-memory list per session_id. Replace/merge by id; complete is gated."""

    def __init__(self, session_id: str) -> None:
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("session_id required")
        self._session_id = sid
        self._items: dict[str, TodoItem] = {}
        self._revision = 0

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def revision(self) -> int:
        return self._revision

    def read(self) -> list[TodoItem]:
        return list(self._items.values())

    def upsert(
        self,
        item_id: str,
        content: str,
        *,
        status: str = "pending",
        evidence: TodoEvidence | None = None,
        turn_id: str = "",
    ) -> TodoItem:
        status_n = str(status or "pending").strip().lower()
        proofs: tuple[TodoEvidence, ...] = ()
        if status_n == "completed":
            proofs = (require_completion_evidence(evidence),)
        elif evidence is not None and evidence.kind and evidence.detail:
            proofs = (evidence,)
        item = TodoItem(
            id=item_id,
            content=content,
            status=status_n,
            evidence=proofs,
            turn_id=turn_id,
            session_id=self._session_id,
        )
        before = self._items.get(item.id)
        self._items[item.id] = item
        if before != item:
            self._revision += 1
        return item

    def complete(
        self,
        item_id: str,
        *,
        evidence: TodoEvidence,
        turn_id: str = "",
    ) -> TodoItem:
        tid = str(item_id or "").strip()
        cur = self._items.get(tid)
        if cur is None:
            raise KeyError(f"todo not found: {tid}")
        if cur.status == "cancelled":
            raise ValueError("cancelled todo cannot complete")
        proof = require_completion_evidence(evidence)
        next_item = replace(
            cur,
            status="completed",
            evidence=(proof,),
            turn_id=str(turn_id or cur.turn_id).strip(),
            session_id=self._session_id,
        )
        if next_item != cur:
            self._revision += 1
        self._items[tid] = next_item
        return next_item

    def active(self) -> list[TodoItem]:
        return [row for row in self.read() if row.status in _ACTIVE]
