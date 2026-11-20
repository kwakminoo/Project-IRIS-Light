"""Tool progress callbacks become one branded line, or no line.

Run: .venv\\Scripts\\python.exe -m iris.engine._check_tool_use_line
"""

from __future__ import annotations

from iris.engine import _sidecar_main as sidecar
from iris.runtime.tool_force import tool_activity


def main() -> None:
    assert sidecar.tool_use_label("tool.started", "read_file") == "[IRIS tool use: read_file]"
    assert sidecar.tool_use_label("tool.completed", "read_file") == "[IRIS tool use: read_file]"
    assert sidecar.tool_use_label("tool.progress", "read_file") == "[IRIS tool use: read_file]"
    assert sidecar.tool_use_label("reasoning.available", "_thinking") is None
    assert sidecar.tool_use_label("tool.started", "tool.started") is None
    assert sidecar.tool_use_label("tool.started", "") is None

    emitted: list[dict] = []
    original = sidecar._emit
    sidecar._emit = emitted.append
    try:
        sidecar._on_tool("tool.started", "read_file", "preview", {})
        sidecar._on_tool("tool.started", "")
    finally:
        sidecar._emit = original
    assert emitted == [{"t": "tool", "label": "[IRIS tool use: read_file]"}]

    sidecar._reasoning_streamed = False
    sidecar._emit = emitted.append
    emitted.clear()
    try:
        sidecar._on_tool("reasoning.available", "_thinking", "hidden thought")
        sidecar._on_reasoning("full thought")
        sidecar._on_tool("reasoning.available", "_thinking", "x" * 600)
    finally:
        sidecar._emit = original
        sidecar._reasoning_streamed = False
    assert emitted == [
        {"t": "think", "text": "hidden thought"},
        {"t": "think", "text": "full thought"},
    ]

    preview = "y" * 600
    sidecar._reasoning_streamed = False
    sidecar._emit = emitted.append
    emitted.clear()
    try:
        sidecar._on_tool("reasoning.available", "_thinking", preview)
    finally:
        sidecar._emit = original
        sidecar._reasoning_streamed = False
    assert emitted == [{"t": "think", "text": preview}]

    respond = tool_activity("[IRIS tool use: respond]")
    assert respond is not None
    assert respond.name == "respond"
    assert respond.exit_tool
    assert not respond.count_ok
    assert respond.record == "respond ok"
    read = tool_activity("[IRIS tool use: read_file]")
    assert read is not None
    assert read.name == "read_file"
    assert not read.exit_tool
    assert not read.count_ok
    chat_only = tool_activity("[IRIS tool use: chat_only]")
    assert chat_only is not None
    assert chat_only.exit_tool
    assert not chat_only.count_ok
    plain = tool_activity("project.run ok")
    assert plain is not None
    assert plain.count_ok
    assert plain.record == "project.run ok"
    print("tool use line ok")


if __name__ == "__main__":
    main()
