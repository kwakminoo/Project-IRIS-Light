"""U03 — Request-scoped approval ledger.

One approval binds to one normalized execution fingerprint. Global
``set_human_confirm(lambda: True)`` bypasses are forbidden; model args cannot
forge ledger state (trust fields stripped at Control boundary).
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass, replace
from typing import Any, Mapping

DEFAULT_TTL_S = 300.0
APPROVAL_SCOPE_ONCE = "once"


def normalize_execution_fingerprint(
    *,
    argv: list[str] | None = None,
    shell: str | None = None,
    command: str | None = None,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    """Stable hash of the execution request. Any field change → new fingerprint."""
    argv_norm = [str(x) for x in argv] if isinstance(argv, list) else None
    shell_norm = str(shell or command or "").strip() or None
    cwd_norm = str(cwd or "").strip()
    env_items: list[list[str]] = []
    if isinstance(env, Mapping) and env:
        env_items = [[str(k), str(v)] for k, v in sorted(env.items(), key=lambda kv: str(kv[0]))]
    payload = {
        "argv": argv_norm,
        "shell": shell_norm,
        "cwd": cwd_norm,
        "env": env_items,
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fingerprint_from_manage_args(args: Mapping[str, Any] | None) -> str:
    raw = dict(args or {})
    argv = raw.get("argv")
    shell = raw.get("shell") or raw.get("command")
    env = raw.get("env")
    return normalize_execution_fingerprint(
        argv=list(argv) if isinstance(argv, list) else None,
        shell=str(shell) if shell else None,
        cwd=str(raw.get("cwd") or ""),
        env=env if isinstance(env, Mapping) else None,
    )


def fingerprint_from_shell_args(args: Mapping[str, Any] | None) -> str:
    raw = dict(args or {})
    command = str(raw.get("command") or raw.get("shell") or "").strip()
    return normalize_execution_fingerprint(
        shell=command or None,
        cwd=str(raw.get("cwd") or ""),
        env=raw.get("env") if isinstance(raw.get("env"), Mapping) else None,
    )


@dataclass(frozen=True)
class ApprovalRecord:
    request_id: str
    tool_call_id: str
    session_id: str
    workspace_id: str
    fingerprint: str
    approval_scope: str
    result: str  # approved | rejected | pending
    created_at: float
    expires_at: float
    used: bool
    block_id: str = ""

    def is_expired(self, now: float | None = None) -> bool:
        clock = time.monotonic() if now is None else now
        return clock >= float(self.expires_at)


class RequestApprovalLedger:
    """In-process ledger. Entries are never accepted from model tool args."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: dict[str, ApprovalRecord] = {}

    def grant(
        self,
        *,
        fingerprint: str,
        session_id: str,
        workspace_id: str = "",
        tool_call_id: str = "",
        block_id: str = "",
        approval_scope: str = APPROVAL_SCOPE_ONCE,
        ttl_s: float = DEFAULT_TTL_S,
        result: str = "approved",
        request_id: str | None = None,
    ) -> ApprovalRecord:
        fp = str(fingerprint or "").strip()
        if not fp:
            raise ValueError("fingerprint required")
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("session_id required")
        now = time.monotonic()
        ttl = max(0.05, float(ttl_s))
        rid = str(request_id or "").strip() or uuid.uuid4().hex
        rec = ApprovalRecord(
            request_id=rid,
            tool_call_id=str(tool_call_id or "").strip(),
            session_id=sid,
            workspace_id=str(workspace_id or "").strip(),
            fingerprint=fp,
            approval_scope=str(approval_scope or APPROVAL_SCOPE_ONCE),
            result=str(result or "approved").strip().lower() or "approved",
            created_at=now,
            expires_at=now + ttl,
            used=False,
            block_id=str(block_id or "").strip(),
        )
        with self._lock:
            self._purge_locked(now)
            self._entries[rid] = rec
        return rec

    def reject(
        self,
        *,
        fingerprint: str,
        session_id: str,
        workspace_id: str = "",
        tool_call_id: str = "",
        ttl_s: float = DEFAULT_TTL_S,
    ) -> ApprovalRecord:
        return self.grant(
            fingerprint=fingerprint,
            session_id=session_id,
            workspace_id=workspace_id,
            tool_call_id=tool_call_id,
            ttl_s=ttl_s,
            result="rejected",
        )

    def get(self, request_id: str) -> ApprovalRecord | None:
        rid = str(request_id or "").strip()
        if not rid:
            return None
        with self._lock:
            self._purge_locked(time.monotonic())
            return self._entries.get(rid)

    def take_block(self, request_id: str) -> str:
        rid = str(request_id or "").strip()
        if not rid:
            return ""
        with self._lock:
            rec = self._entries.get(rid)
            if rec is None:
                return ""
            block = rec.block_id
            if block:
                self._entries[rid] = replace(rec, block_id="")
            return block

    def consume(
        self,
        *,
        request_id: str,
        fingerprint: str,
        session_id: str,
        workspace_id: str = "",
    ) -> tuple[bool, str]:
        """One-shot consume. Fingerprint / session / expiry / used must match."""
        rid = str(request_id or "").strip()
        fp = str(fingerprint or "").strip()
        sid = str(session_id or "").strip()
        wid = str(workspace_id or "").strip()
        if not rid:
            return False, "approval reference required"
        if not fp:
            return False, "fingerprint required"
        if not sid:
            return False, "session_id required"
        now = time.monotonic()
        with self._lock:
            self._purge_locked(now)
            rec = self._entries.get(rid)
            if rec is None:
                return False, "unknown approval"
            if rec.result != "approved":
                return False, "approval not granted"
            if rec.used:
                return False, "approval already used"
            if rec.is_expired(now):
                self._entries.pop(rid, None)
                return False, "approval expired"
            if rec.session_id != sid:
                return False, "session mismatch"
            if wid and rec.workspace_id and rec.workspace_id != wid:
                return False, "workspace mismatch"
            if rec.fingerprint != fp:
                return False, "execution fingerprint mismatch"
            self._entries[rid] = replace(rec, used=True)
            return True, ""

    def cleanup_session(self, session_id: str) -> int:
        sid = str(session_id or "").strip()
        if not sid:
            return 0
        with self._lock:
            drop = [k for k, v in self._entries.items() if v.session_id == sid]
            for k in drop:
                self._entries.pop(k, None)
            return len(drop)

    def purge_expired(self) -> int:
        with self._lock:
            return self._purge_locked(time.monotonic())

    def _purge_locked(self, now: float) -> int:
        drop = [
            k
            for k, v in self._entries.items()
            if v.is_expired(now) or (v.used and v.approval_scope == APPROVAL_SCOPE_ONCE)
        ]
        # Keep used once-entries briefly so take_block can still run; drop expired always.
        drop = [k for k, v in self._entries.items() if v.is_expired(now)]
        for k in drop:
            self._entries.pop(k, None)
        return len(drop)


_DEFAULT: RequestApprovalLedger | None = None
_DEFAULT_LOCK = threading.Lock()


def default_approval_ledger() -> RequestApprovalLedger:
    global _DEFAULT
    with _DEFAULT_LOCK:
        if _DEFAULT is None:
            _DEFAULT = RequestApprovalLedger()
        return _DEFAULT


def reset_approval_ledger_for_tests() -> None:
    global _DEFAULT
    with _DEFAULT_LOCK:
        _DEFAULT = None
