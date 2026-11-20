"""FM-NO-TOOLCALLS 자검 — SelectionGate + TurnNotice.

  .venv\\Scripts\\python.exe -m iris.ui._check_no_toolcalls_gate
"""

from __future__ import annotations

import inspect
from pathlib import Path

from iris.ui.chat import chat_panel as cp
from iris.ui.chat.no_toolcalls_gate import (
    NO_TOOLCALLS_NOTICE,
    SELECTION_BODY,
    SELECTION_HINT,
    selection_gate_copy,
    selection_gate_required,
    tool_intent_utterance,
    turn_notice,
)


ROOT = Path(__file__).resolve().parents[2]


def check_selection_gate_required() -> None:
    assert selection_gate_required(False) is True
    assert selection_gate_required(True) is False
    copy = selection_gate_copy()
    assert "도구" in copy["body"] and "동작하지 않습니다" in copy["body"]
    assert "도구가 필요" in copy["hint"]
    src = inspect.getsource(cp.ChatPanel._confirm_special_model)
    assert "selection_gate_required" in src
    assert "selection_gate_copy" in src
    panel_src = (ROOT / "iris" / "ui" / "chat" / "chat_panel.py").read_text(
        encoding="utf-8"
    )
    assert "selection_gate_required(supports_tools)" in panel_src
    assert SELECTION_BODY.split(".", 1)[0] in panel_src or "selection_gate_copy" in panel_src
    assert "파일·검색·위키 도구 불가" in panel_src


def check_turn_notice_tool_intent() -> None:
    assert tool_intent_utterance("5-1.py 만들어줘")
    assert tool_intent_utterance("이 스크립트 실행해줘")
    assert tool_intent_utterance("오늘 뉴스 검색해줘")
    assert tool_intent_utterance("이 링크 위키에 저장해줘")
    assert not tool_intent_utterance("안녕 오늘 기분 어때")

    claim = turn_notice(
        user="interpolation_test.py 생성해줘",
        tool_ok_count=0,
        supports_tools=True,
        tool_line_count=0,
    )
    assert claim == NO_TOOLCALLS_NOTICE

    assert (
        turn_notice(
            user="파일 만들어줘",
            tool_ok_count=0,
            supports_tools=False,
            tool_line_count=0,
        )
        is None
    )
    assert (
        turn_notice(
            user="파일 만들어줘",
            tool_ok_count=1,
            supports_tools=True,
            tool_line_count=1,
        )
        is None
    )
    assert (
        turn_notice(
            user="그냥 설명해줘",
            tool_ok_count=0,
            supports_tools=True,
            tool_line_count=0,
        )
        is None
    )
    # unknown(None) → TurnNotice 대상
    assert (
        turn_notice(
            user="웹 검색해줘",
            tool_ok_count=0,
            supports_tools=None,
            tool_line_count=0,
        )
        == NO_TOOLCALLS_NOTICE
    )


def check_wiki_grounding_passthrough() -> None:
    """위키 settle / answer_grounding 본문 게이트를 되살리지 않음."""
    from iris.ui.chat.file_write_claim import settle_completion_claim

    wiki_ok = "위키에 저장했습니다. 노트 경로를 확인하세요."
    gate = settle_completion_claim(wiki_ok, verified_path="")
    # 파일 CLAIM_RE 가 아니면 원문 통과 (광역 completion gate 금지)
    assert gate.display == wiki_ok
    assert NO_TOOLCALLS_NOTICE not in gate.display

    mw = (ROOT / "iris" / "ui" / "window" / "main_window.py").read_text(encoding="utf-8")
    assert "no_toolcalls_gate" in mw and "turn_notice" in mw
    assert "append_note(notice)" in mw
    # settle_wiki / answer_grounding 을 turn_notice 로 가로채지 않음
    assert "settle_wiki" not in Path(
        ROOT / "iris" / "ui" / "chat" / "no_toolcalls_gate.py"
    ).read_text(encoding="utf-8")


def main() -> int:
    check_selection_gate_required()
    check_turn_notice_tool_intent()
    check_wiki_grounding_passthrough()
    # SELECTION_HINT 가 제품에 남는지 (카피 강화 증거)
    assert "파일/위키" in SELECTION_HINT or "MCP" in SELECTION_HINT
    print("no_toolcalls_gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
