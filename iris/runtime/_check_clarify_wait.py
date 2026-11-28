"""FFC-03 — Clarify await/resume state machine.

Fails when:
- await→resume does not yield a ResumeTicket
- resume after expire succeeds
- resume with wrong question_id succeeds
- cancel then resume succeeds
- permission fingerprint mismatch is ignored
- question text alone is accepted as continue token

Run:
  .venv\\Scripts\\python.exe -m iris.runtime._check_clarify_wait
"""

from __future__ import annotations

from collections.abc import Callable

from iris.runtime.clarify_wait import (
    ClarifyWaitStore,
    ResumeTicket,
    require_resume_ticket,
    snapshot_hash,
)


def _fp(value: str) -> Callable[[], str]:
    return lambda: value


def _check_await_resume_ok() -> None:
    store = ClarifyWaitStore("sess-1")
    assert store.state == "idle"
    snap = store.open(
        "q1",
        "Which folder?",
        original_goal="open project",
        progress_note="need path",
        permission_fingerprint="perm-a",
        turn_id="t1",
        now=1_000.0,
        ttl_seconds=60.0,
    )
    assert store.state == "awaiting"
    assert snap.session_id == "sess-1"
    assert snap.expires_at == 1_060.0
    ticket = store.resume(
        "q1",
        "C:/work",
        revalidate_permissions=_fp("perm-a"),
        now=1_010.0,
    )
    assert store.state == "resumed"
    assert isinstance(ticket, ResumeTicket)
    assert ticket.question_id == "q1"
    assert ticket.answer == "C:/work"
    assert ticket.snapshot_hash == snapshot_hash(snap)
    assert require_resume_ticket(ticket) is ticket


def _check_resume_after_expire_fails() -> None:
    store = ClarifyWaitStore("sess-2")
    store.open("q2", "Continue?", permission_fingerprint="p", now=100.0, ttl_seconds=10.0)
    store.expire()
    assert store.state == "expired"
    try:
        store.resume("q2", "yes", revalidate_permissions=_fp("p"), now=105.0)
        raise AssertionError("resume after expire must fail")
    except ValueError:
        pass
    # wall-clock auto-expire on resume
    store2 = ClarifyWaitStore("sess-2b")
    store2.open("q2b", "Still?", permission_fingerprint="p", now=200.0, ttl_seconds=5.0)
    try:
        store2.resume("q2b", "ok", revalidate_permissions=_fp("p"), now=210.0)
        raise AssertionError("resume past expires_at must fail")
    except ValueError:
        pass
    assert store2.state == "expired"


def _check_resume_wrong_id_fails() -> None:
    store = ClarifyWaitStore("sess-3")
    store.open("q3", "Pick one", permission_fingerprint="p", now=1.0, ttl_seconds=30.0)
    try:
        store.resume("other", "x", revalidate_permissions=_fp("p"), now=2.0)
        raise AssertionError("wrong question_id must fail")
    except ValueError:
        pass
    assert store.state == "awaiting"


def _check_cancel_then_resume_fails() -> None:
    store = ClarifyWaitStore("sess-4")
    store.open("q4", "Abortable?", permission_fingerprint="p", now=1.0, ttl_seconds=30.0)
    store.cancel()
    assert store.state == "cancelled"
    try:
        store.resume("q4", "later", revalidate_permissions=_fp("p"), now=2.0)
        raise AssertionError("resume after cancel must fail")
    except ValueError:
        pass


def _check_fingerprint_mismatch_fails() -> None:
    store = ClarifyWaitStore("sess-5")
    store.open(
        "q5",
        "Allow write?",
        permission_fingerprint="fp-old",
        now=1.0,
        ttl_seconds=30.0,
    )
    try:
        store.resume("q5", "yes", revalidate_permissions=_fp("fp-new"), now=2.0)
        raise AssertionError("fingerprint mismatch must fail")
    except ValueError:
        pass
    assert store.state == "awaiting"


def _check_resume_ticket_required() -> None:
    try:
        require_resume_ticket("Which folder?")
        raise AssertionError("question text must not count as resume")
    except ValueError:
        pass
    try:
        require_resume_ticket({"question_id": "q", "answer": "a"})
        raise AssertionError("dict must not count as ResumeTicket")
    except ValueError:
        pass
    try:
        ResumeTicket(question_id="q", answer="", snapshot_hash="h")
        raise AssertionError("empty answer ticket must fail")
    except ValueError:
        pass


def _check_blank_session_rejected() -> None:
    try:
        ClarifyWaitStore("")
        raise AssertionError("blank session_id must fail")
    except ValueError:
        pass


def _check() -> None:
    _check_await_resume_ok()
    _check_resume_after_expire_fails()
    _check_resume_wrong_id_fails()
    _check_cancel_then_resume_fails()
    _check_fingerprint_mismatch_fails()
    _check_resume_ticket_required()
    _check_blank_session_rejected()
    print("clarify_wait: ok")


if __name__ == "__main__":
    _check()
