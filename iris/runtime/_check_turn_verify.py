"""VerifyTurn 골격 자검.

  .venv\\Scripts\\python.exe -m iris.runtime._check_turn_verify
"""

from __future__ import annotations

import inspect

from iris.runtime.turn_verify import (
    FILE_CREATE_EXPLICIT_FAIL,
    TurnEvidence,
    verify_file_create_turn,
)
from iris.ui.chat.file_write_claim import CHAT_ONLY
from iris.ui.window import main_window as mw


def _ev(**kwargs) -> TurnEvidence:
    base = dict(
        tool_ok_count=0,
        tool_written=False,
        verified_path="",
        content_match=None,
        empty_reply=False,
        assistant="",
        goal="",
    )
    base.update(kwargs)
    return TurnEvidence(**base)


def _check() -> None:
    soft = verify_file_create_turn(
        _ev(
            assistant="코드는 작성을 완료했습니다. 파일 이름은 tetris_king.py 입니다.",
            goal="테트리스킹 코드 작성해줘",
        )
    )
    assert CHAT_ONLY in soft.display
    assert FILE_CREATE_EXPLICIT_FAIL in soft.display
    assert "display" in soft.actions
    assert "stop" in soft.actions
    assert "failover" not in soft.actions
    assert soft.suppress_voice_followup
    assert soft.suppress_followthrough

    soft_failover = verify_file_create_turn(
        _ev(
            assistant="코드는 작성을 완료했습니다. 파일 이름은 tetris_king.py 입니다.",
            goal="테트리스킹 코드 작성해줘",
        ),
        failover_available=True,
    )
    assert CHAT_ONLY in soft_failover.display
    assert FILE_CREATE_EXPLICIT_FAIL not in soft_failover.display
    assert "failover" in soft_failover.actions
    assert "stop" not in soft_failover.actions
    assert soft_failover.suppress_followthrough

    empty_fail = verify_file_create_turn(
        _ev(
            empty_reply=True,
            assistant="",
            goal="테트리스 코드 작성해줘",
        )
    )
    assert empty_fail.display == FILE_CREATE_EXPLICIT_FAIL
    assert "stop" in empty_fail.actions
    assert empty_fail.suppress_followthrough

    empty_failover = verify_file_create_turn(
        _ev(
            empty_reply=True,
            assistant="",
            goal="테트리스 코드 작성해줘",
        ),
        failover_available=True,
    )
    assert "failover" in empty_failover.actions
    assert empty_failover.suppress_followthrough
    assert not (empty_failover.display or "").strip()

    planned = verify_file_create_turn(
        _ev(
            assistant="tetris_king.py\n```python\nprint(1)\n```",
            goal="테트리스킹 코드 작성한 다음에 실행해줘",
        )
    )
    assert "local_write" in planned.actions
    assert "failover" not in planned.actions
    assert "stop" not in planned.actions
    assert not planned.suppress_followthrough
    assert planned.local_plan is not None
    assert planned.local_plan.kind == "write"
    assert planned.local_plan.pairs[0][0] == "tetris_king.py"

    evidenced = verify_file_create_turn(
        _ev(
            tool_ok_count=1,
            tool_written=True,
            assistant="코드는 작성을 완료했습니다.",
            goal="스크립트 만들어줘",
        )
    )
    assert CHAT_ONLY not in evidenced.display
    assert "local_write" not in evidenced.actions
    assert "failover" not in evidenced.actions
    assert not evidenced.suppress_followthrough

    mismatch = verify_file_create_turn(
        _ev(
            tool_ok_count=1,
            tool_written=True,
            content_match=False,
            assistant="코드는 작성을 완료했습니다.",
            goal="스크립트 만들어줘",
        )
    )
    assert CHAT_ONLY in mismatch.display
    assert "local_write" in mismatch.actions or "ask" in mismatch.actions or "display" in mismatch.actions

    weather = verify_file_create_turn(
        _ev(
            empty_reply=True,
            assistant="",
            goal="오늘 날씨 알려줘",
        )
    )
    assert "failover" not in weather.actions
    assert "stop" not in weather.actions
    assert not weather.suppress_followthrough

    src = inspect.getsource(mw.MainWindow._on_chat_finished)
    assert "_run_file_create_verify_turn" in src
    assert "_fire_file_create_failover" in src or "failover" in src
    assert "_file_create_failover_available" in inspect.getsource(mw.MainWindow)
    print("turn_verify ok")


if __name__ == "__main__":
    _check()
