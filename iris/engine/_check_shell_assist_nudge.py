"""Self-check: shell assist nudge fires once on ok shell, skips failures, appends hint.

Run: .venv\\Scripts\\python.exe -m iris.engine._check_shell_assist_nudge
"""

from __future__ import annotations

from iris.engine.diagram_tool_nudge import append_hint_to_last_tool_result
from iris.engine.shell_assist_nudge import HINT, ShellAssistNudge, looks_like_shell_assist_target


def _main() -> None:
    ok_result = {
        "ok": True,
        "action": "shell.run",
        "data": {
            "exit_code": 0,
            "stdout": "IRIS_ACF_DEADBEEF\n",
            "stderr": "",
        },
    }
    fail_result = {
        "ok": False,
        "error": "exit 1",
        "data": {"exit_code": 1, "stdout": "", "stderr": "boom"},
    }
    empty_ok = {"ok": True, "data": {"exit_code": 0, "stdout": "", "stderr": ""}}

    assert looks_like_shell_assist_target("terminal", ok_result)
    assert looks_like_shell_assist_target("shell.run", ok_result)
    assert not looks_like_shell_assist_target("read_file", ok_result)
    assert not looks_like_shell_assist_target("terminal", fail_result)
    assert not looks_like_shell_assist_target("terminal", empty_ok)

    nudge = ShellAssistNudge()
    assert HINT in nudge.observe("terminal", {"command": "echo IRIS_ACF_DEADBEEF"}, ok_result)
    assert nudge.fired is True
    assert nudge.observe("shell.run", {"command": "echo again"}, ok_result) == ""

    skip = ShellAssistNudge()
    assert skip.observe("terminal", {"command": "bad"}, fail_result) == ""
    assert skip.fired is False

    agent = type(
        "A",
        (),
        {
            "_session_messages": [
                {
                    "role": "tool",
                    "content": '{"ok": true, "data": {"stdout": "IRIS_ACF_DEADBEEF"}}',
                }
            ]
        },
    )()
    assert append_hint_to_last_tool_result(agent, HINT) is True
    assert HINT in agent._session_messages[0]["content"]
    assert append_hint_to_last_tool_result(agent, HINT) is False

    print("shell assist nudge ok")


if __name__ == "__main__":
    _main()
