"""Self-check: absorbed Hermes tool name → Iris Control action registry."""

from __future__ import annotations

from iris.infrastructure.absorbed_tool_aliases import (
    ABSORBED_TOOLS,
    AbsorbedTool,
    INTERNAL_ALIASES,
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

    # FRC-02 absorption of existing Speak/Control actions
    assert "skills_list" not in strip
    assert "skill_view" not in strip
    assert "vision_analyze" not in strip
    assert "skills_list" in model_names()
    assert "skill_view" in model_names()
    assert "vision_analyze" in model_names()
    assert resolve_action("skills_list", "home") == "skill.list"
    assert resolve_action("skill_view", "home") == "skill.view"
    assert resolve_action("vision_analyze", "home") == "vision.analyze_attachment"
    assert action_to_model_name("skill.list") == "skills_list"
    assert action_to_model_name("skill.view") == "skill_view"
    assert action_to_model_name("vision.analyze_attachment") == "vision_analyze"
    # FFC-03 Unit 4a: session_search / skill_manage absorbed
    assert "session_search" not in strip
    assert "skill_manage" not in strip
    assert "session_search" in model_names()
    assert "skill_manage" in model_names()
    assert resolve_action("session_search", "home") == "chat.search_past"
    assert resolve_action("skill_manage", "home") == "skill.manage"
    assert action_to_model_name("chat.search_past") == "session_search"
    assert action_to_model_name("skill.manage") == "skill_manage"
    # FFC-03 Unit 4b: todo_list → todo.manage
    assert "todo_list" not in strip
    assert "todo_list" in model_names()
    assert resolve_action("todo_list", "home") == "todo.manage"
    assert resolve_action("todo_list", "ide_companion") == "todo.manage"
    assert action_to_model_name("todo.manage") == "todo_list"
    # FFC-03 Unit 4c: clarify → clarify.manage
    assert "clarify" not in strip
    assert "clarify" in model_names()
    assert resolve_action("clarify", "home") == "clarify.manage"
    assert resolve_action("clarify", "ide_companion") == "clarify.manage"
    assert action_to_model_name("clarify.manage") == "clarify"
    # FFC-03 Unit 4d: delegate_task → delegate.manage
    assert "delegate_task" not in strip
    assert "delegate_task" in model_names()
    assert resolve_action("delegate_task", "home") == "delegate.manage"
    assert resolve_action("delegate_task", "ide_companion") == "delegate.manage"
    assert action_to_model_name("delegate.manage") == "delegate_task"
    # FFC-03 Unit 5: execute_code internal alias → terminal (no dual schema)
    assert INTERNAL_ALIASES.get("execute_code") == "terminal"
    assert "execute_code" not in strip
    assert "execute_code" not in model_names()
    assert resolve_action("execute_code", "home") == "shell.run"
    assert resolve_action("execute_code", "ide_companion") == "project.run"
    # FFC-03 Unit 5 residual absorbs
    assert "cronjob_manage" not in strip
    assert resolve_action("cronjob_manage", "home") == "routine.manage"
    assert action_to_model_name("routine.manage") == "cronjob_manage"
    assert "manage_connections" not in strip
    assert resolve_action("manage_connections", "home") == "connections.status"
    assert action_to_model_name("connections.status") == "manage_connections"
    assert "computer_use" not in strip
    assert resolve_action("computer_use", "home") == "computer.surfaces"
    assert action_to_model_name("computer.surfaces") == "computer_use"
    assert "image_generate" not in strip
    assert resolve_action("image_generate", "home") == "image.status"
    assert action_to_model_name("image.status") == "image_generate"
    assert "text_to_speech" not in strip
    assert resolve_action("text_to_speech", "home") == "voice.tts_status"
    assert action_to_model_name("voice.tts_status") == "text_to_speech"
    # memory umbrella intentionally strip; memory_* Speak grants remain
    assert "memory" in strip
    assert resolve_action("memory", "home") is None

    print("absorbed_tool_aliases ok")


if __name__ == "__main__":
    main()
