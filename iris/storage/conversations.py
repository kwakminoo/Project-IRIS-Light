"""로컬 채팅 세션 — SQLite conversations + messages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from iris.storage.database import Database

ACTIVE_CHAT_PREF_KEY = "active_chat_conversation_id"
DEFAULT_TITLE = "새 채팅"
_TITLE_LIMIT = 36
_USER_TITLE_LIMIT = 48

# ponytail: 어휘 겹침으로 주제 전환을 본다. 오탐이 늘면 LLM 제목 생성으로 교체.
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+-]*|[가-힣]{2,}")
_STOPWORDS = frozenset(
    {
        "and",
        "for",
        "the",
        "this",
        "that",
        "with",
        "from",
        "please",
        "can",
        "you",
        "how",
        "what",
        "just",
        "okay",
        "yes",
        "그리고",
        "그래서",
        "그럼",
        "아니면",
        "또는",
        "이것",
        "그것",
        "저것",
        "알려줘",
        "해줘",
        "해주세요",
        "짜줘",
        "관련",
        "대해",
        "대한",
        "뭔가",
        "어떻게",
        "무엇",
        "왜요",
    }
)
_FOLLOWUP_RE = re.compile(
    r"^(그럼|그리고|그래서|아니면|또는|또|다시|응|네|아니|"
    r"ok|okay|yes|no|thanks?|고마워|감사|더|자세히|왜요?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ChatConversation:
    id: int
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0
    title_locked: bool = False


@dataclass(frozen=True)
class ChatMessage:
    id: int
    conversation_id: int
    role: str
    content: str
    created_at: str


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def title_from_text(text: str, *, limit: int = _TITLE_LIMIT) -> str:
    body = " ".join((text or "").strip().split())
    if not body:
        return DEFAULT_TITLE
    if len(body) > limit:
        return body[: max(1, limit - 1)] + "…"
    return body


def _tokens(text: str) -> frozenset[str]:
    return frozenset(
        p.lower()
        for p in _TOKEN_RE.findall(text or "")
        if p.lower() not in _STOPWORDS and len(p) >= 2
    )


def _is_topic_line(text: str) -> bool:
    body = " ".join((text or "").split())
    if len(body) < 6:
        return False
    tokens = _tokens(body)
    if _FOLLOWUP_RE.match(body) and len(tokens) < 4:
        return False
    return len(tokens) >= 2


def topic_shifted(anchor: str, later: list[str]) -> bool:
    """later 가 anchor 와 다른 주제로 넘어갔는지."""
    if not later:
        return False
    a = _tokens(anchor)
    b = _tokens(" ".join(later))
    if len(b) < 3:
        return False
    shared = a & b
    novel = b - a
    if len(novel) < 3:
        return False
    lead = " ".join(later[0].split())
    if _FOLLOWUP_RE.match(lead) and len(novel) < 5:
        return False
    return len(novel) >= max(3, 2 * len(shared))


def _anchor_line(texts: list[str]) -> str:
    for text in texts:
        if _is_topic_line(text):
            return text
    return texts[0]


def suggest_title(messages: list[ChatMessage] | list[dict[str, str]]) -> str:
    """현재 대화 맥락의 제목 — 첫 주제 유지, 크게 바뀌면 새 주제 앵커."""
    users: list[str] = []
    for msg in messages:
        if isinstance(msg, dict):
            role, content = str(msg.get("role") or ""), str(msg.get("content") or "")
        else:
            role, content = msg.role, msg.content
        body = content.strip()
        if role == "user" and body:
            users.append(body)
    if not users:
        return DEFAULT_TITLE
    start = 0
    for i in range(1, len(users)):
        if topic_shifted(users[start], [users[i]]):
            start = i
    return title_from_text(_anchor_line(users[start:]))


def ensure_chat_schema(db: Database) -> None:
    db._execute(
        """
        CREATE TABLE IF NOT EXISTS chat_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '새 채팅',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            title_locked INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    db._execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    db._execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_conv "
        "ON chat_messages(conversation_id, id)"
    )
    cols = {
        str(row["name"])
        for row in db._execute("PRAGMA table_info(chat_conversations)").fetchall()
    }
    if "title_locked" not in cols:
        db._execute(
            "ALTER TABLE chat_conversations "
            "ADD COLUMN title_locked INTEGER NOT NULL DEFAULT 0"
        )
    db._commit()


def _conv_from_row(row) -> ChatConversation:
    try:
        locked = bool(int(row["title_locked"] or 0))
    except (KeyError, IndexError, TypeError, ValueError):
        locked = False
    return ChatConversation(
        id=int(row["id"]),
        title=str(row["title"] or DEFAULT_TITLE),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
        message_count=int(row["message_count"] or 0),
        title_locked=locked,
    )


def create_conversation(db: Database, *, title: str = DEFAULT_TITLE) -> ChatConversation:
    ensure_chat_schema(db)
    stamp = _now()
    name = (title or "").strip() or DEFAULT_TITLE
    cur = db._execute(
        """
        INSERT INTO chat_conversations(title, created_at, updated_at, title_locked)
        VALUES(?, ?, ?, 0)
        """,
        (name, stamp, stamp),
    )
    db._commit()
    cid = int(cur.lastrowid or 0)
    return ChatConversation(
        id=cid,
        title=name,
        created_at=stamp,
        updated_at=stamp,
        message_count=0,
        title_locked=False,
    )


def get_conversation(db: Database, conversation_id: int) -> ChatConversation | None:
    ensure_chat_schema(db)
    row = db._execute(
        """
        SELECT c.id, c.title, c.created_at, c.updated_at, c.title_locked,
               (SELECT COUNT(*) FROM chat_messages m WHERE m.conversation_id = c.id)
                 AS message_count
          FROM chat_conversations c
         WHERE c.id = ?
        """,
        (int(conversation_id),),
    ).fetchone()
    if row is None:
        return None
    return _conv_from_row(row)


def set_active_conversation_id(db: Database, conversation_id: int) -> None:
    db.set_preference(ACTIVE_CHAT_PREF_KEY, str(int(conversation_id)))


def active_conversation_id(db: Database) -> int | None:
    raw = (db.get_preference(ACTIVE_CHAT_PREF_KEY, "") or "").strip()
    if not raw.isdigit():
        return None
    return int(raw)


def ensure_active_conversation(db: Database) -> int:
    """저장된 활성 세션이 있으면 쓰고, 없으면 최근 세션 또는 새 세션."""
    ensure_chat_schema(db)
    current = active_conversation_id(db)
    if current is not None and get_conversation(db, current) is not None:
        return current
    row = db._execute(
        "SELECT id FROM chat_conversations ORDER BY updated_at DESC, id DESC LIMIT 1"
    ).fetchone()
    if row is not None:
        cid = int(row["id"])
        set_active_conversation_id(db, cid)
        return cid
    conv = create_conversation(db)
    set_active_conversation_id(db, conv.id)
    return conv.id


def list_conversations(
    db: Database,
    *,
    limit: int = 50,
    include_empty_id: int | None = None,
) -> list[ChatConversation]:
    ensure_chat_schema(db)
    rows = db._execute(
        """
        SELECT c.id, c.title, c.created_at, c.updated_at, c.title_locked,
               (SELECT COUNT(*) FROM chat_messages m WHERE m.conversation_id = c.id)
                 AS message_count
          FROM chat_conversations c
         ORDER BY c.updated_at DESC, c.id DESC
        """
    ).fetchall()
    out: list[ChatConversation] = []
    for row in rows:
        item = _conv_from_row(row)
        if item.message_count <= 0 and item.id != include_empty_id:
            continue
        out.append(item)
        if len(out) >= max(1, int(limit)):
            break
    return out


def list_messages(db: Database, conversation_id: int) -> list[ChatMessage]:
    ensure_chat_schema(db)
    rows = db._execute(
        """
        SELECT id, conversation_id, role, content, created_at
          FROM chat_messages
         WHERE conversation_id = ?
         ORDER BY id ASC
        """,
        (int(conversation_id),),
    ).fetchall()
    return [
        ChatMessage(
            id=int(row["id"]),
            conversation_id=int(row["conversation_id"]),
            role=str(row["role"] or ""),
            content=str(row["content"] or ""),
            created_at=str(row["created_at"] or ""),
        )
        for row in rows
    ]


def history_dicts(db: Database, conversation_id: int) -> list[dict[str, str]]:
    return [
        {"role": m.role, "content": m.content}
        for m in list_messages(db, conversation_id)
        if m.role in ("user", "assistant")
    ]


def _set_title(
    db: Database,
    conversation_id: int,
    title: str,
    *,
    locked: bool,
) -> None:
    db._execute(
        "UPDATE chat_conversations SET title = ?, title_locked = ? WHERE id = ?",
        (title, 1 if locked else 0, int(conversation_id)),
    )


def _maybe_refresh_title(db: Database, conversation_id: int) -> None:
    conv = get_conversation(db, conversation_id)
    if conv is None or conv.title_locked:
        return
    messages = list_messages(db, conversation_id)
    suggested = suggest_title(messages)
    if suggested in ("", DEFAULT_TITLE) or suggested == conv.title:
        return
    if conv.title in ("", DEFAULT_TITLE):
        _set_title(db, conversation_id, suggested, locked=False)
        return
    users = [
        m.content.strip()
        for m in messages
        if m.role == "user" and m.content.strip()
    ]
    if users and topic_shifted(conv.title, [users[-1]]):
        _set_title(db, conversation_id, suggested, locked=False)


def rename_conversation(db: Database, conversation_id: int, title: str) -> str:
    """사용자가 직접 붙인 제목 — 이후 자동 갱신하지 않는다."""
    ensure_chat_schema(db)
    conv = get_conversation(db, conversation_id)
    name = " ".join((title or "").strip().split())
    if not name:
        return conv.title if conv else DEFAULT_TITLE
    if len(name) > _USER_TITLE_LIMIT:
        name = name[:_USER_TITLE_LIMIT]
    _set_title(db, conversation_id, name, locked=True)
    db._commit()
    return name


def append_message(db: Database, conversation_id: int, role: str, content: str) -> int:
    ensure_chat_schema(db)
    stamp = _now()
    cur = db._execute(
        """
        INSERT INTO chat_messages(conversation_id, role, content, created_at)
        VALUES(?, ?, ?, ?)
        """,
        (int(conversation_id), str(role or ""), str(content or ""), stamp),
    )
    db._execute(
        "UPDATE chat_conversations SET updated_at = ? WHERE id = ?",
        (stamp, int(conversation_id)),
    )
    if str(role) == "user" and (content or "").strip():
        _maybe_refresh_title(db, conversation_id)
    db._commit()
    return int(cur.lastrowid or 0)


def pop_last_user_message(db: Database, conversation_id: int) -> bool:
    ensure_chat_schema(db)
    row = db._execute(
        """
        SELECT id, role FROM chat_messages
         WHERE conversation_id = ?
         ORDER BY id DESC LIMIT 1
        """,
        (int(conversation_id),),
    ).fetchone()
    if row is None or str(row["role"]) != "user":
        return False
    db._execute("DELETE FROM chat_messages WHERE id = ?", (int(row["id"]),))
    db._execute(
        "UPDATE chat_conversations SET updated_at = ? WHERE id = ?",
        (_now(), int(conversation_id)),
    )
    db._commit()
    return True


def clear_conversation_messages(db: Database, conversation_id: int) -> None:
    ensure_chat_schema(db)
    db._execute(
        "DELETE FROM chat_messages WHERE conversation_id = ?",
        (int(conversation_id),),
    )
    db._execute(
        "UPDATE chat_conversations SET title = ?, title_locked = 0, updated_at = ? WHERE id = ?",
        (DEFAULT_TITLE, _now(), int(conversation_id)),
    )
    db._commit()


def delete_conversation(db: Database, conversation_id: int) -> None:
    ensure_chat_schema(db)
    db._execute(
        "DELETE FROM chat_messages WHERE conversation_id = ?",
        (int(conversation_id),),
    )
    db._execute(
        "DELETE FROM chat_conversations WHERE id = ?",
        (int(conversation_id),),
    )
    db._commit()


def start_new_conversation(db: Database) -> int:
    """현재 빈 세션이 있으면 재사용, 아니면 새로 만든다."""
    ensure_chat_schema(db)
    current = active_conversation_id(db)
    if current is not None:
        conv = get_conversation(db, current)
        if conv is not None and conv.message_count <= 0:
            return current
    conv = create_conversation(db)
    set_active_conversation_id(db, conv.id)
    return conv.id
