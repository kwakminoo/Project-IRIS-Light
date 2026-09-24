"""현재 채팅 세션의 저장 상태.

MainWindow는 이 객체의 결과를 패널에 그린다. 위젯은 여기 없다.
"""

from __future__ import annotations

from iris.storage.conversations import (
    append_message,
    clear_conversation_messages,
    delete_conversation,
    ensure_active_conversation,
    get_conversation,
    history_dicts,
    list_conversations,
    pop_last_user_message,
    rename_conversation,
    set_active_conversation_id,
    start_new_conversation,
)
from iris.storage.database import Database


class ChatSession:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.conversation_id = ensure_active_conversation(db)
        self.history: list[dict[str, str]] = history_dicts(db, self.conversation_id)

    def record(self, role: str, content: str) -> str | None:
        """메모리에 먼저 넣고 DB에 쓴다. DB 실패 시 메모리는 유지하고 오류 문자열을 돌려준다."""
        self.history.append({"role": role, "content": content})
        try:
            append_message(self.db, self.conversation_id, role, content)
        except Exception as exc:  # noqa: BLE001
            return str(exc)
        return None

    def drop_last_user(self) -> None:
        if self.history and self.history[-1].get("role") == "user":
            self.history.pop()
        try:
            pop_last_user_message(self.db, self.conversation_id)
        except Exception:
            pass

    def list_items(self):
        return list_conversations(self.db, include_empty_id=self.conversation_id)

    def activate(self, conversation_id: int) -> None:
        self.conversation_id = int(conversation_id)
        set_active_conversation_id(self.db, self.conversation_id)
        self.history = history_dicts(self.db, self.conversation_id)

    def clear_messages(self) -> None:
        clear_conversation_messages(self.db, self.conversation_id)
        self.history = []

    def start_new(self) -> int:
        return start_new_conversation(self.db)

    def rename(self, conversation_id: int, title: str) -> str | None:
        try:
            rename_conversation(self.db, int(conversation_id), title)
        except Exception as exc:  # noqa: BLE001
            return str(exc)
        return None

    def title_of(self, conversation_id: int) -> str:
        conv = get_conversation(self.db, int(conversation_id))
        return (conv.title if conv else "").strip()

    def delete(self, conversation_id: int) -> None:
        delete_conversation(self.db, int(conversation_id))

    def ensure_active(self) -> int:
        return ensure_active_conversation(self.db)
