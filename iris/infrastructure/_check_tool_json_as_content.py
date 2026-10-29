"""Fail-closed: tool-call shaped assistant text must not become final chat content.

Measured 2026-10-29 chat_messages id=895 (Hermes session 20261029_031906_0925ef).
Run: .venv\\Scripts\\python.exe -m iris.infrastructure._check_tool_json_as_content
"""

from __future__ import annotations

from iris.infrastructure.hermes_client import (
    _looks_like_tool_args_json,
    _should_emit_assistant_content,
)

# Exact shape persisted as assistant (id 895): [[obj] with one missing ']'.
MEASURED = (
    '[[\n{"name": "read_file", "parameters": {"path": "tetris_game.py"}}\n]'
)
# Well-formed double-list wrapper (also seen in Hermes tool prose).
MEASURED_BALANCED = (
    '[[\n{"name": "read_file", "parameters": {"path": "tetris_game.py"}}\n]]'
)
NAME_PARAMS = '{"name": "read_file", "parameters": {"path": "tetris_game.py"}}'
LEGACY_TOOLISH = (
    '{"file_glob":"**/node_modules/typescript","path":"C:/Users/kwakm","target":"files"}'
)
PLAIN_ANSWER = '{"answer":"yes"}'
CONTENT_PARTS_JOIN = "".join([MEASURED])


def main() -> None:
    choice_stop = {"delta": {"content": MEASURED}, "finish_reason": "stop"}

    assert _looks_like_tool_args_json(MEASURED), "malformed [[...]] wrapper must be detected"
    assert _looks_like_tool_args_json(MEASURED_BALANCED), "balanced [[...]] must be detected"
    assert _looks_like_tool_args_json(NAME_PARAMS), "name/parameters shape must be detected"
    assert _looks_like_tool_args_json(LEGACY_TOOLISH), "legacy toolish keys still detected"
    assert not _looks_like_tool_args_json(PLAIN_ANSWER), "plain answer JSON must still emit"

    assert not _should_emit_assistant_content(MEASURED, choice_stop), (
        "stream must suppress measured tool-call blob"
    )
    assert not _should_emit_assistant_content(MEASURED_BALANCED, choice_stop), (
        "stream must suppress balanced wrapper"
    )
    assert not _should_emit_assistant_content(NAME_PARAMS, choice_stop), (
        "stream must suppress name/parameters object"
    )
    assert not _should_emit_assistant_content(CONTENT_PARTS_JOIN, choice_stop), (
        "worker join of measured blob must not emit"
    )
    assert _should_emit_assistant_content(PLAIN_ANSWER, choice_stop), (
        "plain answer JSON must still emit"
    )
    print("ok — detector blocks tool-call JSON content")


if __name__ == "__main__":
    main()
