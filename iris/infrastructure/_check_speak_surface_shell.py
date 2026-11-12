"""TDD: IDE Companion hard-hides shell.run from SpeakTools / engine schemas."""

from __future__ import annotations

from iris.infrastructure.speak_capability import (
    PHASE4_ALLOWLIST,
    current_speak_surface,
    default_speak_tools,
    engine_tool_name,
    engine_tool_schemas,
    set_speak_surface,
)


def _schema_names() -> set[str]:
    return {str(row["name"]) for row in engine_tool_schemas()}


def _catalog_names() -> set[str]:
    return {row.name for row in default_speak_tools().catalog()}


def main() -> None:
    set_speak_surface("home")
    assert current_speak_surface() == "home"
    assert PHASE4_ALLOWLIST.grant("shell.run") is not None
    assert "shell.run" in PHASE4_ALLOWLIST.names()
    assert engine_tool_name("shell.run") in _schema_names()
    assert "shell.run" in _catalog_names()

    set_speak_surface("ide_companion")
    assert current_speak_surface() == "ide_companion"
    names = _schema_names()
    assert engine_tool_name("shell.run") not in names, names
    assert "shell_run" not in names
    catalog = _catalog_names()
    assert "shell.run" not in catalog, catalog
    assert "project.run" in catalog
    hidden = default_speak_tools().invoke("shell.run", {"command": "echo nope"})
    assert hidden.ok is False, hidden
    assert "not_allowed" in (hidden.error or ""), hidden

    set_speak_surface("home")
    assert current_speak_surface() == "home"
    assert engine_tool_name("shell.run") in _schema_names()
    assert "shell.run" in _catalog_names()
    print("speak_surface_shell ok")


if __name__ == "__main__":
    main()
