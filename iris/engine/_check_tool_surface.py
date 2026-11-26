"""Iris eager tool surface keeps terminal visible and defers search_files."""

from __future__ import annotations

from iris.engine.tool_surface import (
    IRIS_EAGER_MODEL_TOOLS,
    assemble_iris_model_tools,
    dispatch_iris_bridge,
)


def main() -> None:
    assert "terminal" in IRIS_EAGER_MODEL_TOOLS
    assert "search_files" not in IRIS_EAGER_MODEL_TOOLS

    def schema(name: str, summary: str = "") -> dict:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": summary or name,
                "parameters": {"type": "object", "properties": {}},
            },
        }

    tools = [
        schema("terminal", "shell"),
        schema("search_files", "find files by name"),
        schema("write_file", "write"),
        schema("browser_navigate", "open url"),
    ]
    visible, deferred, activated = assemble_iris_model_tools(tools, context_length=64000)
    names = {
        str((row.get("function") or {}).get("name") or "")
        for row in visible
        if isinstance(row, dict)
    }
    deferred_names = {
        str((row.get("function") or {}).get("name") or "")
        for row in deferred
        if isinstance(row, dict)
    }
    assert activated is True, (activated, names)
    assert "terminal" in names
    assert "write_file" in names
    assert "search_files" not in names
    assert "search_files" in deferred_names
    assert "browser_navigate" in deferred_names
    assert {"tool_search", "tool_describe", "tool_call"} <= names
    found = dispatch_iris_bridge(
        "tool_search",
        {"queries": ["search files"]},
        deferred_defs=deferred,
    )
    assert found is not None and "search_files" in found, found
    print("tool_surface ok", f"visible={len(names)}", f"deferred={len(deferred_names)}")


if __name__ == "__main__":
    main()
