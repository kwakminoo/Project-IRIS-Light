"""Host-minted opaque tokens for TurnTodo completion evidence.

Only the host may mint. Model-supplied free strings have no ledger entry
and must not complete a todo.
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass

from iris.runtime.turn_todo import COMPLETION_KINDS, TodoEvidence


@dataclass(frozen=True)
class _LedgerEntry:
    kind: str
    detail: str


class HostEvidenceLedger:
    """Session-local registry of host-attested completion proofs."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: dict[str, _LedgerEntry] = {}

    def mint(self, kind: str, detail: str) -> TodoEvidence:
        kind_n = str(kind or "").strip()
        detail_n = str(detail or "").strip()
        if kind_n not in COMPLETION_KINDS:
            raise ValueError(
                f"completion kind must be one of {sorted(COMPLETION_KINDS)}, got {kind_n!r}"
            )
        if not detail_n:
            raise ValueError("mint requires non-empty detail")
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._entries[token] = _LedgerEntry(kind=kind_n, detail=detail_n)
        return TodoEvidence(kind=kind_n, detail=detail_n, token=token)

    def resolve_token(self, token: str) -> TodoEvidence:
        """Rebuild TodoEvidence from a host mint. Unknown/forged token → error."""
        token_n = str(token or "").strip()
        if not token_n:
            raise ValueError("completed requires host-minted evidence token")
        with self._lock:
            entry = self._entries.get(token_n)
        if entry is None:
            raise ValueError("evidence token not attested by host ledger")
        return TodoEvidence(kind=entry.kind, detail=entry.detail, token=token_n)

    def verify(self, evidence: TodoEvidence) -> TodoEvidence:
        """Return evidence if token+kind+detail match a mint; else raise."""
        if evidence is None:
            raise ValueError("completed requires host-attested evidence")
        kind = str(evidence.kind or "").strip()
        detail = str(evidence.detail or "").strip()
        token = str(getattr(evidence, "token", "") or "").strip()
        if kind not in COMPLETION_KINDS:
            raise ValueError(
                f"completion kind must be one of {sorted(COMPLETION_KINDS)}, got {kind!r}"
            )
        if not detail:
            raise ValueError("completed requires non-empty evidence detail")
        if not token:
            raise ValueError("completed requires host-minted evidence token")
        with self._lock:
            entry = self._entries.get(token)
        if entry is None:
            raise ValueError("evidence token not attested by host ledger")
        if entry.kind != kind or entry.detail != detail:
            raise ValueError("evidence kind/detail does not match host attestation")
        return evidence

    def restore(self, evidence: TodoEvidence) -> None:
        """Re-seed a previously minted token after persist reload (host-only)."""
        kind = str(evidence.kind or "").strip()
        detail = str(evidence.detail or "").strip()
        token = str(evidence.token or "").strip()
        if not token or kind not in COMPLETION_KINDS or not detail:
            return
        with self._lock:
            self._entries[token] = _LedgerEntry(kind=kind, detail=detail)
