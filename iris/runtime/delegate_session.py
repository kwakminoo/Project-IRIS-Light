"""FFC-03 — delegation session domain over Engine.fork (no Hermes registry).

Parent/child grants intersect at spawn. Budget caps tokens, time, concurrency,
and depth. Cancel and parent-drop mark orphan_guard so children are not left
running without an owner. Production wire uses ``Engine.fork`` via injectable
``engine_factory`` (see ``delegate_host.production_engine_factory``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

CHILD_STATUSES = frozenset({"pending", "running", "done", "failed", "cancelled"})
_ACTIVE = frozenset({"pending", "running"})


@dataclass(frozen=True)
class DelegateBudget:
    max_tokens: int
    max_seconds: float
    max_children: int
    max_depth: int

    def __post_init__(self) -> None:
        if int(self.max_tokens) < 0:
            raise ValueError("max_tokens must be >= 0")
        if float(self.max_seconds) < 0:
            raise ValueError("max_seconds must be >= 0")
        if int(self.max_children) < 1:
            raise ValueError("max_children must be >= 1")
        if int(self.max_depth) < 1:
            raise ValueError("max_depth must be >= 1")


@dataclass(frozen=True)
class ParentCtx:
    """Caller-facing parent snapshot at spawn (session + grants)."""

    session_id: str
    grants: frozenset[str]

    def __post_init__(self) -> None:
        sid = str(self.session_id or "").strip()
        if not sid:
            raise ValueError("parent session_id required")
        object.__setattr__(self, "session_id", sid)
        object.__setattr__(self, "grants", frozenset(str(g) for g in (self.grants or ())))


@dataclass
class DelegateChild:
    child_id: str
    parent_session_id: str
    depth: int
    grants_intersection: frozenset[str]
    budget: DelegateBudget
    status: str = "pending"
    task: str = ""
    result: Any = None
    orphan_guard: bool = False

    def __post_init__(self) -> None:
        status = str(self.status or "pending").strip().lower()
        if status not in CHILD_STATUSES:
            raise ValueError(f"invalid child status: {self.status!r}")
        self.status = status
        self.child_id = str(self.child_id or "").strip()
        self.parent_session_id = str(self.parent_session_id or "").strip()
        self.task = str(self.task or "").strip()
        self.grants_intersection = frozenset(str(g) for g in (self.grants_intersection or ()))
        if not self.child_id:
            raise ValueError("child_id required")
        if not self.parent_session_id:
            raise ValueError("parent_session_id required")


@dataclass(frozen=True)
class ChildAggregate:
    child_id: str
    status: str
    result: Any = None


# (parent_session_id, child_id, task, grants, budget, depth) -> handle with cancel()
EngineFactory = Callable[..., Any]


@dataclass
class DelegateSessionRegistry:
    """In-memory parent→child registry. Inject ``engine_factory``; never call Hermes."""

    engine_factory: EngineFactory
    _children: dict[str, DelegateChild] = field(default_factory=dict, init=False, repr=False)
    _handles: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    _dropped_parents: set[str] = field(default_factory=set, init=False, repr=False)

    def spawn(
        self,
        parent_ctx: ParentCtx,
        task: str,
        *,
        grants: frozenset[str] | set[str] | list[str],
        budget: DelegateBudget,
        depth: int,
    ) -> DelegateChild:
        if not isinstance(parent_ctx, ParentCtx):
            raise TypeError("parent_ctx must be ParentCtx")
        if parent_ctx.session_id in self._dropped_parents:
            raise ValueError("parent session dropped")
        task_s = str(task or "").strip()
        if not task_s:
            raise ValueError("task required")
        requested = frozenset(str(g) for g in grants)
        if not requested <= parent_ctx.grants:
            raise PermissionError("grant escalation rejected")
        depth_i = int(depth)
        if depth_i < 0:
            raise ValueError("depth must be >= 0")
        if depth_i >= int(budget.max_depth):
            raise ValueError("depth limit exceeded")
        active = self._active_count(parent_ctx.session_id)
        if active >= int(budget.max_children):
            raise ValueError("concurrency limit exceeded")

        child_id = uuid4().hex
        child = DelegateChild(
            child_id=child_id,
            parent_session_id=parent_ctx.session_id,
            depth=depth_i,
            grants_intersection=requested,
            budget=budget,
            status="running",
            task=task_s,
        )
        handle = self.engine_factory(
            parent_session_id=parent_ctx.session_id,
            child_id=child_id,
            task=task_s,
            grants=requested,
            budget=budget,
            depth=depth_i,
        )
        self._children[child_id] = child
        self._handles[child_id] = handle
        return child

    def cancel(self, child_id: str) -> DelegateChild:
        child = self._require_child(child_id)
        if child.status in ("done", "failed", "cancelled"):
            return child
        self._cancel_handle(child_id)
        child.status = "cancelled"
        child.orphan_guard = True
        return child

    def drop_parent(self, parent_session_id: str) -> list[DelegateChild]:
        """Parent gone: cancel live children and stamp orphan_guard."""
        sid = str(parent_session_id or "").strip()
        if not sid:
            raise ValueError("parent_session_id required")
        self._dropped_parents.add(sid)
        touched: list[DelegateChild] = []
        for child in list(self._children.values()):
            if child.parent_session_id != sid:
                continue
            if child.status in _ACTIVE:
                self._cancel_handle(child.child_id)
                child.status = "cancelled"
            child.orphan_guard = True
            touched.append(child)
        return touched

    def finish(
        self,
        child_id: str,
        *,
        status: str,
        result: Any = None,
        parent_session_id: str = "",
    ) -> DelegateChild:
        """Mark done/failed. Foreign parent_session_id is rejected."""
        child = self._require_child(child_id)
        want = str(status or "").strip().lower()
        if want not in ("done", "failed"):
            raise ValueError("finish status must be done or failed")
        if child.status == "cancelled":
            raise ValueError("cancelled child cannot finish")
        foreign = str(parent_session_id or "").strip()
        if foreign and foreign != child.parent_session_id:
            raise PermissionError("foreign session rejected")
        child.status = want
        child.result = result
        return child

    def aggregate(self, parent_session_id: str) -> list[ChildAggregate]:
        sid = str(parent_session_id or "").strip()
        if not sid:
            raise ValueError("parent_session_id required")
        out: list[ChildAggregate] = []
        for child in self._children.values():
            if child.parent_session_id != sid:
                continue
            out.append(
                ChildAggregate(
                    child_id=child.child_id,
                    status=child.status,
                    result=child.result,
                )
            )
        return out

    def get(self, child_id: str) -> DelegateChild | None:
        return self._children.get(str(child_id or "").strip())

    def _active_count(self, parent_session_id: str) -> int:
        return sum(
            1
            for c in self._children.values()
            if c.parent_session_id == parent_session_id and c.status in _ACTIVE
        )

    def _require_child(self, child_id: str) -> DelegateChild:
        cid = str(child_id or "").strip()
        child = self._children.get(cid)
        if child is None:
            raise KeyError(f"unknown child_id: {cid!r}")
        return child

    def _cancel_handle(self, child_id: str) -> None:
        handle = self._handles.get(child_id)
        cancel = getattr(handle, "cancel", None) if handle is not None else None
        if callable(cancel):
            cancel()
