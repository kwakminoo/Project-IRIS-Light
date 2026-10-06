"""오늘 사실·위키·구조 질문을 가려 검색과 발췌를 모델 맥락에 넣는다.

답 문장은 바꾸지 않는다. 고정 문장을 붙이거나 지우는 일은 하지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_TODAY = re.compile(
    r"뉴스|날씨|기온|미세먼지|환율|주가|시세|코스피|코스닥|비트코인|경기\s*결과|스코어|속보"
)
_NOT_TODAY = re.compile(r"계산|코드|의견|소설|번역|설계")
_STORED = re.compile(r"위키|노트|inbox|첨부|저장(?:해\s*둔|된\s*자료|한\s*자료)")
_SAVE_ACT = re.compile(r"저장해|넣어\s*줘|기록해|옮겨|삭제해|보내\s*줘|실행해|만들어")
_CODE_WORK = re.compile(r"고쳐|구현|코드|리팩터|짜\s*줘|작성")
_IRIS_NAME = re.compile(r"아이리스|iris", re.IGNORECASE)
_IRIS_HOW = re.compile(r"어떻게\s*(?:짜|되|고치|바꾸)")
_IRIS_TOPIC = re.compile(r"구조|커스텀|타일|화면|비율|노트|위키")
_CODE_REQUEST = re.compile(r"짜\s*줘|작성해|구현해|만들어\s*줘|고쳐\s*줘")
_MARKERS = ("[자료 본문]", "BEGIN ATTACHMENT TEXT")


def classify_turn(text: str) -> str:
    raw = text or ""
    if _TODAY.search(raw) and not _NOT_TODAY.search(raw):
        return "today"
    if _STORED.search(raw) and not _SAVE_ACT.search(raw):
        return "stored"
    if _SAVE_ACT.search(raw):
        return "action"
    return "other"


def turn_has_grounding_material(text: str, history: list | None, attachments: list | None) -> bool:
    """첨부가 있는데 글·코드 작업이 아니면 저장 자료 질문으로 본다."""
    if _CODE_WORK.search(text or ""):
        return False
    if attachments:
        return True
    return bool(material_from_history(history).strip())


def wants_wiki_lookup(text: str) -> bool:
    raw = text or ""
    if _SAVE_ACT.search(raw):
        return False
    return bool(re.search(r"위키|노트|inbox|저장(?:해\s*둔|된|한)", raw))


def wants_iris_structure(text: str) -> bool:
    """아이리스 구조·커스텀을 묻는 말. 코드 작성·저장·오늘 사실은 아니다."""
    raw = text or ""
    if _SAVE_ACT.search(raw) or _CODE_REQUEST.search(raw) or _TODAY.search(raw):
        return False
    if _IRIS_HOW.search(raw):
        return True
    if re.search(r"타일\s*비율", raw):
        return True
    return bool(_IRIS_NAME.search(raw) and _IRIS_TOPIC.search(raw))


def search_failure_reply(error: str, query: str) -> str:
    """검색이 안 된 사실. 사용자에게 보여줄 문장이 아니다."""
    from iris.runtime.routine_search import SearchOutcome, format_evidence

    return format_evidence(
        SearchOutcome(query=query or "", error=error or "알 수 없음")
    )


def search_timeout_reply(query: str) -> str:
    return search_failure_reply("검색 시간 초과", query)


@dataclass(frozen=True)
class TodaySearch:
    ok: bool
    evidence: str
    reply: str
    urls: list[str]


def today_search(query: str) -> TodaySearch:
    from iris.runtime.routine_search import format_evidence, run_search

    text = " ".join((query or "").split())[:180]
    engine = "google_news" if any(word in text for word in ("뉴스", "속보")) else "google"
    outcome = run_search(text, engine=engine)
    if not outcome.ok:
        return TodaySearch(False, "", search_failure_reply(outcome.error, outcome.query or text), [])
    urls = [hit.link for hit in outcome.hits if hit.link]
    return TodaySearch(True, format_evidence(outcome), "", urls)


def evidence_corpus(*, web: str = "", wiki: str = "", material: str = "", code: str = "") -> str:
    return "\n".join(part for part in (web, wiki, material, code) if (part or "").strip())


def material_from_history(history: list | None) -> str:
    last = ""
    for item in reversed(history or []):
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        last = "\n".join(
            str(item.get(key) or "") for key in ("model_content", "content") if item.get(key)
        )
        break
    chunks: list[str] = []
    for marker in _MARKERS:
        if marker in last:
            chunks.append(last.split(marker, 1)[1])
    return "\n".join(chunks)


def settle_grounded_answer(
    text: str,
    *,
    kind: str = "",
    evidence: str = "",
    web_failed: bool = False,
    failure_reply: str = "",
    tool_ok: int = 0,
    tool_lines: list[str] | None = None,
) -> str:
    """모델이 쓴 답을 그대로 둔다."""
    del kind, evidence, web_failed, failure_reply, tool_ok, tool_lines
    return text or ""


def _check() -> None:
    assert classify_turn("오늘 날씨 알려줘") == "today"
    assert classify_turn("주가 알려줘") == "today"
    assert classify_turn("오늘 뉴스 3개") == "today"
    assert classify_turn("환율 계산해줘") == "other"
    assert classify_turn("위키에 강화학습 있어?") == "stored"
    assert classify_turn("위키에 저장해줘") == "action"
    assert classify_turn("함수 짜줘") == "other"
    assert turn_has_grounding_material("요약해줘", [], ["a.pdf"])
    assert not turn_has_grounding_material("코드 짜줘", [], ["a.py"])
    assert wants_wiki_lookup("위키에 있어")
    assert not wants_wiki_lookup("위키에 저장해줘")
    assert not wants_wiki_lookup("첨부 pdf 요약")
    assert wants_iris_structure("타일 비율이 어떻게 되지")
    assert wants_iris_structure("이 화면을 어떻게 고치지")
    assert wants_iris_structure("아이리스는 어떻게 짜여 있어")
    assert not wants_iris_structure("함수 짜줘")
    assert not wants_iris_structure("위키에 저장해줘")
    assert not wants_iris_structure("오늘 날씨")

    image = "감마 보정과 히스토그램 평활화로 보입니다."
    shown = settle_grounded_answer(
        image,
        kind="stored",
        evidence="BEGIN ATTACHMENT TEXT\n쪽 번호 없음",
        web_failed=False,
        failure_reply="",
        tool_ok=0,
        tool_lines=[],
    )
    assert shown == image
    assert "발췌에 없다" not in shown

    tree = "src/\n  main.py"
    ratio = settle_grounded_answer(
        tree,
        kind="iris",
        evidence="80:20 타일",
        web_failed=False,
        failure_reply="",
        tool_ok=0,
        tool_lines=[],
    )
    assert ratio == tree
    assert "노트에 없다" not in ratio

    mail = "메일을 보냈습니다. 10월 달력은 그대로입니다."
    claimed = settle_grounded_answer(
        mail,
        kind="action",
        evidence="",
        web_failed=True,
        failure_reply="실패",
        tool_ok=0,
        tool_lines=[],
    )
    assert claimed == mail
    assert "ok 없음" not in claimed

    fail = search_failure_reply("SerpApi 키가 없습니다", "오늘 날씨")
    assert "SerpApi 키가 없습니다" in fail
    assert "오늘 날씨" in fail
    assert "발췌에 없다" not in fail

    corpus = evidence_corpus(web="검색", wiki="", material="", code="80:20")
    assert "예전 대화" not in corpus and "80:20" in corpus
    history = [{"role": "user", "content": "질문\n\n[자료 본문]\n원문 42"}]
    assert "42" in material_from_history(history)
    print("answer_grounding self-check ok")


if __name__ == "__main__":
    _check()
