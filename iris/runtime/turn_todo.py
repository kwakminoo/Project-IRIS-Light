"""FFC-03 — session-scoped todo list with host-attested completion evidence.

Model claims are not completion. A todo may move to ``completed`` only with
host-minted ``TodoEvidence`` (ledger token + kind ∈ completion kinds).
No Speak/UI wire here — domain + check only.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from iris.runtime.todo_evidence_ledger import HostEvidenceLedger

COMPLETION_KINDS = frozenset({"tool_result", "verified_path", "user_confirm"})
VALID_STATUSES = frozenset(
    {"pending", "in_progress", "blocked", "completed", "failed", "cancelled"}
)
_TERMINAL = frozenset({"completed", "failed", "cancelled"})
_ACTIVE = frozenset({"pending", "in_progress", "blocked"})


@dataclass(frozen=True)
class TodoEvidence:
    """Host-attested proof that a todo finished.

    ``token`` is opaque and must match a ``HostEvidenceLedger`` mint for
    completion. Free strings without a ledger entry are rejected.
    """

    kind: str
    detail: str
    token: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", str(self.kind or "").strip())
        object.__setattr__(self, "detail", str(self.detail or "").strip())
        object.__setattr__(self, "token", str(self.token or "").strip())


@dataclass(frozen=True)
class TodoItem:
    id: str
    content: str
    status: str = "pending"
    evidence: tuple[TodoEvidence, ...] = ()
    turn_id: str = ""
    session_id: str = ""
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", str(self.id or "").strip())
        object.__setattr__(self, "content", str(self.content or "").strip())
        status = str(self.status or "pending").strip().lower()
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid todo status: {self.status!r}")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "turn_id", str(self.turn_id or "").strip())
        object.__setattr__(self, "session_id", str(self.session_id or "").strip())
        deps = tuple(
            str(d or "").strip()
            for d in (self.depends_on or ())
            if str(d or "").strip()
        )
        object.__setattr__(self, "depends_on", deps)
        if not self.id:
            raise ValueError("todo id required")
        if not self.content:
            raise ValueError("todo content required")


def require_completion_evidence(evidence: TodoEvidence | None) -> TodoEvidence:
    """Shape gate for completed status (kind/detail/token non-empty + kind set).

    Does not consult the host ledger — callers that complete must also
    ``ledger.verify``. Kept for callers that only need shape checks.
    """
    if evidence is None:
        raise ValueError("completed requires evidence")
    if evidence.kind not in COMPLETION_KINDS:
        raise ValueError(
            f"completion kind must be one of {sorted(COMPLETION_KINDS)}, "
            f"got {evidence.kind!r}"
        )
    if not evidence.detail:
        raise ValueError("completed requires non-empty evidence detail")
    if not evidence.token:
        raise ValueError("completed requires host-minted evidence token")
    return evidence


def _default_ledger() -> HostEvidenceLedger:
    from iris.runtime.todo_evidence_ledger import HostEvidenceLedger

    return HostEvidenceLedger()


class TurnTodoStore:
    """One list per session_id. Complete is gated by host ledger attestation."""

    def __init__(
        self,
        session_id: str,
        *,
        ledger: HostEvidenceLedger | None = None,
        persist_dir: Path | str | None = None,
    ) -> None:
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("session_id required")
        self._session_id = sid
        self._items: dict[str, TodoItem] = {}
        self._revision = 0
        self._lock = threading.RLock()
        self._ledger = ledger if ledger is not None else _default_ledger()
        self._persist_dir = Path(persist_dir) if persist_dir else None

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def ledger(self) -> HostEvidenceLedger:
        return self._ledger

    def read(self) -> list[TodoItem]:
        with self._lock:
            return list(self._items.values())

    def read_one(self, item_id: str) -> TodoItem | None:
        tid = str(item_id or "").strip()
        with self._lock:
            return self._items.get(tid)

    def upsert(
        self,
        item_id: str,
        content: str,
        *,
        status: str = "pending",
        evidence: TodoEvidence | None = None,
        turn_id: str = "",
        depends_on: Sequence[str] = (),
    ) -> TodoItem:
        with self._lock:
            status_n = str(status or "pending").strip().lower()
            deps = tuple(
                str(d or "").strip() for d in depends_on if str(d or "").strip()
            )
            proofs: tuple[TodoEvidence, ...] = ()
            if status_n == "completed":
                proofs = (self._attest(evidence),)
            elif evidence is not None and evidence.kind and evidence.detail and evidence.token:
                proofs = (self._attest(evidence),)
            if status_n not in _TERMINAL and deps and not self._deps_satisfied(deps):
                status_n = "blocked"
            item = TodoItem(
                id=item_id,
                content=content,
                status=status_n,
                evidence=proofs,
                turn_id=turn_id,
                session_id=self._session_id,
                depends_on=deps,
            )
            before = self._items.get(item.id)
            self._items[item.id] = item
            if before != item:
                self._revision += 1
            self._refresh_blocked()
            self._persist()
            return self._items[item.id]

    def complete(
        self,
        item_id: str,
        *,
        evidence: TodoEvidence,
        turn_id: str = "",
    ) -> TodoItem:
        with self._lock:
            tid = str(item_id or "").strip()
            cur = self._items.get(tid)
            if cur is None:
                raise KeyError(f"todo not found: {tid}")
            if cur.status == "cancelled":
                raise ValueError("cancelled todo cannot complete")
            if cur.status == "failed":
                raise ValueError("failed todo cannot complete")
            if cur.status == "completed":
                raise ValueError("todo already completed")
            if cur.depends_on and not self._deps_satisfied(cur.depends_on):
                raise ValueError("todo blocked until dependencies completed")
            if cur.status == "blocked":
                raise ValueError("todo blocked until dependencies completed")
            proof = self._attest(evidence)
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
            self._refresh_blocked()
            self._persist()
            return next_item

    def fail(self, item_id: str, *, detail: str = "") -> TodoItem:
        with self._lock:
            tid = str(item_id or "").strip()
            cur = self._items.get(tid)
            if cur is None:
                raise KeyError(f"todo not found: {tid}")
            if cur.status in _TERMINAL:
                raise ValueError(f"{cur.status} todo cannot fail")
            note = str(detail or "").strip() or "failed"
            next_item = replace(
                cur,
                status="failed",
                evidence=(TodoEvidence(kind="tool_result", detail=note),),
            )
            if next_item != cur:
                self._revision += 1
            self._items[tid] = next_item
            self._persist()
            return next_item

    def cancel(self, item_id: str, *, detail: str = "") -> TodoItem:
        with self._lock:
            tid = str(item_id or "").strip()
            cur = self._items.get(tid)
            if cur is None:
                raise KeyError(f"todo not found: {tid}")
            if cur.status == "completed":
                raise ValueError("completed todo cannot cancel")
            note = str(detail or "").strip() or "cancelled"
            next_item = replace(
                cur,
                status="cancelled",
                evidence=(TodoEvidence(kind="user_confirm", detail=note),),
            )
            if next_item != cur:
                self._revision += 1
            self._items[tid] = next_item
            self._persist()
            return next_item

    def mark_in_progress(self, item_id: str) -> TodoItem:
        with self._lock:
            tid = str(item_id or "").strip()
            cur = self._items.get(tid)
            if cur is None:
                raise KeyError(f"todo not found: {tid}")
            if cur.status in _TERMINAL:
                raise ValueError(f"{cur.status} todo cannot mark in_progress")
            if cur.depends_on and not self._deps_satisfied(cur.depends_on):
                raise ValueError("todo blocked until dependencies completed")
            next_item = replace(cur, status="in_progress")
            if next_item != cur:
                self._revision += 1
            self._items[tid] = next_item
            self._persist()
            return next_item

    def active(self) -> list[TodoItem]:
        return [row for row in self.read() if row.status in _ACTIVE]

    def _attest(self, evidence: TodoEvidence | None) -> TodoEvidence:
        shaped = require_completion_evidence(evidence)
        return self._ledger.verify(shaped)

    def _deps_satisfied(self, deps: Sequence[str]) -> bool:
        for dep_id in deps:
            row = self._items.get(dep_id)
            if row is None or row.status != "completed":
                return False
        return True

    def _refresh_blocked(self) -> None:
        changed = False
        for tid, row in list(self._items.items()):
            if row.status in _TERMINAL:
                continue
            if not row.depends_on:
                continue
            if self._deps_satisfied(row.depends_on):
                if row.status == "blocked":
                    self._items[tid] = replace(row, status="pending")
                    changed = True
            elif row.status != "blocked":
                self._items[tid] = replace(row, status="blocked")
                changed = True
        if changed:
            self._revision += 1

    def _persist_path(self) -> Path | None:
        if self._persist_dir is None:
            return None
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        return self._persist_dir / f"{self._session_id}.json"

    def _persist(self) -> None:
        path = self._persist_path()
        if path is None:
            return
        payload = {
            "session_id": self._session_id,
            "revision": self._revision,
            "items": [
                {
                    "id": row.id,
                    "content": row.content,
                    "status": row.status,
                    "turn_id": row.turn_id,
                    "session_id": row.session_id,
                    "depends_on": list(row.depends_on),
                    "evidence": [asdict(ev) for ev in row.evidence],
                }
                for row in self._items.values()
            ],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(
        cls,
        session_id: str,
        *,
        persist_dir: Path | str,
        ledger: HostEvidenceLedger | None = None,
    ) -> TurnTodoStore:
        store = cls(session_id, ledger=ledger, persist_dir=persist_dir)
        path = store._persist_path()
        if path is None or not path.is_file():
            return store
        raw = json.loads(path.read_text(encoding="utf-8"))
        with store._lock:
            for row in raw.get("items") or []:
                proofs = tuple(
                    TodoEvidence(
                        kind=str(ev.get("kind") or ""),
                        detail=str(ev.get("detail") or ""),
                        token=str(ev.get("token") or ""),
                    )
                    for ev in (row.get("evidence") or [])
                )
                item = TodoItem(
                    id=str(row.get("id") or ""),
                    content=str(row.get("content") or ""),
                    status=str(row.get("status") or "pending"),
                    evidence=proofs,
                    turn_id=str(row.get("turn_id") or ""),
                    session_id=store._session_id,
                    depends_on=tuple(row.get("depends_on") or ()),
                )
                store._items[item.id] = item
            store._revision = int(raw.get("revision") or 0)
            # Re-seed ledger so reloaded tokens still verify for later completes.
            for item in store._items.values():
                for ev in item.evidence:
                    if ev.token and ev.kind in COMPLETION_KINDS and ev.detail:
                        store._ledger.restore(ev)
        return store
