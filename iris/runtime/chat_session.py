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
        from .attachment_store import AttachmentStore
        self.attachments = AttachmentStore()

    def record(self, role: str, content: str, *, model_content: str = "") -> str | None:
        """메모리에 먼저 넣고 DB에 쓴다. DB에 못 쓰면 메모리에서도 빼서 다음 턴에 안 남긴다."""
        self.history.append({"role": role, "content": content, **({"model_content": model_content} if model_content else {})})
        try:
            append_message(self.db, self.conversation_id, role, content, model_content=model_content)
        except Exception as exc:  # noqa: BLE001
            if self.history and self.history[-1].get("role") == role and self.history[-1].get("content") == content:
                self.history.pop()
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
        if int(conversation_id) != self.conversation_id:
            from .attachment_store import AttachmentStore
            self.attachments = AttachmentStore()
        self.conversation_id = int(conversation_id)
        set_active_conversation_id(self.db, self.conversation_id)
        self.history = history_dicts(self.db, self.conversation_id)

    def clear_messages(self) -> None:
        from .attachment_store import AttachmentStore
        self.attachments = AttachmentStore()
        clear_conversation_messages(self.db, self.conversation_id)
        self.history = []

    def start_new(self, project_id: int = 0) -> int:
        from .attachment_store import AttachmentStore
        self.attachments = AttachmentStore()
        return start_new_conversation(self.db, project_id=int(project_id or 0))

    def list_projects(self):
        from iris.storage.chat_projects import list_projects

        return list_projects(self.db)

    def open_launch_chat(self) -> int:
        """프로그램·창을 열 때. 이전 대화는 두고 빈 채팅을 연다."""
        cid = start_new_conversation(self.db)
        self.activate(cid)
        return cid

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


def workspace_needs_fresh_chat(
    *,
    prev_active: bool,
    prev_root: str,
    mode: str,
    root: str,
) -> bool:
    """IDE를 처음 열거나 workspace가 바뀔 때 새 채팅."""
    root_s = (root or "").strip()
    prev = (prev_root or "").strip()
    if mode == "workspace" and root_s and root_s != prev:
        return True
    if mode in ("welcome", "hero") and not prev_active:
        return True
    return False


def should_open_fresh_work_chat(
    *,
    ide_id: str,
    prev_active: bool,
    prev_root: str,
    mode: str,
    root: str,
) -> bool:
    """IRIS IDE는 기본 화면에서 쓰던 채팅을 유지한다."""
    if (ide_id or "").strip().lower() == "iris_ide":
        return False
    return workspace_needs_fresh_chat(
        prev_active=prev_active,
        prev_root=prev_root,
        mode=mode,
        root=root,
    )
