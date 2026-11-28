"""FFC-03 — clarify await/resume domain state machine.

Question text alone is not success. Callers must receive a ResumeTicket
and use it to continue the turn. No Speak/UI wire here — domain + check only.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

ClarifyState = Literal["idle", "awaiting", "resumed", "expired", "cancelled"]
VALID_STATES = frozenset({"idle", "awaiting", "resumed", "expired", "cancelled"})


@dataclass(frozen=True)
class ClarifySnapshot:
    question_id: str
    question_text: str
    original_goal: str
    progress_note: str
    permission_fingerprint: str
    created_at: float
    expires_at: float
    session_id: str
    turn_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "question_id", str(self.question_id or "").strip())
        object.__setattr__(self, "question_text", str(self.question_text or "").strip())
        object.__setattr__(self, "original_goal", str(self.original_goal or "").strip())
        object.__setattr__(self, "progress_note", str(self.progress_note or "").strip())
        object.__setattr__(
            self,
            "permission_fingerprint",
            str(self.permission_fingerprint or "").strip(),
        )
        object.__setattr__(self, "session_id", str(self.session_id or "").strip())
        object.__setattr__(self, "turn_id", str(self.turn_id or "").strip())
        if not self.question_id:
            raise ValueError("question_id required")
        if not self.question_text:
            raise ValueError("question_text required")
        if not self.session_id:
            raise ValueError("session_id required")
        if float(self.expires_at) < float(self.created_at):
            raise ValueError("expires_at must be >= created_at")


@dataclass(frozen=True)
class ResumeTicket:
    """Proof that an awaiting clarify was answered. Required to continue the turn."""

    question_id: str
    answer: str
    snapshot_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "question_id", str(self.question_id or "").strip())
        object.__setattr__(self, "answer", str(self.answer or "").strip())
        object.__setattr__(self, "snapshot_hash", str(self.snapshot_hash or "").strip())
        if not self.question_id:
            raise ValueError("ResumeTicket.question_id required")
        if not self.answer:
            raise ValueError("ResumeTicket.answer required")
        if not self.snapshot_hash:
            raise ValueError("ResumeTicket.snapshot_hash required")


def snapshot_hash(snap: ClarifySnapshot) -> str:
    payload = "\0".join(
        (
            snap.question_id,
            snap.question_text,
            snap.original_goal,
            snap.progress_note,
            snap.permission_fingerprint,
            repr(float(snap.created_at)),
            repr(float(snap.expires_at)),
            snap.session_id,
            snap.turn_id,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def require_resume_ticket(value: object) -> ResumeTicket:
    """Gate: question text (or bare answer) is not a valid continue token."""
    if isinstance(value, ResumeTicket):
        if not value.question_id or not value.answer or not value.snapshot_hash:
            raise ValueError("ResumeTicket fields required")
        return value
    raise ValueError("ResumeTicket required to continue turn")


class ClarifyWaitStore:
    """One clarify wait per session. States: idle|awaiting|resumed|expired|cancelled."""

    def __init__(self, session_id: str) -> None:
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("session_id required")
        self._session_id = sid
        self._state: ClarifyState = "idle"
        self._snapshot: ClarifySnapshot | None = None

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def state(self) -> ClarifyState:
        return self._state

    @property
    def snapshot(self) -> ClarifySnapshot | None:
        return self._snapshot

    def open(
        self,
        question_id: str,
        question_text: str,
        *,
        original_goal: str = "",
        progress_note: str = "",
        permission_fingerprint: str = "",
        ttl_seconds: float = 300.0,
        expires_at: float | None = None,
        turn_id: str = "",
        now: float | None = None,
    ) -> ClarifySnapshot:
        if self._state == "awaiting":
            raise ValueError("already awaiting a clarify")
        clock = float(time.time() if now is None else now)
        ttl = float(ttl_seconds)
        if ttl <= 0 and expires_at is None:
            raise ValueError("ttl_seconds must be > 0")
        end = float(expires_at) if expires_at is not None else clock + ttl
        snap = ClarifySnapshot(
            question_id=question_id,
            question_text=question_text,
            original_goal=original_goal,
            progress_note=progress_note,
            permission_fingerprint=permission_fingerprint,
            created_at=clock,
            expires_at=end,
            session_id=self._session_id,
            turn_id=turn_id,
        )
        self._snapshot = snap
        self._state = "awaiting"
        return snap

    def resume(
        self,
        question_id: str,
        user_answer: str,
        *,
        revalidate_permissions: Callable[[], str],
        now: float | None = None,
    ) -> ResumeTicket:
        qid = str(question_id or "").strip()
        answer = str(user_answer or "").strip()
        if not answer:
            raise ValueError("user_answer required")
        if self._state != "awaiting" or self._snapshot is None:
            raise ValueError(f"cannot resume from state {self._state!r}")
        snap = self._snapshot
        if qid != snap.question_id:
            raise ValueError("question_id mismatch")
        clock = float(time.time() if now is None else now)
        if clock >= float(snap.expires_at):
            self._state = "expired"
            raise ValueError("clarify expired")
        current_fp = str(revalidate_permissions() or "").strip()
        if current_fp != snap.permission_fingerprint:
            raise ValueError("permission fingerprint mismatch")
        ticket = ResumeTicket(
            question_id=snap.question_id,
            answer=answer,
            snapshot_hash=snapshot_hash(snap),
        )
        self._state = "resumed"
        return ticket

    def expire(self) -> ClarifySnapshot:
        if self._state != "awaiting" or self._snapshot is None:
            raise ValueError(f"cannot expire from state {self._state!r}")
        self._state = "expired"
        return self._snapshot

    def cancel(self) -> ClarifySnapshot:
        if self._state != "awaiting" or self._snapshot is None:
            raise ValueError(f"cannot cancel from state {self._state!r}")
        self._state = "cancelled"
        return self._snapshot
