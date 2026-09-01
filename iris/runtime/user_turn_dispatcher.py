from __future__ import annotations

from collections import deque

from PyQt6.QtCore import QObject, pyqtSignal

from .user_turn import UserTurn, UserTurnSource


class UserTurnDispatcher(QObject):
    turn_ready = pyqtSignal(object)  # UserTurn
    turn_queued = pyqtSignal(object, str)  # UserTurn, reason
    turn_dropped = pyqtSignal(object, str)  # UserTurn, reason

    def __init__(self, parent: QObject | None = None, *, max_pending: int = 8) -> None:
        super().__init__(parent)
        self._max_pending = max(1, int(max_pending))
        self._active: UserTurn | None = None
        self._pending: deque[UserTurn] = deque()

    @property
    def active_turn(self) -> UserTurn | None:
        return self._active

    def is_busy(self) -> bool:
        return self._active is not None

    def pending_count(self) -> int:
        return len(self._pending)

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
        if not body and not att:
            return None
        turn = UserTurn(
            text=body,
            source=source if isinstance(source, UserTurnSource) else UserTurnSource(str(source)),
            session_id=session_id,
            attachments=att,
        )
        if self._active is None:
            self._active = turn
            self.turn_ready.emit(turn)
            return turn
        self._enqueue(turn, enqueue_front=enqueue_front)
        return turn

    def finish_active_turn(self, turn_id: str | None = None) -> UserTurn | None:
        active = self._active
        if active is None:
            return None
        if turn_id and active.id != turn_id:
            return None
        finished = active
        self._active = None
        self._dispatch_next()
        return finished

    def clear_pending(self) -> list[UserTurn]:
        dropped = list(self._pending)
        self._pending.clear()
        return dropped

    def _enqueue(self, turn: UserTurn, *, enqueue_front: bool) -> None:
        if len(self._pending) >= self._max_pending:
            dropped = self._pending.popleft()
            self.turn_dropped.emit(dropped, "queue_overflow")
        if enqueue_front:
            self._pending.appendleft(turn)
        else:
            self._pending.append(turn)
        self.turn_queued.emit(turn, "busy")

    def _dispatch_next(self) -> None:
        if self._active is not None or not self._pending:
            return
        self._active = self._pending.popleft()
        self.turn_ready.emit(self._active)
