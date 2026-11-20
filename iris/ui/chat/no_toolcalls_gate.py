"""FM-NO-TOOLCALLS — SelectionGate + TurnNotice (도구 미지원·미발화).

SelectionGate: supports_tools=false 피커 확정 전 HUD.
TurnNotice: 도구 가능(또는 unknown) 모델인데 tool-intent 턴에 tool_ok==0 이면
채팅 note 한 줄. 위키/검색 answer_grounding 본문 게이트는 건드리지 않는다.
"""

from __future__ import annotations

import re

from iris.runtime.tool_force import side_effect_goal

# SelectionGate copy (picker confirm)
SELECTION_TITLE = "도구 호출 미지원"
SELECTION_BADGE = "NO TOOLS"
SELECTION_BODY = (
    "이 모델은 도구 호출을 지원하지 않습니다. "
    "파일 쓰기·실행·검색·위키 도구가 동작하지 않습니다."
)
SELECTION_HINT = (
    "에이전트 사용(웹검색·스킬·MCP·파일/위키)에 도구가 필요합니다. "
    "그래도 선택하시겠습니까?"
)

# TurnNotice — LiveActivity footer 와 동일 카피, 채팅 note 로 고정
NO_TOOLCALLS_NOTICE = "도구 호출 없음"

# side_effect_goal(파일·실행) 밖: 검색·위키 도구 의도만 (본문 settle 아님)
_SEARCH_WIKI_RE = re.compile(
    r"검색|찾아\s*줘|찾아줘|search\b|웹.?검색|"
    r"위키에\s*저장|위키\s*저장|wiki\.(?:save|import|write)|스크랩",
    re.I,
)


def selection_gate_required(supports_tools: bool) -> bool:
    """supports_tools=false 이면 피커 confirm 필수."""
    return not bool(supports_tools)


def selection_gate_copy() -> dict[str, str]:
    return {
        "title": SELECTION_TITLE,
        "badge": SELECTION_BADGE,
        "body": SELECTION_BODY,
        "hint": SELECTION_HINT,
    }


def tool_intent_utterance(text: str) -> bool:
    """파일 쓰기·실행·검색·위키 도구 동사가 보이면 True."""
    goal = text or ""
    if side_effect_goal(goal):
        return True
    return bool(_SEARCH_WIKI_RE.search(goal))


def turn_notice(
    *,
    user: str,
    tool_ok_count: int,
    supports_tools: bool | None = True,
    tool_line_count: int | None = None,
) -> str | None:
    """tool-intent + 도구 미발화(또는 ok 0)이면 durable 한 줄. 미지원 모델은 None.

    supports_tools False 는 SelectionGate 영역 — TurnNotice 생략.
    None/True(unknown·지원) 만 대상.
    """
    if supports_tools is False:
        return None
    if tool_line_count is not None and int(tool_line_count) > 0:
        return None
    if int(tool_ok_count or 0) > 0:
        return None
    if not tool_intent_utterance(user):
        return None
    return NO_TOOLCALLS_NOTICE
