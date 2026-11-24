"""Self-check: absorbed Hermes tool name → Iris Control action registry."""

from __future__ import annotations

from iris.infrastructure.absorbed_tool_aliases import (
    ABSORBED_TOOLS,
    AbsorbedTool,
    action_to_model_name,
    model_names,
    resolve_action,
    strip_only_names,
)

_SURFACES = ("home", "ide_companion")


def main() -> None:
    names = [t.model_name for t in ABSORBED_TOOLS]
    assert len(names) == len(set(names)), names
    assert all("." not in n for n in names), names
    assert model_names() == frozenset(names)

    for tool in ABSORBED_TOOLS:
        assert isinstance(tool, AbsorbedTool)
        has_route = bool(tool.action) or bool(tool.by_surface)
        assert has_route, tool
        for surface in _SURFACES:
            resolved = resolve_action(tool.model_name, surface)
            assert resolved, (tool.model_name, surface, resolved)
            assert "." in resolved, resolved

    home_term = resolve_action("terminal", "home")
    ide_term = resolve_action("terminal", "ide_companion")
    assert home_term == "shell.run", home_term
    assert ide_term == "project.run", ide_term
    assert home_term != ide_term

    assert resolve_action("write_file", "home") == "project.write_file"
    assert resolve_action("write_file", "ide_companion") == "project.write_file"
    assert resolve_action("read_file", "home") == "project.read_file"
    assert resolve_action("search_files", "home") == "local.search_files"
    assert resolve_action("web_search", "home") == "web.run_search"
    assert resolve_action("web_extract", "home") == "web.run_extract"

    assert action_to_model_name("shell.run") == "terminal"
    assert action_to_model_name("project.run") == "terminal"
    assert action_to_model_name("project.write_file") == "write_file"
    assert action_to_model_name("local.search_files") == "search_files"
    assert action_to_model_name("no.such") is None

    strip = strip_only_names()
    assert "process_manage" not in strip
    assert "process_manage" in model_names()
    assert resolve_action("process_manage", "home") == "process.manage"
    assert resolve_action("process_manage", "ide_companion") == "process.manage"
    assert action_to_model_name("process.manage") == "process_manage"
    assert "patch" not in strip
    assert "apply_patch" in model_names()
    assert "patch" not in model_names()
    assert resolve_action("apply_patch", "home") == "project.apply_patch"
    assert resolve_action("patch", "home") == "project.apply_patch"
    assert action_to_model_name("project.apply_patch") == "apply_patch"
    assert resolve_action("unknown_tool", "home") is None

    print("absorbed_tool_aliases ok")


if __name__ == "__main__":
    main()
