"""agent.log → Live Activity 필터·truncate 자검.

  .venv\\Scripts\\python.exe -m iris.runtime._check_agent_log_activity
"""

from __future__ import annotations

from pathlib import Path

from iris.runtime.agent_log_activity import (
    AGENT_LOG_MAX_CHARS,
    AgentLogTailer,
    classify_agent_log_line,
    default_agent_log_path,
    truncate_activity_line,
)


def _check() -> None:
    api = (
        "2026-10-28 01:58:19,787 INFO [20261028_015816_1cda48] "
        "agent.conversation_loop: API call #1: model=gemma4:31b-cloud "
        "provider=custom in=23747 out=6 total=23753 latency=2.6s id=chatcmpl-862"
    )
    tool_ok = (
        "2026-10-28 02:34:04,338 INFO [20261028_023401_b5f035] "
        "agent.tool_executor: tool tool_search completed (0.12s, 972 chars)"
    )
    tool_err = (
        "2026-10-28 14:41:48,409 WARNING [20261028_144142_be2dfb] "
        "agent.tool_executor: Tool write_file returned error (0.00s): "
        "{\"error\": \"write_file: missing required field 'path'.\"}"
    )
    turn = (
        "2026-10-28 01:58:19,820 INFO [20261028_015816_1cda48] "
        "agent.conversation_loop: Turn ended: reason=text_response(finish_reason=stop) "
        "model=gemma4:31b-cloud api_calls=1"
    )
    eof = (
        "2026-10-29 03:26:58,193 WARNING agent.chat_completion_helpers: "
        "Clean EOF, no finish_reason: server ended the stream "
        "(no transport exception) after delivering text with no tool calls."
    )
    noise_state = (
        "2026-10-28 01:57:23,529 WARNING hermes_state: state.db: linked SQLite "
        "3.50.4 is vulnerable to the WAL-reset corruption bug"
    )
    noise_gateway = (
        "2026-10-29 11:09:07,004 INFO gateway.run: Starting Hermes Gateway..."
    )
    noise_registry = (
        "2026-10-28 01:58:16,330 INFO tools.registry: check_fn "
        "check_discord_tool_requirements returned False; dependent tools "
        "will be unavailable this turn"
    )
    # conversation_loop INFO that is not API/Turn — reject
    noise_loop_info = (
        "2026-10-28 01:58:19,700 INFO [tag] agent.conversation_loop: "
        "warming caches for session"
    )

    got = classify_agent_log_line(api)
    assert got is not None and got.kind == "api"
    assert got.text.startswith("API call #1:")

    got = classify_agent_log_line(tool_ok)
    assert got is not None and got.kind == "tool"
    assert "tool_search completed" in got.text

    got = classify_agent_log_line(tool_err)
    assert got is not None and got.kind == "tool"
    assert "returned error" in got.text

    got = classify_agent_log_line(turn)
    assert got is not None and got.kind == "turn"
    assert got.text.startswith("Turn ended:")

    got = classify_agent_log_line(eof)
    assert got is not None and got.kind == "warn"
    assert "Clean EOF" in got.text

    for raw in (noise_state, noise_gateway, noise_registry, noise_loop_info):
        assert classify_agent_log_line(raw) is None, raw

    long = "x" * (AGENT_LOG_MAX_CHARS + 50)
    truncated = truncate_activity_line(long)
    assert len(truncated) == AGENT_LOG_MAX_CHARS
    assert truncated.endswith("…")

    path = default_agent_log_path()
    assert path.name == "agent.log"
    assert "logs" in path.parts

    # Tailer: only lines after reset_to_eof
    tmp = Path(__file__).resolve().parent / "_tmp_agent_log_activity.log"
    try:
        tmp.write_text(
            noise_gateway + "\n" + api + "\n",
            encoding="utf-8",
        )
        tailer = AgentLogTailer(tmp)
        tailer.reset_to_eof()
        with tmp.open("a", encoding="utf-8") as fh:
            fh.write(tool_ok + "\n")
            fh.write(noise_state + "\n")
            fh.write(turn + "\n")
        items = tailer.poll()
        kinds = [i.kind for i in items]
        assert kinds == ["tool", "turn"], kinds
        assert all(classify_agent_log_line(noise_state) is None for _ in (0,))
    finally:
        if tmp.exists():
            tmp.unlink()

    print("agent_log_activity ok", AGENT_LOG_MAX_CHARS, path)


if __name__ == "__main__":
    _check()
