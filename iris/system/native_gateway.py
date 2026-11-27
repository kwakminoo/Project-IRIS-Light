"""Authenticated local Agent API backed by the product Engine."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from sqlite3 import Error as StorageError
from threading import Condition, Thread, Timer
from time import monotonic, time
from typing import TYPE_CHECKING, Callable, Iterator
from uuid import uuid4

from iris.engine import (
    CancelToken, ChatTranscript, ContentDelta, StatelessTurn, TurnCancelled,
    TurnFailed, TurnFinished, shared_engine,
)
from iris.infrastructure.agent_tool_registry import speak_invoke_agent_tool
from iris.infrastructure.iris_agent_client import IrisAgentInferenceTarget
from iris.infrastructure.speak_capability import GATEWAY_SPEAK_ACTIONS
from iris.storage.gateway import GatewayStore, TERMINAL_RUN_STATES
from iris.system.execution_context import ExecutionContext

if TYPE_CHECKING:
    from iris.system.control_surface import ActionSpec

_PREFIX = "/v1/agent"
_MAX_ACTIVE = 4
_MAX_RUNS = 64
_MAX_MESSAGE = 8000
_MAX_CONTEXT = 64000
_MAX_EVENTS = 256
_RUN_TIMEOUT_SEC = 300
_LOCAL_PRINCIPAL = "iris.local_gateway"
_DEFAULT_TOKEN_SCOPES = frozenset({"read", "run", "cancel"})
_TOKEN_SCOPES = _DEFAULT_TOKEN_SCOPES | {"mcp"}
_APPROVAL_TTL_SEC = 90


@dataclass
class _Approval:
    identity: str
    summary: str
    preview: str
    deadline: float
    expires_at: float
    decision: str = ""


@dataclass
class _Run:
    run_id: str
    session_id: str
    conversation_id: int
    principal: str
    allow_mcp: bool = False
    cancel: CancelToken = field(default_factory=CancelToken)
    status: str = "running"
    events: deque[dict] = field(default_factory=lambda: deque(maxlen=_MAX_EVENTS))
    thread: Thread | None = None
    approval: _Approval | None = None

    def describe(self) -> dict:
        return {"run_id": self.run_id, "session_id": self.session_id, "status": self.status}


class NativeGateway:
    def __init__(
        self, resolve_target: Callable[[], IrisAgentInferenceTarget], *, db_path: Path | None = None,
        allow_control_token: bool = True,
    ) -> None:
        self._resolve_target = resolve_target
        self._changed = Condition()
        self._runs: dict[str, _Run] = {}
        self._store = GatewayStore(db_path, max_events=_MAX_EVENTS)
        self._allow_control_token = allow_control_token
        self._closed = False

    def authorize(self, authorization: str, *, control: bool, scope: str) -> tuple[int, str]:
        if control and self._allow_control_token and scope in _DEFAULT_TOKEN_SCOPES:
            return 200, _LOCAL_PRINCIPAL
        if not authorization.startswith("Bearer ") or len(authorization) > 256:
            return 401, ""
        with self._changed:
            if self._closed:
                return 503, ""
            identity = self._store.authenticate(authorization[7:])
        if identity is None:
            return 401, ""
        principal, granted = identity
        return (200, principal) if scope in granted else (403, "")

    def manage_token(self, path: str, payload: dict) -> tuple[int, dict]:
        parts = path.removeprefix(f"{_PREFIX}/tokens").split("/")
        token_id, action = (parts[1], parts[2]) if len(parts) == 3 else ("", "")
        if parts != [""] and (not token_id or action not in {"rotate", "revoke"}):
            return 404, {"error": "not found"}
        with self._changed:
            if self._closed:
                return 503, {"error": "gateway is shutting down"}
            if action == "revoke":
                if payload:
                    return 400, {"error": "expected an empty request"}
                return (200, {"revoked": True}) if self._store.revoke_token(token_id) else (404, {"error": "not found"})
            ttl = payload.get("ttl_seconds", 86400)
            scopes = payload.get("scopes", sorted(_DEFAULT_TOKEN_SCOPES))
            allowed_fields = {"ttl_seconds"} if action == "rotate" else {"ttl_seconds", "scopes"}
            if (payload.keys() - allowed_fields or type(ttl) is not int or not 1 <= ttl <= 30 * 86400
                    or not isinstance(scopes, list) or not scopes
                    or any(not isinstance(value, str) or value not in _TOKEN_SCOPES for value in scopes)):
                return 400, {"error": "invalid token scope or expiration"}
            result = self._store.issue_token(ttl, sorted(set(scopes)), rotate=token_id)
            return (200 if token_id else 201, result) if result is not None else (404, {"error": "not found"})

    @staticmethod
    def approval_run_id(path: str) -> str:
        parts = path.split("/")
        return parts[4] if len(parts) == 6 and parts[1:4] == ["v1", "agent", "runs"] and parts[5] == "approval" else ""

    def approval(self, run_id: str, payload: dict | None = None) -> tuple[int, dict]:
        with self._changed:
            run = self._runs.get(run_id)
            entry = run.approval if run is not None else None
            if (self._closed or entry is None or entry.decision or run.cancel.cancelled()
                    or monotonic() >= entry.deadline):
                return 404, {"error": "no pending approval"}
            if payload is None:
                return 200, {"approval_id": entry.identity, "summary": entry.summary,
                             "arguments_preview": entry.preview, "expires_at": entry.expires_at}
            decision = payload.get("decision")
            if (payload.keys() != {"approval_id", "decision"} or payload["approval_id"] != entry.identity
                    or decision not in ("approve", "deny")):
                return 400, {"error": "matching approval_id and decision required"}
            entry.decision = "approved" if decision == "approve" else "denied"
            self._changed.notify_all()
            return 200, {"status": entry.decision}

    def _approve_mcp(self, run: _Run, spec: ActionSpec, preview: dict) -> bool:
        with self._changed:
            if self._closed or run.cancel.cancelled() or run.approval is not None:
                return False
            entry = _Approval(uuid4().hex, spec.summary, str(preview.get("text", "")),
                              monotonic() + _APPROVAL_TTL_SEC, time() + _APPROVAL_TTL_SEC)
            run.approval = entry
            try:
                self._publish(run, {"type": "approval_required", "approval_id": entry.identity,
                                    "summary": entry.summary, "expires_at": entry.expires_at})
                while not entry.decision and not run.cancel.cancelled() and monotonic() < entry.deadline:
                    self._changed.wait(timeout=min(0.25, max(0, entry.deadline - monotonic())))
                status = "cancelled" if run.cancel.cancelled() else entry.decision or "expired"
                if run.status == "running":
                    self._publish(run, {"type": "approval_resolved", "approval_id": entry.identity, "status": status})
                return status == "approved"
            finally:
                run.approval = None

    def health(self) -> tuple[int, dict]:
        try:
            self._resolve_target()
        except (OSError, ValueError):
            return 503, {"ready": False, "error": "configured local model unavailable"}
        with self._changed:
            return (503, {"ready": False}) if self._closed else (200, {"ready": True})

    def get(self, path: str, *, principal: str = _LOCAL_PRINCIPAL) -> tuple[int, dict]:
        with self._changed:
            if self._closed:
                return 503, {"error": "gateway is shutting down"}
            if path == f"{_PREFIX}/capabilities":
                return 200, {
                    "sessions": "durable", "session_search": True, "events": "ndjson", "cancel": True,
                    "tools": sorted(GATEWAY_SPEAK_ACTIONS), "max_active_runs": _MAX_ACTIVE,
                }
            parent, _, identity = path.rpartition("/")
            if parent == f"{_PREFIX}/runs":
                run = self._store.run(identity, principal)
                if run is not None:
                    return 200, run
            if parent == f"{_PREFIX}/sessions":
                history = self._store.history(identity, principal)
                if history is not None:
                    return 200, {"session_id": identity, "messages": history}
        return 404, {"error": "not found"}

    def search_sessions(self, query: str, *, principal: str = _LOCAL_PRINCIPAL) -> tuple[int, dict]:
        query = query.strip()
        if not query or len(query) > 200:
            return 400, {"error": "q must contain 1–200 characters"}
        with self._changed:
            if self._closed:
                return 503, {"error": "gateway is shutting down"}
            return 200, {"hits": self._store.search(query, principal)}

    def post(self, path: str, payload: dict, *, principal: str = _LOCAL_PRINCIPAL,
             allow_mcp: bool = False) -> tuple[int, dict]:
        if path == f"{_PREFIX}/runs":
            return self._start(payload, principal, allow_mcp=allow_mcp)
        parent, _, operation = path.rpartition("/")
        if operation == "cancel" and parent.rpartition("/")[0] == f"{_PREFIX}/runs":
            run_id = parent.rpartition("/")[-1]
            with self._changed:
                if self._closed:
                    return 503, {"error": "gateway is shutting down"}
                run = self._runs.get(run_id)
                if run is not None and run.principal == principal:
                    if run.status != "running":
                        return 200, run.describe()
                    self._store.cancel(run_id)
                    run.cancel.cancel()
                    self._changed.notify_all()
                    return 202, {**run.describe(), "status": "cancelling"}
                stored = self._store.run(run_id, principal)
                if stored is not None:
                    return 200, stored
        return 404, {"error": "not found"}

    def _start(self, payload: dict, principal: str, *, allow_mcp: bool) -> tuple[int, dict]:
        message = payload.get("message")
        session_id = payload.get("session_id", "")
        if (
            payload.keys() - {"message", "session_id"}
            or not isinstance(message, str) or not message.strip() or len(message) > _MAX_MESSAGE
            or not isinstance(session_id, str)
        ):
            return 400, {"error": "message and optional session_id required"}
        try:
            target = self._resolve_target()
        except (OSError, ValueError):
            return 503, {"error": "configured local model unavailable"}
        with self._changed:
            if self._closed:
                return 503, {"error": "gateway is shutting down"}
            history = self._store.history(session_id, principal) if session_id else []
            if history is None:
                return 404, {"error": "session not found"}
            active = [run for run in self._runs.values() if run.status == "running"]
            if session_id and any(run.session_id == session_id for run in active):
                return 409, {"error": "session already has an active run"}
            if len(active) >= _MAX_ACTIVE:
                return 429, {"error": "gateway capacity reached"}
            if sum(len(row["content"]) for row in history) + len(message) > _MAX_CONTEXT:
                return 409, {"error": "session context limit reached"}
            user = {"role": "user", "content": message}
            transcript = ChatTranscript.parse([*history, user])
            if len(self._runs) >= _MAX_RUNS:
                oldest = next(key for key, run in self._runs.items() if run.status != "running")
                del self._runs[oldest]
            run_id, sid = uuid4().hex, session_id or uuid4().hex
            try:
                cid = self._store.start(run_id, sid, principal, new_session=not session_id)
            except StorageError:
                return 503, {"error": "gateway storage unavailable"}
            run = _Run(run_id, sid, cid, principal, allow_mcp)
            self._runs[run.run_id] = run
            run.thread = Thread(target=self._execute, args=(run, transcript, target, user), daemon=True)
            try:
                run.thread.start()
            except RuntimeError:
                self._publish(run, {"type": "failed", "error": "could not start agent run"})
                return 503, {"error": "could not start agent run"}
            return 202, run.describe()

    def _execute(self, run: _Run, transcript: ChatTranscript, target: IrisAgentInferenceTarget, user: dict) -> None:
        context = ExecutionContext(
            session_id=run.session_id, conversation_id=str(run.conversation_id),
            turn_id=run.run_id, run_id=run.run_id, source="gateway", principal=run.principal,
            permission_scope="gateway.mcp" if run.allow_mcp else "session",
        )
        turn = StatelessTurn(transcript, target, run.cancel, speak_surface="gateway", execution_context=context)
        terminal = {"type": "failed", "error": "agent run did not finish"}
        engine = None
        timeout = Timer(_RUN_TIMEOUT_SEC, run.cancel.cancel)
        timeout.daemon = True
        timeout.start()
        try:
            engine = shared_engine().fork()
            engine.bind_tool_handler(speak_invoke_agent_tool)
            if run.allow_mcp:
                engine.bind_mcp_approval(lambda spec, preview: self._approve_mcp(run, spec, preview))
            for event in engine.run_turn(turn):
                if isinstance(event, ContentDelta):
                    with self._changed:
                        if run.status == "running":
                            self._publish(run, {"type": "delta", "text": event.text})
                elif isinstance(event, TurnFinished):
                    terminal = {"type": "finished", "text": event.text}
                elif isinstance(event, TurnCancelled):
                    terminal = {"type": "cancelled"}
                elif isinstance(event, TurnFailed):
                    terminal = {"type": "failed", "error": event.error.user_message, "code": event.error.code.value}
        except Exception:
            terminal = {"type": "failed", "error": "agent runtime unavailable"}
        finally:
            timeout.cancel()
            try:
                if engine is not None:
                    engine.shutdown()
            finally:
                with self._changed:
                    if run.status == "running":
                        if run.cancel.cancelled():
                            terminal = {"type": "cancelled"}
                        finished_turn = ((run.conversation_id, user["content"], terminal["text"])
                                         if terminal["type"] == "finished" else None)
                        self._publish(run, terminal, finished_turn=finished_turn)

    def _publish(self, run: _Run, details: dict, *, finished_turn: tuple[int, str, str] | None = None) -> None:
        seq = run.events[-1]["seq"] + 1 if run.events else 1
        run.events.append(self._store.publish(run.run_id, seq, details, finished_turn=finished_turn))
        if details["type"] in TERMINAL_RUN_STATES:
            run.status = details["type"]
        self._changed.notify_all()

    def events(self, run_id: str, after: int, *, principal: str = _LOCAL_PRINCIPAL) -> Iterator[dict] | None:
        with self._changed:
            if self._closed:
                return None
            run = self._runs.get(run_id)
            if run is None:
                if self._store.run(run_id, principal) is None:
                    return None
                rows = self._store.events(run_id, after)
                if rows and rows[0]["seq"] > after + 1:
                    rows.insert(0, {"type": "gap", "next_seq": rows[0]["seq"]})
                return iter(rows)
            if run.principal != principal:
                return None
        return self._events(run, after)

    def _events(self, run: _Run, after: int) -> Iterator[dict]:
        while True:
            with self._changed:
                self._changed.wait_for(
                    lambda: run.status != "running" or (run.events and run.events[-1]["seq"] > after),
                    timeout=10,
                )
                rows = [row for row in run.events if row["seq"] > after]
                done = run.status != "running"
            if rows and rows[0]["seq"] > after + 1:
                yield {"type": "gap", "next_seq": rows[0]["seq"]}
            for row in rows:
                after = row["seq"]
                yield row
            if done:
                return
            if not rows:
                yield {"type": "heartbeat"}

    def close(self) -> None:
        with self._changed:
            if self._closed:
                return
            self._closed = True
            active = [run for run in self._runs.values() if run.status == "running"]
            for run in active:
                self._store.cancel(run.run_id)
                run.cancel.cancel()
        deadline = monotonic() + 3
        for run in active:
            if run.thread is not None:
                run.thread.join(timeout=max(0, deadline - monotonic()))
        with self._changed:
            for run in active:
                if run.status == "running":
                    self._publish(run, {"type": "interrupted", "error": "Gateway shut down during the run"})
            self._store.close()
