from __future__ import annotations

from collections import deque

from PyQt6.QtCore import QObject, pyqtSignal

from .chat_run_slot import MAX_CONCURRENT
from .user_turn import UserTurn, UserTurnSource


class UserTurnDispatcher(QObject):
    """텍스트·음성 입력을 대화 id별 턴으로 큐잉한다.

    추론과 HTTP는 하지 않는다. UI는 ``turn_ready``를 구독해 실행한다.
    같은 대화는 한 줄로 기다리고, 서로 다른 대화는 ``max_concurrent``까지 동시에 나간다.
    새 에이전트 도구는 여기가 아니라 Hermes 스킬/MCP에 둔다.
    """

    turn_ready = pyqtSignal(object)  # UserTurn
    turn_queued = pyqtSignal(object, str)  # UserTurn, reason
    turn_dropped = pyqtSignal(object, str)  # UserTurn, reason

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        max_pending: int = 8,
        max_concurrent: int = MAX_CONCURRENT,
    ) -> None:
        super().__init__(parent)
        self._max_pending = max(1, int(max_pending))
        self._max_concurrent = max(1, int(max_concurrent))
        self._active: dict[int | None, UserTurn] = {}
        self._pending: dict[int | None, deque[UserTurn]] = {}
        self._wait_order: deque[int | None] = deque()

    @property
    def active_turn(self) -> UserTurn | None:
        if len(self._active) == 1:
            return next(iter(self._active.values()))
        return None

    def turn_by_id(self, turn_id: str) -> UserTurn | None:
        for turn in self._active.values():
            if turn.id == turn_id:
                return turn
        return None

    def is_busy(self) -> bool:
        return bool(self._active)

    def is_session_busy(self, session_id: int | None) -> bool:
        return session_id in self._active

    def pending_count(self) -> int:
        return sum(len(queue) for queue in self._pending.values())

    def pending_count_for(self, session_id: int | None) -> int:
        return len(self._pending.get(session_id, ()))

    def submit(
        self,
        *,
        text: str,
        source: UserTurnSource | str,
        session_id: int | None = None,
        attachments: tuple[str, ...] | list[str] = (),
        enqueue_front: bool = False,
    ) -> UserTurn | None:
        body = (text or "").strip()
        att = tuple(str(p).strip() for p in attachments if str(p).strip())
        if att:
            from iris.runtime.attachment_context import trace
            trace("user_turn", paths=list(att), text_chars=len(body), source=str(source))
        if not body and not att:
            return None
        turn = UserTurn(
            text=body,
            source=source if isinstance(source, UserTurnSource) else UserTurnSource(str(source)),
            session_id=session_id,
            attachments=att,
        )
        if session_id not in self._active and self._running() < self._max_concurrent:
            self._active[session_id] = turn
            self.turn_ready.emit(turn)
            return turn
        self._enqueue(session_id, turn, enqueue_front=enqueue_front)
        return turn

    def finish_active_turn(self, turn_id: str | None = None) -> UserTurn | None:
        missing = object()
        sid: int | None | object = missing
        if turn_id:
            for key, active in self._active.items():
                if active.id == turn_id:
                    sid = key
                    break
            if sid is missing:
                return None
        elif len(self._active) == 1:
            sid = next(iter(self._active))
        else:
            return None
        finished = self._active.pop(sid)
        self._promote(sid)
        return finished

    def clear_pending(self) -> list[UserTurn]:
        dropped: list[UserTurn] = []
        for queue in self._pending.values():
            dropped.extend(queue)
            queue.clear()
        self._wait_order.clear()
        return dropped

    def _running(self) -> int:
        return len(self._active)

    def _enqueue(self, sid: int | None, turn: UserTurn, *, enqueue_front: bool) -> None:
        queue = self._pending.setdefault(sid, deque())
        if len(queue) >= self._max_pending:
            dropped = queue.popleft()
            self.turn_dropped.emit(dropped, "queue_overflow")
        if enqueue_front:
            queue.appendleft(turn)
        else:
            queue.append(turn)
        if sid not in self._active and sid not in self._wait_order:
            self._wait_order.append(sid)
        reason = "busy" if sid in self._active else "concurrent_cap"
        self.turn_queued.emit(turn, reason)

    def _promote(self, preferred: int | None) -> None:
        self._start_queued(preferred)
        while self._running() < self._max_concurrent and self._wait_order:
            sid = self._wait_order.popleft()
            if sid == preferred or sid in self._active or not self._pending.get(sid):
                continue
            self._start_queued(sid)

    def _start_queued(self, sid: int | None) -> bool:
        if sid in self._active or self._running() >= self._max_concurrent:
            return False
        queue = self._pending.get(sid)
        if not queue:
            return False
        turn = queue.popleft()
        self._active[sid] = turn
        self.turn_ready.emit(turn)
        return True
