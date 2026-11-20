"""agent_tool_activity_footer 결정표 자검.

  .venv\\Scripts\\python.exe -m iris.runtime._check_agent_tool_activity
"""

from __future__ import annotations

from iris.runtime.agent_tool_activity import agent_tool_activity_footer


def _check() -> None:
    assert agent_tool_activity_footer(tool_line_count=1, attachment_count=0) is None
    assert agent_tool_activity_footer(tool_line_count=2, attachment_count=3) is None
    assert (
        agent_tool_activity_footer(tool_line_count=0, attachment_count=2)
        == "도구 호출 없음 · 첨부 2건은 컨텍스트로 전달됨"
    )
    assert (
        agent_tool_activity_footer(tool_line_count=0, attachment_count=0)
        == "도구 호출 없음"
    )
    print("agent_tool_activity: ok")


if __name__ == "__main__":
    _check()
