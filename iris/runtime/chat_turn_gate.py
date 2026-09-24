"""진행 중 채팅 턴의 식별·점유·결과 폐기.

워커 시작과 위젯 갱신은 호출 측(UI 스레드)이 한다.
"""

from __future__ import annotations


class ChatTurnGate:
    def __init__(self) -> None:
        self.active_id = ""
        self.busy = False
        self.ignore_result = False

    def begin(self, turn_id: str) -> None:
        self.active_id = turn_id

    def is_current(self, turn_id: str) -> bool:
        return bool(turn_id) and turn_id == self.active_id

    def arm(self) -> None:
        self.busy = True
        self.ignore_result = False

    def suppress_result(self) -> None:
        self.ignore_result = True

    def consume_ignored(self) -> bool:
        if not self.ignore_result:
            return False
        self.ignore_result = False
        return True

    def finish(self, turn_id: str | None) -> str:
        """점유를 풀고, 디스패처에 넘길 턴 id를 돌려준다."""
        current_id = turn_id or self.active_id
        self.busy = False
        if current_id and current_id == self.active_id:
            self.active_id = ""
        elif not current_id and self.active_id:
            current_id = self.active_id
            self.active_id = ""
        return current_id or ""
