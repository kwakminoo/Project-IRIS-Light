"""로컬 채팅 세션 — SQLite conversations + messages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from iris.storage.database import Database

ACTIVE_CHAT_PREF_KEY = "active_chat_conversation_id"
CHAT_TITLE_BASIS_KEY = "chat_title_basis"
TITLE_BASIS_LAST = "last"
TITLE_BASIS_FIRST = "first"
DEFAULT_TITLE = "새 채팅"
# 답변 도중 다른 대화로 옮기면 끊긴 답변 뒤에 붙여 저장하는 안내문. 다시 열었을 때
# 중단됐다는 걸 알리는 용도라 저장은 하되, 제목을 만들 때는 뺀다 — 안 빼면 답이
# 비어 있던 대화의 제목이 이 문장이 되고, 멀쩡하던 제목도 덮어써진다.
INTERRUPTED_NOTE = "대화 전환으로 응답을 중단했습니다."
_TITLE_LIMIT = 36
_USER_TITLE_LIMIT = 48

# ponytail: 답변 첫 문장을 제목으로 자른다. 품질이 부족하면 LLM 요약으로 교체.
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_TOOL_RE = re.compile(r"IRIS_TOOL_\w+_(?:START|END)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_SENTENCE_RE = re.compile(r"^(.+?[.!?。])(?:\s|$)")


@dataclass(frozen=True)
class ChatConversation:
    id: int
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0
    title_locked: bool = False
    project_id: int = 0


@dataclass(frozen=True)
class ChatMessage:
    id: int
    conversation_id: int
    role: str
    content: str
    created_at: str
    model_content: str = ""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def title_from_text(text: str, *, limit: int = _TITLE_LIMIT) -> str:
    body = " ".join((text or "").strip().split())
    if not body:
        return DEFAULT_TITLE
    if len(body) > limit:
        return body[: max(1, limit - 1)] + "…"
    return body


def load_title_basis(db: Database) -> str:
    raw = (db.get_preference(CHAT_TITLE_BASIS_KEY, TITLE_BASIS_LAST) or "").strip()
    if raw in (TITLE_BASIS_FIRST, TITLE_BASIS_LAST):
        return raw
    return TITLE_BASIS_LAST


def save_title_basis(db: Database, basis: str) -> str:
    value = basis if basis in (TITLE_BASIS_FIRST, TITLE_BASIS_LAST) else TITLE_BASIS_LAST
    db.set_preference(CHAT_TITLE_BASIS_KEY, value)
    return value


def summarize_reply(text: str, *, limit: int = _TITLE_LIMIT) -> str:
    """아이리스 답변의 첫 문장을 제목 길이로 자른다."""
    body = _FENCE_RE.sub(" ", text or "")
    body = _TOOL_RE.sub(" ", body)
    body = _LINK_RE.sub(r"\1", body)
    lines: list[str] = []
    for line in body.splitlines():
        line = re.sub(r"^[\s#>*\-]+", "", line)
        line = re.sub(r"^\d+[.)]\s*", "", line)
        line = re.sub(r"[*_`]+", "", line).strip()
        if line:
            lines.append(line)
    body = " ".join(lines)
    if not body:
        return DEFAULT_TITLE
    match = _SENTENCE_RE.match(body)
    sentence = match.group(1) if match else body
    return title_from_text(sentence, limit=limit)


def _message_parts(msg: ChatMessage | dict[str, str]) -> tuple[str, str]:
    if isinstance(msg, dict):
        return str(msg.get("role") or ""), str(msg.get("content") or "")
    return msg.role, msg.content


# ponytail: 어휘 겹침으로 주제 전환을 본다. 오탐이 늘면 LLM 제목 생성으로 교체.
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+-]*|[가-힣]{2,}")
_STOPWORDS = frozenset(
    {
        "and", "for", "the", "this", "that", "with", "from", "please", "can", "you",
        "how", "what", "just", "okay", "yes",
        "그리고", "그래서", "그럼", "아니면", "또는",
        "이것", "그것", "저것", "알려줘", "해줘", "해주세요", "짜줘",
        "관련", "대해", "대한", "뭔가", "어떻게", "무엇", "왜요",
    }
)
_FOLLOWUP_RE = re.compile(
    r"^(그럼|그리고|그래서|아니면|또는|또|다시|응|네|아니|"
    r"ok|okay|yes|no|thanks?|고마워|감사|더|자세히|왜요?)\b",
    re.IGNORECASE,
)


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


def _anchor_line(texts: list[str]) -> str:
    for text in texts:
        if _is_topic_line(text):
            return text
    return texts[0]


# ponytail: 어휘 규칙으로 10~25자 요약을 만든다. 제목이 자주 빗나가면 완료된 턴에서만 LLM으로 교체.
_SUMMARY_LIMIT = 25
_VERB_STEMS = ("수정", "구현", "개선", "추가", "삭제", "연결", "확대", "생성", "검색", "초기화", "저장", "확인", "열기")
_SUMMARY_STOP = _STOPWORDS | {
    "문제",
    "원인",
    "프로그램",
    "링크",
    "입력",
    "선택",
    "이거",
    "저거",
    "그냥",
    "부분",
    "알려",
    "보여",
    "하고",
    "있는",
    "있는데",
    "하면",
    "해서",
}
_TAIL = re.compile(
    r"(에서|으로|부터|까지|처럼|보다|하면|해서|하는|되는|한테|에게|이라고|라고|은|는|이|가|을|를|에|의|도|만|과|와|요|죠|한)$"
)


def _stem_token(token: str) -> str:
    word = token
    if re.fullmatch(r"[가-힣]+", word):
        trimmed = _TAIL.sub("", word)
        if len(trimmed) >= 2:
            word = trimmed
    return word


def summarize_work_title(text: str) -> str:
    """사용자 문장을 대상+작업 형태의 짧은 제목으로 줄인다. 요약이 안 되면 빈 문자열."""
    raw = " ".join((text or "").split())
    if not raw:
        return ""
    auto_link = bool(re.search(r"없으면|자동", raw))
    show_feature = bool(re.search(r"보여\s*주|보고\s*싶", raw))
    folded = raw
    folded = re.sub(r"검색창", "검색", folded)
    folded = re.sub(
        r"프로그램(?:이|을|가)?\s*꺼\w*|꺼지\w*|꺼짐|crash\w*|강제\s*종료",
        " 종료 오류 ",
        folded,
        flags=re.IGNORECASE,
    )
    folded = re.sub(r"에러|버그|errors?", " 오류 ", folded, flags=re.IGNORECASE)
    folded = re.sub(r"고쳐\s*줘(?:요)?", " 수정 ", folded)
    folded = re.sub(r"(붙여|붙이)\s*줘(?:요)?", " 추가 ", folded)
    verb = "|".join(_VERB_STEMS)
    folded = re.sub(rf"({verb})\s*해\s*(?:줘(?:요)?|주세요|봐)?", r" \1 ", folded)
    folded = re.sub(
        r"(?:해\s*줘(?:요)?|해주세요|해\s*주세요|하고\s*싶(?:어|어요|습니다)?|"
        r"싶(?:어|어요|습니다)?|보여\s*주고|보여주고|알려\s*줘(?:요)?|"
        r"문제가\s*있\w*|가능한지|없으면|확인하고|입력하\w*|선택한|창에서|링크를)",
        " ",
        folded,
    )
    tokens: list[str] = []
    for piece in _TOKEN_RE.findall(folded):
        stem = _stem_token(piece)
        key = stem.lower()
        if key in _SUMMARY_STOP or len(stem) < 2:
            continue
        if tokens and tokens[-1].lower() == key:
            continue
        tokens.append(stem)
    if auto_link and "연결" in tokens and "자동" not in tokens:
        tokens.insert(tokens.index("연결"), "자동")
    if show_feature and "기능" not in tokens and not any(t in tokens for t in ("수정", "구현", "삭제")):
        tokens.append("기능")
    if "검색" in tokens and "노드" in tokens:
        merged: list[str] = []
        for token in tokens:
            if token == "노드" and merged and merged[-1] == "검색":
                merged.append("및")
            merged.append(token)
        tokens = merged
    if len([t for t in tokens if t != "및"]) < 2:
        return ""
    while len(tokens) > 2 and len(" ".join(tokens)) > _SUMMARY_LIMIT:
        drop_at = -2 if tokens[-1] in _VERB_STEMS or tokens[-1] == "기능" else -1
        if tokens[drop_at] == "및" and len(tokens) > 3:
            drop_at = -3
        tokens.pop(drop_at)
    title = " ".join(tokens).strip()
    if len(title) > _SUMMARY_LIMIT:
        title = title[: _SUMMARY_LIMIT - 1].rstrip() + "…"
    if title == raw:
        return ""
    return title


def _user_lines(messages: list[ChatMessage] | list[dict[str, str]]) -> list[str]:
    users: list[str] = []
    for msg in messages:
        role, content = _message_parts(msg)
        body = _title_user_text(content)
        if role == "user" and body:
            users.append(body)
    return users


def _title_user_text(text: str) -> str:
    """제목 재료에서 첨부 표식과 그 뒤 본문을 뺀다."""
    body = text or ""
    for mark in ("[첨부 파일]", "[자료 본문]"):
        at = body.find(mark)
        if at >= 0:
            body = body[:at]
    body = re.sub(r'\s*@"[^"]*"', " ", body)
    return " ".join(body.split())


def _reply_texts(messages: list[ChatMessage] | list[dict[str, str]]) -> list[str]:
    replies: list[str] = []
    for msg in messages:
        role, content = _message_parts(msg)
        if role != "assistant":
            continue
        body = (content or "").replace(INTERRUPTED_NOTE, "\n").strip()
        if body:
            replies.append(body)
    return replies


def _question_echo(raw: str, title: str) -> bool:
    """조사·요청어만 빠져 질문과 같은 제목이면 True. 새 단어나 두 단어 이하 핵심은 False."""
    raw_s = " ".join((raw or "").split())
    title_s = " ".join((title or "").split())
    if not title_s or title_s == raw_s:
        return True
    title_tokens = [tok for tok in title_s.split() if tok != "및"]
    if any(tok not in raw_s for tok in title_tokens):
        return False
    # 「IRIS 구조」처럼 두 단어 이하로 줄인 핵심은 질문 전문이 아니다.
    if len(title_tokens) <= 2 and len(raw_s) > len(title_s) + 2:
        return False
    return True


def _first_reply_title(
    messages: list[ChatMessage] | list[dict[str, str]],
) -> str:
    seen_user = False
    for msg in messages:
        role, content = _message_parts(msg)
        if role == "user" and _title_user_text(content):
            seen_user = True
            continue
        if not seen_user or role != "assistant":
            continue
        body = (content or "").replace(INTERRUPTED_NOTE, "\n").strip()
        if not body:
            continue
        title = summarize_reply(body)
        if title not in ("", DEFAULT_TITLE):
            return title
    return DEFAULT_TITLE


def suggest_title(
    messages: list[ChatMessage] | list[dict[str, str]],
    *,
    basis: str = TITLE_BASIS_LAST,
) -> str:
    """last는 최근 답변의 첫 문장. first는 첫 질문의 작업 제목, 아니면 그 답변."""
    if basis != TITLE_BASIS_FIRST:
        replies = _reply_texts(messages)
        if not replies:
            return DEFAULT_TITLE
        title = summarize_reply(replies[-1])
        return title if title not in ("", DEFAULT_TITLE) else DEFAULT_TITLE
    users = _user_lines(messages)
    if not users:
        return DEFAULT_TITLE
    anchor = _anchor_line(users)
    work = summarize_work_title(anchor) if _is_topic_line(anchor) else ""
    if work and not _question_echo(anchor, work):
        return work
    return _first_reply_title(messages)


def ensure_chat_schema(db: Database) -> None:
    db._execute(
        """
        CREATE TABLE IF NOT EXISTS chat_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '새 채팅',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            title_locked INTEGER NOT NULL DEFAULT 0,
            project_id INTEGER NOT NULL DEFAULT 0
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
    if "project_id" not in cols:
        db._execute(
            "ALTER TABLE chat_conversations "
            "ADD COLUMN project_id INTEGER NOT NULL DEFAULT 0"
        )
    # 예전 버전이 중단 안내문으로 붙여 둔 제목을 기본 제목으로 되돌린다(직접 붙인 제목 제외).
    db._execute(
        "UPDATE chat_conversations SET title = ? WHERE title = ? AND title_locked = 0",
        (DEFAULT_TITLE, summarize_reply(INTERRUPTED_NOTE)),
    )
    message_cols = {
        str(row["name"])
        for row in db._execute("PRAGMA table_info(chat_messages)").fetchall()
    }
    if "model_content" not in message_cols:
        db._execute(
            "ALTER TABLE chat_messages ADD COLUMN model_content TEXT NOT NULL DEFAULT ''"
        )
    db._commit()


def _conv_from_row(row) -> ChatConversation:
    try:
        locked = bool(int(row["title_locked"] or 0))
    except (KeyError, IndexError, TypeError, ValueError):
        locked = False
    try:
        project_id = int(row["project_id"] or 0)
    except (KeyError, IndexError, TypeError, ValueError):
        project_id = 0
    return ChatConversation(
        id=int(row["id"]),
        title=str(row["title"] or DEFAULT_TITLE),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
        message_count=int(row["message_count"] or 0),
        title_locked=locked,
        project_id=project_id,
    )


def create_conversation(
    db: Database,
    *,
    title: str = DEFAULT_TITLE,
    project_id: int = 0,
) -> ChatConversation:
    ensure_chat_schema(db)
    stamp = _now()
    name = (title or "").strip() or DEFAULT_TITLE
    folder = int(project_id or 0)
    cur = db._execute(
        """
        INSERT INTO chat_conversations(title, created_at, updated_at, title_locked, project_id)
        VALUES(?, ?, ?, 0, ?)
        """,
        (name, stamp, stamp, folder),
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
        project_id=folder,
    )


def get_conversation(db: Database, conversation_id: int) -> ChatConversation | None:
    ensure_chat_schema(db)
    row = db._execute(
        """
        SELECT c.id, c.title, c.created_at, c.updated_at, c.title_locked, c.project_id,
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
        SELECT c.id, c.title, c.created_at, c.updated_at, c.title_locked, c.project_id,
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
        SELECT id, conversation_id, role, content, created_at, model_content
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
            model_content=str(row["model_content"] or ""),
        )
        for row in rows
    ]


def history_dicts(db: Database, conversation_id: int) -> list[dict[str, str]]:
    return [
        {"role": m.role, "content": m.content, **({"model_content": m.model_content} if m.model_content else {})}
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


def refresh_conversation_title(db: Database, conversation_id: int) -> None:
    """기준만 저장한다. 이미 붙은 제목을 문장 자르기로 다시 쓰지 않는다.

    다음 답변을 만들 때 모델이 그 기준으로 제목을 붙인다.
    """
    del db, conversation_id


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


def append_message(db: Database, conversation_id: int, role: str, content: str, *, model_content: str = "") -> int:
    ensure_chat_schema(db)
    stamp = _now()
    cur = db._execute(
        """
        INSERT INTO chat_messages(conversation_id, role, content, created_at, model_content)
        VALUES(?, ?, ?, ?, ?)
        """,
        (int(conversation_id), str(role or ""), str(content or ""), stamp, model_content),
    )
    db._execute(
        "UPDATE chat_conversations SET updated_at = ? WHERE id = ?",
        (stamp, int(conversation_id)),
    )
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


def start_new_conversation(db: Database, *, project_id: int = 0) -> int:
    """현재 빈 세션이 같은 폴더에 있으면 재사용, 아니면 새로 만든다."""
    ensure_chat_schema(db)
    folder = int(project_id or 0)
    current = active_conversation_id(db)
    if current is not None:
        conv = get_conversation(db, current)
        if conv is not None and conv.message_count <= 0 and conv.project_id == folder:
            return current
    conv = create_conversation(db, project_id=folder)
    set_active_conversation_id(db, conv.id)
    return conv.id
