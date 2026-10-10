"""대화 id마다 두는 채팅 실행 슬롯.

창에 워커를 하나 두지 않는다. MainWindow 생성자가 ChatRunMap을 만든다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from iris.runtime.chat_turn_gate import ChatTurnGate

MAX_CONCURRENT = 2


@dataclass
class ChatRunSlot:
    conversation_id: int
    gate: ChatTurnGate = field(default_factory=ChatTurnGate)
    worker: object | None = None
    followthrough_count: int = 0
    followthrough_goal: str = ""
    followthrough_gen: int = 0
    followthrough_token: int = 0
    tool_ok_count: int = 0
    sending_followthrough: bool = False
    turn_is_followthrough: bool = False
    pending_partial: str = ""
    away_reply: str = ""
    wiki_turn_moved: bool = False
    wiki_turn_moved_folder: bool = False
    wiki_list_truncated: bool = False


class ChatRunMap:
    def __init__(self) -> None:
        self._slots: dict[int, ChatRunSlot] = {}

    def slot(self, conversation_id: int) -> ChatRunSlot:
        cid = int(conversation_id)
        found = self._slots.get(cid)
        if found is None:
            found = ChatRunSlot(conversation_id=cid)
            self._slots[cid] = found
        return found

    def owning(self, turn_id: str) -> ChatRunSlot | None:
        if not turn_id:
            return None
        for item in self._slots.values():
            if item.gate.is_current(turn_id):
                return item
        return None

    def all_slots(self) -> list[ChatRunSlot]:
        return list(self._slots.values())

    def running_count(self) -> int:
        return sum(1 for item in self._slots.values() if item.gate.busy)


class SlotAttr:
    """MainWindow 필드 읽기/쓰기를 지금 슬롯으로 보낸다."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __get__(self, obj: object, objtype: type | None = None) -> object:
        if obj is None:
            return self
        return getattr(obj._slot_now(), self.name)  # type: ignore[attr-defined]

    def __set__(self, obj: object, value: object) -> None:
        setattr(obj._slot_now(), self.name, value)  # type: ignore[attr-defined]
