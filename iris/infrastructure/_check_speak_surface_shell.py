"""TDD: IDE Companion hard-hides shell.run from SpeakTools / engine schemas.

When model_tool_names catalog is active, home also hides shell_run from the
model list while PHASE4 keeps the grant for Control / adapters. project.run
is likewise hidden from model schemas (terminal covers it) but invoke stays.
"""

from __future__ import annotations

from iris.engine.model_tool_names import catalog_uses_model_tool_names
from iris.infrastructure.tool_capability import (
    PHASE4_ALLOWLIST,
    current_speak_surface,
    default_agent_tools,
    engine_tool_name,
    engine_tool_schemas,
    set_speak_surface,
)


def _schema_names() -> set[str]:
    return {str(row["name"]) for row in engine_tool_schemas()}


def _catalog_names() -> set[str]:
    return {row.name for row in default_agent_tools().catalog()}


def main() -> None:
    set_speak_surface("home")
    assert current_speak_surface() == "home"
    assert PHASE4_ALLOWLIST.grant("shell.run") is not None
    assert "shell.run" in PHASE4_ALLOWLIST.names()
    folded = catalog_uses_model_tool_names()
    if folded:
        assert engine_tool_name("shell.run") not in _schema_names()
        assert "shell.run" not in _catalog_names()
    else:
        assert engine_tool_name("shell.run") in _schema_names()
        assert "shell.run" in _catalog_names()

    set_speak_surface("ide_companion")
    assert current_speak_surface() == "ide_companion"
    names = _schema_names()
    assert engine_tool_name("shell.run") not in names, names
    assert "shell_run" not in names
    catalog = _catalog_names()
    assert "shell.run" not in catalog, catalog
    if folded:
        assert "project.run" not in catalog, catalog
        assert PHASE4_ALLOWLIST.grant("project.run") is not None
    else:
        assert "project.run" in catalog
    hidden = default_agent_tools().invoke("shell.run", {"command": "echo nope"})
    assert hidden.ok is False, hidden
    assert "not_allowed" in (hidden.error or ""), hidden

    set_speak_surface("home")
    assert current_speak_surface() == "home"
    # Grant always; model schema only when hide_from_model is off.
    assert PHASE4_ALLOWLIST.grant("shell.run") is not None
    if folded:
        assert engine_tool_name("shell.run") not in _schema_names()
        assert "shell.run" not in _catalog_names()
    else:
        assert engine_tool_name("shell.run") in _schema_names()
        assert "shell.run" in _catalog_names()
    print("speak_surface_shell ok", f"hide_from_model={folded}")


if __name__ == "__main__":
    main()
