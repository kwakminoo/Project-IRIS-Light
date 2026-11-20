"""대화 목록 활동 상태 — idle / working / done (Qt 없음)."""

from __future__ import annotations

from enum import Enum
from typing import Mapping


class ChatActivity(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    DONE = "done"
    FAILED = "failed"


class ChatActivityMap:
    """conversation_id → ChatActivity. IDLE은 저장하지 않음."""

    def __init__(self) -> None:
        self._by_id: dict[int, ChatActivity] = {}

    def get(self, conversation_id: int) -> ChatActivity:
        return self._by_id.get(int(conversation_id), ChatActivity.IDLE)

    def snapshot(self) -> Mapping[int, ChatActivity]:
        return dict(self._by_id)

    def mark_working(self, conversation_id: int) -> None:
        self._by_id[int(conversation_id)] = ChatActivity.WORKING

    def mark_finished(self, conversation_id: int, *, viewing: bool) -> None:
        cid = int(conversation_id)
        if self._by_id.get(cid) != ChatActivity.WORKING:
            return
        if viewing:
            self._by_id.pop(cid, None)
        else:
            self._by_id[cid] = ChatActivity.DONE

    def mark_failed(self, conversation_id: int, *, viewing: bool) -> None:
        cid = int(conversation_id)
        if viewing:
            self._by_id.pop(cid, None)
        else:
            self._by_id[cid] = ChatActivity.FAILED

    def clear_done(self, conversation_id: int) -> None:
        cid = int(conversation_id)
        if self._by_id.get(cid) in (ChatActivity.DONE, ChatActivity.FAILED):
            self._by_id.pop(cid, None)
