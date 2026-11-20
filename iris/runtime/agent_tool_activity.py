"""Agent 턴 종료 Live Activity 푸터 (도구 줄 vs 첨부 컨텍스트).

tool_progress 줄과 첨부 ingest를 구분한다. UX 카피만 만든다.
"""

from __future__ import annotations


def agent_tool_activity_footer(*, tool_line_count: int, attachment_count: int) -> str | None:
    """도구 줄이 있으면 None. 없으면 첨부 유무에 따른 한 줄."""
    if tool_line_count > 0:
        return None
    if attachment_count > 0:
        return f"도구 호출 없음 · 첨부 {attachment_count}건은 컨텍스트로 전달됨"
    return "도구 호출 없음"
