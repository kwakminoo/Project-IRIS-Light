"""FFC-03 — Delegation session domain (grants, depth, concurrency, cancel, aggregate).

Fails when:
- child grants escalate beyond parent
- depth >= max_depth is accepted
- more than max_children active for one parent
- cancel does not mark cancelled / call handle.cancel / orphan_guard
- aggregate mixes foreign parent sessions
- parent drop leaves active children without orphan_guard

Run:
  .venv\\Scripts\\python.exe -m iris.runtime._check_delegate_session
"""

from __future__ import annotations

from iris.runtime.delegate_session import (
    DelegateBudget,
    DelegateSessionRegistry,
    ParentCtx,
)


class _FakeHandle:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


def _factory(**_kwargs):
    return _FakeHandle()


def _budget(*, children: int = 2, depth: int = 2) -> DelegateBudget:
    return DelegateBudget(
        max_tokens=1024,
        max_seconds=30.0,
        max_children=children,
        max_depth=depth,
    )


def _check_grant_escalation_rejected() -> None:
    reg = DelegateSessionRegistry(engine_factory=_factory)
    parent = ParentCtx(session_id="p1", grants=frozenset({"wiki.read", "mail.read"}))
    try:
        reg.spawn(
            parent,
            "steal",
            grants=frozenset({"wiki.read", "wiki.write"}),
            budget=_budget(),
            depth=0,
        )
        raise AssertionError("grant escalation must be rejected")
    except PermissionError:
        pass
    ok = reg.spawn(
        parent,
        "read only",
        grants=frozenset({"wiki.read"}),
        budget=_budget(),
        depth=0,
    )
    assert ok.grants_intersection == frozenset({"wiki.read"})
    assert ok.status == "running"


def _check_depth_limit() -> None:
    reg = DelegateSessionRegistry(engine_factory=_factory)
    parent = ParentCtx(session_id="p-depth", grants=frozenset({"x"}))
    budget = _budget(depth=2)
    reg.spawn(parent, "leaf", grants=frozenset({"x"}), budget=budget, depth=0)
    reg.spawn(parent, "mid", grants=frozenset({"x"}), budget=budget, depth=1)
    try:
        reg.spawn(parent, "too deep", grants=frozenset({"x"}), budget=budget, depth=2)
        raise AssertionError("depth == max_depth must fail")
    except ValueError as exc:
        assert "depth" in str(exc).lower()


def _check_concurrency_limit() -> None:
    reg = DelegateSessionRegistry(engine_factory=_factory)
    parent = ParentCtx(session_id="p-conc", grants=frozenset({"x"}))
    budget = _budget(children=2, depth=3)
    a = reg.spawn(parent, "a", grants=frozenset({"x"}), budget=budget, depth=0)
    b = reg.spawn(parent, "b", grants=frozenset({"x"}), budget=budget, depth=0)
    assert a.status == "running" and b.status == "running"
    try:
        reg.spawn(parent, "c", grants=frozenset({"x"}), budget=budget, depth=0)
        raise AssertionError("third active child must fail")
    except ValueError as exc:
        assert "concurrency" in str(exc).lower()
    reg.finish(a.child_id, status="done", result="ok-a")
    c = reg.spawn(parent, "c", grants=frozenset({"x"}), budget=budget, depth=0)
    assert c.status == "running"


def _check_cancel_propagates() -> None:
    handles: list[_FakeHandle] = []

    def factory(**_kwargs):
        h = _FakeHandle()
        handles.append(h)
        return h

    reg = DelegateSessionRegistry(engine_factory=factory)
    parent = ParentCtx(session_id="p-cancel", grants=frozenset({"x"}))
    child = reg.spawn(
        parent,
        "work",
        grants=frozenset({"x"}),
        budget=_budget(),
        depth=0,
    )
    out = reg.cancel(child.child_id)
    assert out.status == "cancelled"
    assert out.orphan_guard is True
    assert handles and handles[0].cancelled is True


def _check_aggregate_rejects_foreign_session() -> None:
    reg = DelegateSessionRegistry(engine_factory=_factory)
    pa = ParentCtx(session_id="sess-a", grants=frozenset({"x"}))
    pb = ParentCtx(session_id="sess-b", grants=frozenset({"x"}))
    budget = _budget(children=4, depth=3)
    ca = reg.spawn(pa, "task-a", grants=frozenset({"x"}), budget=budget, depth=0)
    cb = reg.spawn(pb, "task-b", grants=frozenset({"x"}), budget=budget, depth=0)
    reg.finish(ca.child_id, status="done", result="A")
    reg.finish(cb.child_id, status="done", result="B")
    try:
        reg.finish(ca.child_id, status="done", result="hack", parent_session_id="sess-b")
        raise AssertionError("foreign session finish must fail")
    except PermissionError:
        pass
    only_a = reg.aggregate("sess-a")
    only_b = reg.aggregate("sess-b")
    assert [r.child_id for r in only_a] == [ca.child_id]
    assert only_a[0].result == "A"
    assert [r.child_id for r in only_b] == [cb.child_id]
    assert only_b[0].result == "B"
    mixed_ids = {r.child_id for r in only_a} & {r.child_id for r in only_b}
    assert not mixed_ids


def _check_orphan_guard_on_parent_drop() -> None:
    handles: list[_FakeHandle] = []

    def factory(**_kwargs):
        h = _FakeHandle()
        handles.append(h)
        return h

    reg = DelegateSessionRegistry(engine_factory=factory)
    parent = ParentCtx(session_id="p-drop", grants=frozenset({"x"}))
    budget = _budget(children=3, depth=3)
    c1 = reg.spawn(parent, "one", grants=frozenset({"x"}), budget=budget, depth=0)
    c2 = reg.spawn(parent, "two", grants=frozenset({"x"}), budget=budget, depth=0)
    reg.finish(c2.child_id, status="done", result="kept")
    touched = reg.drop_parent("p-drop")
    assert {t.child_id for t in touched} == {c1.child_id, c2.child_id}
    left = reg.get(c1.child_id)
    done = reg.get(c2.child_id)
    assert left is not None and left.status == "cancelled" and left.orphan_guard is True
    assert done is not None and done.status == "done" and done.orphan_guard is True
    assert handles[0].cancelled is True
    try:
        reg.spawn(parent, "after drop", grants=frozenset({"x"}), budget=budget, depth=0)
        raise AssertionError("spawn after parent drop must fail")
    except ValueError:
        pass


def _check() -> None:
    _check_grant_escalation_rejected()
    _check_depth_limit()
    _check_concurrency_limit()
    _check_cancel_propagates()
    _check_aggregate_rejects_foreign_session()
    _check_orphan_guard_on_parent_drop()
    print("delegate_session: ok")


if __name__ == "__main__":
    _check()
