"""긴 작업 턴 감독. 모델의 완료 문장은 완료 증거가 아니다."""

from __future__ import annotations

import re

CAP = 8

NOTE_CONTINUE = "남은 작업이 있어 이어서 진행합니다."
NOTE_CAP = "자동 진행 상한에 도달했습니다. 이어서 하려면 다시 요청하세요."
FOLLOWTHROUGH_UTTERANCE = (
    "이미 요청된 작업을 멈추지 마라. 완료라고 말하지 말고 이번 턴에 도구를 호출하라. "
    "사이트 전체 저장이면 wiki.import_pages 한 번이면 된다. "
    "파일·스크립트 생성이면 SpeakTools project.write_file 을 호출하라."
)
FILE_FOLLOWTHROUGH_UTTERANCE = (
    "완료라고 말하지 말고 이번 턴에 SpeakTools project.write_file 을 호출하라. "
    "ok 와 디스크 path 없이 생성·작성했다고 말하지 마라."
)

_GOAL_BULK = ("저장", "수집", "전부", "모든", "하나하나", "순차", "페이지")
_CONTINUE = (
    "계속할까요",
    "진행할까요",
    "계속",
    "이어서",
    "다음 장",
    "넘어가",
    "진행하겠",
    "저장하겠",
    "시작하겠",
)
_ASK = ("어느 쪽", "어떤 파일", "어느 파일", "삭제할까")
_DONE = (
    "저장했",
    "저장 완료",
    "가져왔",
    "모두 저장",
    "전부 저장",
    "정리했",
    "덮어",
    "번역해 두",
    "번역했",
    "열었",
    "열어 드",
    "옮겼",
    "이동 완료",
    "분류했",
    "생성했",
    "생성하겠",
    "작성했",
    "작성하겠",
    "작성을 완료",
    "작성을 마쳤",
    "코드를 짰",
    "코드는 작성",
    "처리 완료",
    "만들었",
    "만들겠",
)
_OR_CHOICE = re.compile(r"\S{1,20}\s또는\s\S{1,20}")
_BATCH_SAVED = re.compile(r"\d+\s*건\s*저장")


def counts_as_tool_ok(message: str) -> bool:
    """도구 성공 진행 줄만 센다. completed / running / respond·chat_only 는 성공이 아니다."""
    text = (message or "").strip()
    low = text.lower()
    if "completed" in low or "running" in low:
        return False
    # Exit tools satisfy "≥1 tool" on the wire but are not side-effect evidence.
    if low.startswith("respond ") or low == "respond ok" or "respond ok" in low:
        return False
    if "chat_only" in low.replace("-", "_"):
        return False
    # Hermes 내장 terminal/shell/bash 는 Iris에서 비활성 — IDE project.run 증거로 세지 않는다.
    first = low.split(":", 1)[0].strip()
    head = first.split()[0] if first else ""
    if head in {"terminal", "shell", "bash", "run_terminal_cmd", "execute"}:
        return False
    return text.endswith(" ok") or " ok " in text


def decide_followthrough(
    goal: str,
    assistant: str,
    tool_ok_count: int,
    followups: int,
    *,
    cap: int = CAP,
    moved: bool = False,
    moved_folder: bool = False,
    list_truncated: bool = False,
) -> str:
    """continue | stop | ask. 채팅 실패 경로에서는 호출하지 않는다."""
    if followups >= cap:
        return "stop"
    text = assistant or ""
    if _BATCH_SAVED.search(text) and "실패" in text:
        return "stop"
    if _asks_choice(text):
        return "ask"
    goal_s = goal or ""
    if any(word in goal_s for word in _GOAL_BULK) and _promises_more(text):
        return "continue"
    if _relocate_goal(goal_s) and _claims_done(text) and not moved:
        return "continue"
    # ponytail: 잘린 목록 뒤의 파일 단위 이동은 전체가 아니다. 폴더 이동이 끝나면 멈춘다.
    if _relocate_goal(goal_s) and list_truncated and _claims_done(text) and not moved_folder:
        return "continue"
    if tool_ok_count == 0 and _wiki_save_goal(goal_s) and _claims_done(text):
        return "continue"
    # 파일 생성 + 도구 0 허위완료는 예전 continue(FILE_FOLLOWTHROUGH)였다.
    # VerifyTurn failover/명시실패가 맡기므로 여기선 stop.
    return "stop"


def _asks_choice(text: str) -> bool:
    if any(phrase in text for phrase in _ASK):
        return True
    return _OR_CHOICE.search(text) is not None


def _promises_more(text: str) -> bool:
    last = _last_sentence(text)
    return any(phrase in last for phrase in _CONTINUE)


def _last_sentence(text: str) -> str:
    parts = [part.strip() for part in re.split(r"[\n\r.!?。！？]+", text) if part.strip()]
    return parts[-1] if parts else ""


def _wiki_save_goal(goal: str) -> bool:
    from iris.knowledge.wiki_claim import wiki_work_goal

    return wiki_work_goal(goal)


def _relocate_goal(goal: str) -> bool:
    from iris.knowledge.wiki_claim import relocate_goal

    return relocate_goal(goal)


def _claims_done(text: str) -> bool:
    return any(phrase in text for phrase in _DONE)


def _check() -> None:
    goal = "웹사이트 모든 내용을 위키에 저장"
    assert (
        decide_followthrough(goal, "1강을 저장했습니다. 계속할까요?", 2, 0) == "continue"
    )
    assert decide_followthrough(goal, "67건 저장, 0건 실패", 1, 0) == "stop"
    assert decide_followthrough("오늘 날씨 알려줘", "서울은 맑습니다.", 0, 0) == "stop"
    assert decide_followthrough("위키에 저장", "어느 파일로 저장할까요?", 0, 0) == "ask"
    assert (
        decide_followthrough(goal, "1강을 저장했습니다. 계속할까요?", 2, 8) == "stop"
    )
    assert decide_followthrough("위키에 저장", "저장했습니다.", 0, 0) == "continue"
    assert (
        decide_followthrough(
            "원문은 남기고 위에 정리하고 문단은 한국어로",
            "정리했습니다.",
            0,
            0,
        )
        == "continue"
    )
    assert (
        decide_followthrough("정리된 위키를 열어", "열어 드리겠습니다.", 0, 0) == "continue"
    )
    assert decide_followthrough("오늘 날씨 알려줘", "정리했습니다.", 0, 0) == "stop"
    arrange = "학습자료 폴더를 만들고 강화학습으로 분류해서 저장"
    assert decide_followthrough(arrange, "분류했습니다.", 2, 0, moved=False) == "continue"
    assert decide_followthrough(arrange, "옮겼습니다.", 1, 0, moved=True) == "stop"
    assert (
        decide_followthrough(arrange, "분류했습니다.", 1, 0, moved=True, list_truncated=True)
        == "continue"
    )
    assert (
        decide_followthrough(
            arrange,
            "옮겼습니다.",
            1,
            0,
            moved=True,
            moved_folder=True,
            list_truncated=True,
        )
        == "stop"
    )
    assert counts_as_tool_ok("wiki.reprocess_note ok")
    assert not counts_as_tool_ok("wiki.reprocess_note completed")
    assert counts_as_tool_ok("wiki.write_user_note ok")
    assert counts_as_tool_ok("Iris control: wiki.write_user_note ok")
    assert counts_as_tool_ok("project.run ok")
    assert not counts_as_tool_ok("terminal ok")
    assert not counts_as_tool_ok("shell: python main.py ok")
    assert not counts_as_tool_ok("completed")
    assert not counts_as_tool_ok("tool running")
    assert (
        decide_followthrough(
            "5-1.py 스크립트 만들어줘",
            "5-1.py 를 생성했습니다. 처리 완료",
            0,
            0,
        )
        == "stop"
    )
    assert (
        decide_followthrough(
            "5-1.py 스크립트 만들어줘",
            "5-1.py 를 생성했습니다.",
            1,
            0,
        )
        == "stop"
    )
    assert decide_followthrough("오늘 날씨 알려줘", "생성했습니다.", 0, 0) == "stop"
    assert (
        decide_followthrough(
            "테트리스 코드 작성해줘",
            "코드는 작성을 완료했습니다.",
            0,
            0,
        )
        == "stop"
    )
    assert (
        decide_followthrough(
            "스크립트 만들어줘",
            "코드를 짰습니다.",
            0,
            0,
        )
        == "stop"
    )
    assert (
        decide_followthrough(
            "테트리스 코드 작성해줘",
            "",
            0,
            0,
        )
        == "stop"
    )
    print("turn_followthrough ok")


if __name__ == "__main__":
    _check()
