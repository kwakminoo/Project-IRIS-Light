"""이전 대화 참고 — SpeakTool `chat.search_past` 가 다른 대화 기록을 찾는다.

두 가지를 지킨다.

- **지금 대화는 빼고 찾는다.** 이미 모델 컨텍스트에 있고, 안 빼면 방금 보낸
  질문이 자기 자신을 1위로 찾아온다.
- **무엇을 참고했는지 사용자에게 보인다**(`sources_note`). 엉뚱한 기록이 섞이면
  사용자가 보고 설정에서 끌 수 있어야 한다.

채팅을 지우면 그 대화의 기록도 지워진다(`history_index.forget_conversation`).

기록은 **질문과 답을 한 쌍**으로 붙인다(`PastChat`). 질문만 걸리면 모델이 쓸
게 없고, 답만 걸리면 무엇에 대한 답인지 모른다. 실제 앱에서 "저번에 설치 오류
어떻게 고쳤지?"가 다른 테스트 채팅의 **같은 질문**(답 없음)을 찾아왔다 — 그런
기록은 버린다.

의도 판별(저번/이전 대화 regex)은 없다. 모델이 `chat.search_past` 를 고를 때만
검색한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from iris.knowledge.history_index import SearchHit, like_terms
from iris.knowledge.history_store import HistoryEntry, get_entry
from iris.storage.conversations import INTERRUPTED_NOTE

# 이보다 짧은 말("응", "고마워")로는 찾지 않는다 — 키워드 검색이 잡음만 올린다.
MIN_QUERY_CHARS = 4
# SpeakTool 한 호출에 붙일 상한. 토큰·잡음을 막는다.
MAX_PAST_HITS = 3
# SpeakTool 경로: 임베더 없거나 embed off 일 때 (키워드-only 금지).
SEMANTIC_UNAVAILABLE_MSG = (
    "semantic search unavailable; enable embed in settings or install an embedding model"
)

# 인수인계·루틴은 "관련 기록이 있다"는 전제에서 순위만 매기면 되지만, 평소
# 채팅은 "관련 기록이 있기나 한가"를 판정해야 한다. 그래서 더 엄격하게 거른다.
# bge-m3 로 잰 값(질의는 결과를 보기 전에 고정): 관련 21개·무관 12개 질문에서
#   유사도 0.55 이상 → 관련 19/21 찾음, 무관 1/12 새어듦("운동 루틴 짜줘")
#   0.58 이상 → 관련 15/21, 무관 0/12
# 새어든 1건 바로 위(0.572)로 자르면 그 한 문장에 맞추는 셈이라 0.55 로 뒀다.
PAST_MIN_SIMILARITY = 0.55
# 벡터 점수가 없는 기록(임베딩 모델 없음·3초 초과로 키워드만 쓴 경우)은 질문의
# 단어가 이만큼 겹쳐야 붙인다. 같은 측정에서 관련 5/21, 무관 0/12 — 거의 안
# 붙지만 엉뚱한 것도 안 붙는다. 1단어면 관련 10/21, 무관 1/12("저녁").
PAST_MIN_TERMS = 2

# 지금 질문과 이만큼 비슷한 옛 질문은 되풀이일 뿐이라 답이 없으면 버린다.
_ECHO_RATIO = 0.8
_NON_WORD = re.compile(r"[^\w가-힣]+")


@dataclass(frozen=True)
class PastChat:
    """검색에 걸린 기록 + 같은 대화에서 그 앞뒤 한 턴씩(시간 순).

    앞뒤를 같이 봐야 뜻이 산다. 앱에서 "robocopy 로 바꾸니까 설치 됐어요!"
    (사용자 후속 말)가 걸렸는데, 정작 해결법은 그 **앞** 아이리스 답에 있었다.
    """

    hit: SearchHit
    turns: tuple[HistoryEntry, ...] = ()

    @property
    def entry(self) -> HistoryEntry:
        return self.hit.entry

    @property
    def similarity(self) -> float | None:
        return self.hit.similarity

    @property
    def question(self) -> HistoryEntry | None:
        """걸린 게 사용자 말이면 그것, 아니면 앞의 사용자 말."""
        if self.entry.role == "user":
            return self.entry
        users = [t for t in self.turns if t.role == "user" and t.id < self.entry.id]
        return users[-1] if users else None

    @property
    def answer(self) -> HistoryEntry | None:
        """쓸 만한 아이리스 답(걸린 것이 답이면 그것, 아니면 앞뒤에서)."""
        if self.entry.role == "assistant":
            return self.entry
        for turn in self.turns:
            if turn.role == "assistant":
                return turn
        return None

_HEADER = (
    "# 이전 대화에서 찾은 기록 (참고용)\n\n"
    "아래는 **지금과 다른, 예전 대화**에서 오간 내용이다. 지금 질문과 관련 있을 "
    "때만 쓰고, 쓸 때는 \"이전 대화에서\"라고 밝혀라. 관련 없으면 무시하고 "
    "언급하지 마라. 지금 대화의 내용이 이것과 다르면 지금 대화를 따른다."
)


def past_chat_limit(retrieval_limit: int) -> int:
    return max(0, min(int(retrieval_limit), MAX_PAST_HITS))


def should_search(text: str) -> bool:
    """도구 내부 길이 게이트. 의도 regex 없음 — 호출자가 검색 여부를 고른다."""
    return len((text or "").strip()) >= MIN_QUERY_CHARS


def find_past_chats(
    service: object,
    query: str,
    current_conversation_id: int,
    ollama_client: object | None = None,
    *,
    limit: int | None = None,
) -> list[SearchHit]:
    """다른 대화의 기록을 찾는다. `ollama_client` 가 있으면 의미검색까지 한다.

    의미검색은 질의 임베딩이 1~3초 걸리므로 클라이언트를 줄 때는 워커 스레드에서
    불러야 한다. 없으면 키워드 검색만이라 UI 스레드에서도 즉시 끝난다.
    """
    settings = service.history_settings  # type: ignore[attr-defined]
    if not settings.enabled or not settings.reference_past_chats:
        return []
    if not should_search(query):
        return []
    capped = past_chat_limit(
        settings.retrieval_limit if limit is None else limit
    )
    if capped <= 0:
        return []
    embedder = None
    if ollama_client is not None:
        from iris.runtime.model_switch import resolve_embedder

        embedder = resolve_embedder(settings, ollama_client)
    hits = service.retrieve(  # type: ignore[attr-defined]
        query,
        limit=capped * 3,  # 거르고 나서 capped 만큼 남도록 넉넉히
        embedder=embedder,
        exclude_conversation_id=int(current_conversation_id or 0) or None,
        # 1위 대비 컷을 끈다 — 똑같은 옛 질문이 유사도 1.0으로 1위면 쓸모 있는
        # 기록까지 다 잘린다(실측). 아래 is_relevant 의 절대 기준으로 거른다.
        vector_margin=None,
    )
    db = service.db  # type: ignore[attr-defined]
    out: list[PastChat] = []
    covered: set[int] = set()  # 이미 다른 묶음에 들어간 기록 — 겹쳐 붙이지 않는다
    for hit in hits:
        if hit.entry.id in covered or not is_relevant(query, hit):
            continue
        chat = pair_turn(db, hit)
        if chat is None or _is_echo(query, chat):
            continue
        # 앞 묶음이 이미 붙인 턴(같은 대화의 겹치는 앞뒤)은 빼고 붙인다.
        chat = PastChat(chat.hit, turns=tuple(t for t in chat.turns if t.id not in covered))
        covered.update(t.id for t in chat.turns)
        out.append(chat)
        if len(out) >= capped:
            break
    return out


def semantic_past_chats(
    service: object,
    query: str,
    current_conversation_id: int,
    ollama_client: object,
    *,
    limit: int | None = None,
) -> tuple[list, str | None]:
    """Embed-backed past search for SpeakTool. Never keyword-only.

    Returns (chats, message). message is set when search cannot run; chats empty.
    Caller must supply a real Ollama client and run this off the UI thread.
    """
    settings = service.history_settings  # type: ignore[attr-defined]
    if not settings.enabled or not settings.reference_past_chats:
        return [], "past chat reference is disabled in settings"
    if not settings.embed_enabled:
        return [], SEMANTIC_UNAVAILABLE_MSG
    from iris.runtime.model_switch import resolve_embedder

    if resolve_embedder(settings, ollama_client) is None:
        return [], SEMANTIC_UNAVAILABLE_MSG
    chats = find_past_chats(
        service,
        query,
        current_conversation_id,
        ollama_client,
        limit=limit,
    )
    return chats, None


def _clean_answer(text: str) -> str:
    return (text or "").replace(INTERRUPTED_NOTE, "").strip()


def _neighbor(db, entry: HistoryEntry, *, after: bool) -> HistoryEntry | None:
    """같은 대화에서 바로 다음(또는 앞) 대화 기록. 수행 기록 등은 건너뛴다."""
    if not entry.conversation_id:
        return None
    op, order = (">", "ASC") if after else ("<", "DESC")
    row = db._execute(
        f"SELECT id FROM wiki_history WHERE conversation_id = ? AND kind = 'chat' "
        f"AND id {op} ? ORDER BY id {order} LIMIT 1",
        (int(entry.conversation_id), int(entry.id)),
    ).fetchone()
    return get_entry(db, int(row["id"])) if row else None


def _useful(entry: HistoryEntry | None) -> bool:
    """중단 안내문뿐인 답은 쓸모없다."""
    if entry is None:
        return False
    if entry.role == "assistant":
        return bool(_clean_answer(entry.body))
    return bool((entry.body or "").strip())


def pair_turn(db, hit: SearchHit) -> PastChat | None:
    """걸린 기록에 같은 대화의 앞뒤 한 턴을 붙인다. 쓸 내용이 없으면 None."""
    entry = hit.entry
    if entry.role not in ("user", "assistant"):
        return PastChat(hit, turns=(entry,))  # 수행·생성물 기록은 그대로
    if not _useful(entry):
        return None  # "대화 전환으로 응답을 중단했습니다."뿐인 답
    turns = [entry]
    prev = _neighbor(db, entry, after=False)
    if _useful(prev) and prev.role != entry.role:
        turns.insert(0, prev)
    nxt = _neighbor(db, entry, after=True)
    if _useful(nxt) and nxt.role != entry.role:
        turns.append(nxt)
    return PastChat(hit, turns=tuple(turns))


def _normalized(text: str) -> str:
    return _NON_WORD.sub("", (text or "").lower())


def _is_echo(query: str, chat: PastChat) -> bool:
    """답 없이 지금 질문을 거의 그대로 되풀이한 옛 질문인가."""
    if chat.entry.role != "user" or chat.answer is not None:
        return False
    a, b = _normalized(query), _normalized(chat.question.body)
    if not a or not b:
        return False
    # 포함 여부로 보면 안 된다 — "설치 오류는 venv 소유권 문제였어요"는 질문을 품고도
    # 정보를 더한다. 문장 전체가 거의 같을 때만 되풀이로 본다.
    return SequenceMatcher(None, a, b).ratio() >= _ECHO_RATIO


def is_relevant(query: str, hit: SearchHit) -> bool:
    """평소 채팅에 붙일 만큼 관련 있는가. 기준값의 근거는 위 상수 주석."""
    if hit.similarity is not None and hit.similarity >= PAST_MIN_SIMILARITY:
        return True
    text = f"{hit.entry.title} {hit.entry.body}"
    return sum(1 for term in like_terms(query) if term in text) >= PAST_MIN_TERMS


def warm_embedder(service: object, ollama_client: object | None) -> str:
    """임베딩 모델을 미리 메모리에 올린다. 올린 모델 이름, 안 올렸으면 빈 문자열.

    입력하는 동안 불러 두면 보낼 때 콜드 로드(실측 9초)를 안 탄다. 이미 떠 있으면
    0.6초 안에 끝나고 붙잡아 두는 시간만 연장된다. **워커 스레드에서만 부를 것.**
    """
    settings = service.history_settings  # type: ignore[attr-defined]
    if not settings.enabled or not settings.reference_past_chats:
        return ""
    from iris.runtime.model_switch import resolve_embedder

    embedder = resolve_embedder(settings, ollama_client)
    if embedder is None:
        return ""
    embedder.embed(["warmup"])
    return embedder.model


def _cut(text: str, limit: int) -> str:
    body = (text or "").strip()
    return body if len(body) <= limit else body[:limit] + " …(생략)"


def format_past_chats_for_prompt(chats: list, *, body_limit: int = 500) -> str:
    if not chats:
        return ""
    lines = [_HEADER, ""]
    for chat in chats:
        turns = getattr(chat, "turns", ()) or (chat.entry,)
        if all(t.role not in ("user", "assistant") for t in turns):
            lines.append(f"## {chat.entry.as_context_line()}")
            lines.extend(["", _cut(chat.entry.body, body_limit), ""])
            continue
        lines.append(f"## [{chat.entry.created_at}] 이전 대화")
        for turn in turns:
            who = "사용자" if turn.role == "user" else "아이리스"
            lines.append(f"- {who}: {_cut(_clean_answer(turn.body), body_limit)}")
        lines.append("")
    return "\n".join(lines)


def _snippet(text: str, limit: int = 24) -> str:
    one_line = " ".join((text or "").split())
    return one_line if len(one_line) <= limit else one_line[:limit] + "…"


def sources_note(chats: list) -> str:
    """채팅 화면에 띄울 한 줄 — 무엇을 참고했는지. 짝이 있으면 질문으로 부른다."""
    if not chats:
        return ""
    parts = []
    for chat in chats:
        entry = getattr(chat, "question", None) or chat.entry
        day = entry.created_at[5:10].replace("-", "/").lstrip("0") if entry.created_at else ""
        label = entry.title or _snippet(entry.body)
        parts.append(f"{day} 「{label}」".strip())
    return f"이전 대화 {len(chats)}건 참고 — " + ", ".join(parts)
