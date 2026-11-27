"""Authenticated local Agent API backed by the product Engine."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from threading import Condition, Thread, Timer
from time import monotonic
from typing import Callable, Iterator
from uuid import uuid4

from iris.engine import (
    CancelToken, ChatTranscript, ContentDelta, StatelessTurn, TurnCancelled,
    TurnFailed, TurnFinished, shared_engine,
)
from iris.infrastructure.agent_tool_registry import speak_invoke_agent_tool
from iris.infrastructure.iris_agent_client import IrisAgentInferenceTarget
from iris.infrastructure.speak_capability import GATEWAY_SPEAK_ACTIONS
from iris.system.execution_context import ExecutionContext

_PREFIX = "/v1/agent"
_MAX_ACTIVE = 4
_MAX_RUNS = 64
_MAX_SESSIONS = 64
_MAX_MESSAGE = 8000
_MAX_CONTEXT = 64000
_MAX_EVENTS = 256
_RUN_TIMEOUT_SEC = 300


@dataclass
class _Run:
    run_id: str
    session_id: str
    cancel: CancelToken = field(default_factory=CancelToken)
    status: str = "running"
    events: deque[dict] = field(default_factory=lambda: deque(maxlen=_MAX_EVENTS))
    thread: Thread | None = None

    def describe(self) -> dict:
        return {"run_id": self.run_id, "session_id": self.session_id, "status": self.status}


class NativeGateway:
    def __init__(self, resolve_target: Callable[[], IrisAgentInferenceTarget]) -> None:
        self._resolve_target = resolve_target
        self._changed = Condition()
        self._runs: dict[str, _Run] = {}
        # ponytail: local API sessions are bounded and process-local until the
        # IRIS conversation schema supports durable external ownership.
        self._sessions: dict[str, list[dict[str, str]]] = {}
        self._closed = False

    def health(self) -> tuple[int, dict]:
        try:
            self._resolve_target()
        except (OSError, ValueError):
            return 503, {"ready": False, "error": "configured local model unavailable"}
        with self._changed:
            return (503, {"ready": False}) if self._closed else (200, {"ready": True})

    def get(self, path: str) -> tuple[int, dict]:
        with self._changed:
            if path == f"{_PREFIX}/capabilities":
                return 200, {
                    "sessions": "process-local", "events": "ndjson", "cancel": True,
                    "tools": sorted(GATEWAY_SPEAK_ACTIONS), "max_active_runs": _MAX_ACTIVE,
                }
            parent, _, identity = path.rpartition("/")
            if parent == f"{_PREFIX}/runs" and identity in self._runs:
                return 200, self._runs[identity].describe()
            if parent == f"{_PREFIX}/sessions" and identity in self._sessions:
                return 200, {"session_id": identity, "messages": list(self._sessions[identity])}
        return 404, {"error": "not found"}

    def post(self, path: str, payload: dict) -> tuple[int, dict]:
        if path == f"{_PREFIX}/runs":
            return self._start(payload)
        parent, _, operation = path.rpartition("/")
        if operation == "cancel" and parent.rpartition("/")[0] == f"{_PREFIX}/runs":
            run_id = parent.rpartition("/")[-1]
            with self._changed:
                run = self._runs.get(run_id)
                if run is not None:
                    if run.status != "running":
                        return 200, run.describe()
                    run.cancel.cancel()
                    return 202, {**run.describe(), "status": "cancelling"}
        return 404, {"error": "not found"}

    def _start(self, payload: dict) -> tuple[int, dict]:
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
            if session_id and session_id not in self._sessions:
                return 404, {"error": "session not found"}
            active = [run for run in self._runs.values() if run.status == "running"]
            if session_id and any(run.session_id == session_id for run in active):
                return 409, {"error": "session already has an active run"}
            if len(active) >= _MAX_ACTIVE or (not session_id and len(self._sessions) >= _MAX_SESSIONS):
                return 429, {"error": "gateway capacity reached"}
            history = self._sessions.get(session_id, [])
            if sum(len(row["content"]) for row in history) + len(message) > _MAX_CONTEXT:
                return 409, {"error": "session context limit reached"}
            user = {"role": "user", "content": message}
            transcript = ChatTranscript.parse([*history, user])
            if len(self._runs) >= _MAX_RUNS:
                oldest = next(key for key, run in self._runs.items() if run.status != "running")
                del self._runs[oldest]
            new_session = not session_id
            run = _Run(uuid4().hex, session_id or uuid4().hex)
            self._runs[run.run_id] = run
            self._sessions.setdefault(run.session_id, history)
            run.thread = Thread(target=self._execute, args=(run, transcript, target, user), daemon=True)
            try:
                run.thread.start()
            except RuntimeError:
                del self._runs[run.run_id]
                if new_session:
                    del self._sessions[run.session_id]
                return 503, {"error": "could not start agent run"}
            return 202, run.describe()

    def _execute(self, run: _Run, transcript: ChatTranscript, target: IrisAgentInferenceTarget, user: dict) -> None:
        context = ExecutionContext(
            session_id=run.session_id, conversation_id=run.session_id,
            turn_id=run.run_id, run_id=run.run_id, source="gateway", principal="iris.local_gateway",
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
            for event in engine.run_turn(turn):
                if isinstance(event, ContentDelta):
                    with self._changed:
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
                    if run.cancel.cancelled():
                        terminal = {"type": "cancelled"}
                    if terminal["type"] == "finished":
                        self._sessions[run.session_id].extend((user, {"role": "assistant", "content": terminal["text"]}))
                    run.status = terminal["type"]
                    self._publish(run, terminal)

    def _publish(self, run: _Run, details: dict) -> None:
        seq = run.events[-1]["seq"] + 1 if run.events else 1
        run.events.append({"seq": seq, "run_id": run.run_id, **details})
        self._changed.notify_all()

    def events(self, run_id: str, after: int) -> Iterator[dict] | None:
        with self._changed:
            run = self._runs.get(run_id)
        if run is None:
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
            self._closed = True
            active = [run for run in self._runs.values() if run.status == "running"]
            for run in active:
                run.cancel.cancel()
        deadline = monotonic() + 3
        for run in active:
            if run.thread is not None:
                run.thread.join(timeout=max(0, deadline - monotonic()))
