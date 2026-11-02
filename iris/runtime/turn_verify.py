"""채팅 턴 종료 VerifyTurn — 파일 허위완료·로컬쓰기·failover 한 진입점."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from iris.runtime.tool_force import honesty_rejects_side_effect_success
from iris.ui.chat.file_write_claim import (
    CHAT_ONLY,
    LocalWritePlan,
    file_create_goal,
    plan_local_file_writes,
    settle_completion_claim,
    turn_write_evidence,
)

VerifyAction = Literal["display", "ask", "local_write", "failover", "stop"]

FILE_CREATE_EXPLICIT_FAIL = (
    "도구로 파일을 만들지 못했다. 모델을 바꾸거나 파일 이름을 지정해 다시 요청하라"
)
SIDE_EFFECT_EXPLICIT_FAIL = (
    "도구로 실행·설치를 끝내지 못했다. 다시 요청하거나 모델을 바꿔라"
)


@dataclass(frozen=True)
class TurnEvidence:
    tool_ok_count: int
    tool_written: bool
    verified_path: str
    content_match: bool | None
    empty_reply: bool
    assistant: str
    goal: str
    exit_tool_seen: bool = False


@dataclass(frozen=True)
class VerifyResult:
    display: str
    actions: tuple[VerifyAction, ...]
    suppress_voice_followup: bool
    local_plan: LocalWritePlan | None = None
    suppress_followthrough: bool = False


def verify_file_create_turn(
    evidence: TurnEvidence,
    *,
    plan_local_write_fn: Callable[[str, str], LocalWritePlan] | None = None,
    failover_available: bool = False,
) -> VerifyResult:
    """파일 생성 턴의 표시·ask·local_write·failover 결정을 한곳에서 낸다.

    content_match=False 는 디스크 증거 없음과 같다.
    empty_reply|CHAT_ONLY + file goal + tool_ok==0 이고 local_write/ask 가 없으면
    failover(가능 시) 또는 명시 실패. FILE_FOLLOWTHROUGH continue 보다 우선.
    """
    plan_fn = plan_local_write_fn or plan_local_file_writes
    wrote_ev = turn_write_evidence(
        verified_path=evidence.verified_path,
        tool_written=evidence.tool_written,
        content_match=evidence.content_match,
    )
    actions: list[VerifyAction] = []
    local_plan: LocalWritePlan | None = None
    if not wrote_ev.wrote:
        planned = plan_fn(evidence.goal, evidence.assistant)
        if planned.kind == "write":
            local_plan = planned
            actions.append("local_write")
        elif planned.kind == "ask":
            local_plan = planned
            actions.append("ask")
    gate = settle_completion_claim(
        evidence.assistant,
        verified_path=wrote_ev.verified_path,
        wrote=wrote_ev.wrote,
        content_match=evidence.content_match,
    )
    display = gate.display
    suppress_voice = gate.suppress_followup_write
    suppress_ft = False
    chat_only = CHAT_ONLY in (display or "")
    file_goal = file_create_goal(evidence.goal).matched
    # Policy A: on_disk / tool_written evidence means the file exists — not CHAT_ONLY-as-missing.
    needs_recovery = (
        file_goal
        and not wrote_ev.wrote
        and int(evidence.tool_ok_count or 0) == 0
        and (bool(evidence.empty_reply) or chat_only)
        and "local_write" not in actions
        and "ask" not in actions
    )
    # ToolForce honesty: side-effect (create/run/install) + exit_tool only → not success.
    side_effect_reject = honesty_rejects_side_effect_success(
        goal=evidence.goal,
        tool_ok_count=int(evidence.tool_ok_count or 0),
        exit_tool_seen=bool(evidence.exit_tool_seen),
        display=display or "",
    ) and "local_write" not in actions and "ask" not in actions
    if needs_recovery or side_effect_reject:
        suppress_ft = True
        suppress_voice = True
        if failover_available and (needs_recovery or file_goal):
            actions.append("failover")
        else:
            actions.append("stop")
            fail_line = (
                FILE_CREATE_EXPLICIT_FAIL
                if file_goal
                else SIDE_EFFECT_EXPLICIT_FAIL
            )
            if fail_line not in (display or ""):
                display = (
                    fail_line
                    if not (display or "").strip()
                    else display.rstrip() + "\n\n" + fail_line
                )
    actions.append("display")
    return VerifyResult(
        display=display,
        actions=tuple(actions),
        suppress_voice_followup=suppress_voice,
        local_plan=local_plan,
        suppress_followthrough=suppress_ft,
    )
