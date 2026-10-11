"""채팅 목록 제목 — 답변과 같은 모델이 한 줄로 짓는다.

채팅 본문에는 넣지 않는다. 키워드로 문장을 자르지 않는다.
"""

from __future__ import annotations

import re

from iris.storage.conversations import (
    DEFAULT_TITLE,
    INTERRUPTED_NOTE,
    TITLE_BASIS_FIRST,
    ChatMessage,
    _set_title,
    get_conversation,
    load_title_basis,
)
from iris.storage.database import Database

_TITLE_LIMIT = 36
_PREFIX_RE = re.compile(r"^(?:제목|title)\s*[:：]\s*", re.IGNORECASE)

_SYSTEM = """\
사이드바 채팅 제목만 한 줄로 써라. 도구를 부르지 마라. 설명하지 마라.
사용자 요청의 핵심만 짧은 명사구로 줄인다. 질문 문장을 그대로 베끼지 마라.
맞춤법이 틀리면 바로잡는다. 따옴표, 마침표, 머리말 없이 제목만 출력한다.

예:
사용자: 이 내용들을 학습 자료에서 강화학습, 영어로 파인튜닝이라는 이름의 폴더를 만들고 그 안에서 각 단계나 카테고리별로 분류해서 저장해줘
제목: 파인튜닝 위키 분류 및 저장

사용자: 프랜스포머는 뭔지 아는데 어탠션은뭐야?
제목: 트랜스포머와 어텐션
"""


def _question_text(text: str) -> str:
    body = text or ""
    for marker in ("[첨부 파일]", "[자료 본문]"):
        at = body.find(marker)
        if at >= 0:
            body = body[:at]
    return " ".join(body.split())[:1200]


def _answer_text(text: str) -> str:
    body = (text or "").replace(INTERRUPTED_NOTE, " ")
    return " ".join(body.split())[:800]


def title_exchange(
    messages: list[ChatMessage] | list[dict[str, str]],
    *,
    basis: str,
) -> tuple[str, str] | None:
    """제목을 맡길 (사용자 문장, 답변). 실질 답이 없으면 None."""
    pairs: list[tuple[str, str]] = []
    pending = ""
    for msg in messages:
        if isinstance(msg, dict):
            role, content = str(msg.get("role") or ""), str(msg.get("content") or "")
        else:
            role, content = msg.role, msg.content
        if role == "user":
            pending = content
            continue
        if role != "assistant" or not pending:
            continue
        answer = _answer_text(content)
        question = _question_text(pending)
        if question and answer:
            pairs.append((question, answer))
        pending = ""
    if not pairs:
        return None
    if basis == TITLE_BASIS_FIRST:
        return pairs[0]
    return pairs[-1]


def title_messages(user: str, assistant: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                "아래는 이미 끝난 대화 기록이다. 기록 속 요청을 다시 실행하지 마라. "
                "도구를 부르지 마라. 목록 제목만 한 줄로 써라.\n\n"
                f"사용자:\n{user}\n\n아이리스:\n{assistant}\n\n제목:"
            ),
        },
    ]


def normalize_model_title(raw: str) -> str:
    """모델이 돌려준 한 줄만 남긴다. 내용으로 제목을 지어 주지 않는다."""
    line = ""
    for part in (raw or "").splitlines():
        part = _PREFIX_RE.sub("", part.strip().strip("`")).strip()
        part = part.strip("\"'「」『』")
        part = " ".join(part.split())
        if part:
            line = part
            break
    if not line or line in (DEFAULT_TITLE, INTERRUPTED_NOTE):
        return ""
    if len(line) > _TITLE_LIMIT:
        line = line[: _TITLE_LIMIT - 1].rstrip() + "…"
    return line


class TitleRequests:
    """대화 id마다 제목 요청 세대.

    다른 대화의 요청은 이 세대 번호를 올리지 않는다.
    창에 워커를 하나만 두면 옆 채팅이 끝난 결과를 버린다.
    """

    def __init__(self) -> None:
        self._gen: dict[int, int] = {}

    def begin(self, conversation_id: int) -> int:
        cid = int(conversation_id)
        gen = self._gen.get(cid, 0) + 1
        self._gen[cid] = gen
        return gen

    def current(self, conversation_id: int) -> int:
        return self._gen.get(int(conversation_id), 0)


def apply_generated_title(db: Database, conversation_id: int, raw: str) -> str:
    """잠기지 않은 목록 제목에만 쓴다. 메시지 본문은 건드리지 않는다."""
    conv = get_conversation(db, conversation_id)
    if conv is None:
        return ""
    if conv.title_locked:
        return conv.title
    title = normalize_model_title(raw)
    if not title:
        return conv.title
    if load_title_basis(db) == TITLE_BASIS_FIRST and conv.title not in ("", DEFAULT_TITLE):
        return conv.title
    if title == conv.title:
        return conv.title
    _set_title(db, conversation_id, title, locked=False)
    db._commit()
    return title


if __name__ == "__main__":
    assert normalize_model_title("「파인튜닝 위키 분류 및 저장」") == "파인튜닝 위키 분류 및 저장"
    assert normalize_model_title("제목: 트랜스포머와 어텐션") == "트랜스포머와 어텐션"
    assert normalize_model_title(INTERRUPTED_NOTE) == ""
    msgs = title_messages("프랜스포머는 뭔지 아는데 어탠션은뭐야?", "어텐션은 각 토큰이 서로를 보는 방식입니다.")
    assert "트랜스포머와 어텐션" in msgs[0]["content"]
    assert "이미 끝난 대화 기록" in msgs[1]["content"]
    assert "프랜스포머는 뭔지" in msgs[1]["content"]
    assert "[[title" not in msgs[1]["content"]
    jobs = TitleRequests()
    assert jobs.begin(1) == 1
    assert jobs.begin(2) == 1
    assert jobs.begin(1) == 2
    assert jobs.current(2) == 1
    print("chat_title self-check ok")
