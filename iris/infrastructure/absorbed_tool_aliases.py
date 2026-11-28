"""Hermes model tool names → Iris Control actions (domain registry).

One familiar name for the model; Iris resolves the Control action by
fixed id or by speak surface (home vs ide_companion).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

# Hermes tool names with no Iris Control replacement (strip from schemas only).
# skills_list / skill_view / vision_analyze absorbed (FRC-02);
# session_search / skill_manage absorbed (FFC-03 Unit 4a);
# todo_list absorbed (FFC-03 Unit 4b → todo.manage);
# clarify absorbed (FFC-03 Unit 4c → clarify.manage);
# delegate_task absorbed (FFC-03 Unit 4d → delegate.manage);
# execute_code / cronjob_manage / manage_connections / computer_use /
# image_generate / text_to_speech absorbed (FFC-03 Unit 5).
# memory umbrella stays strip on purpose: FFC-02 already exposes
# memory.search/save/update/delete as Speak; do not re-emit Hermes `memory`.
STRIP_ONLY_NAMES: frozenset[str] = frozenset(
    {
        "memory",
    }
)

# Hermes names that resolve to an absorbed model name but are NOT schema-emitted.
# ``patch`` → ``apply_patch`` (one schema; no dual write_file/apply_patch style exposure).
# ``execute_code`` → ``terminal`` (shell/IDE path; no inline code executor, no dual schema).
INTERNAL_ALIASES: Mapping[str, str] = {
    "patch": "apply_patch",
    "execute_code": "terminal",
}


@dataclass(frozen=True)
class AbsorbedTool:
    model_name: str  # e.g. "terminal", "write_file" — what the model sees
    action: str | None = None  # fixed Control action id, or None if surface-routed
    by_surface: Mapping[str, str] | None = None  # surface → Control action


ABSORBED_TOOLS: tuple[AbsorbedTool, ...] = (
    AbsorbedTool(
        "terminal",
        by_surface={"home": "shell.run", "ide_companion": "project.run"},
    ),
    AbsorbedTool("process_manage", action="process.manage"),
    AbsorbedTool("write_file", action="project.write_file"),
    AbsorbedTool("read_file", action="project.read_file"),
    AbsorbedTool("search_files", action="local.search_files"),
    AbsorbedTool("apply_patch", action="project.apply_patch"),
    AbsorbedTool("web_search", action="web.run_search"),
    AbsorbedTool("web_extract", action="web.run_extract"),
    # FRC-02: Hermes familiar names → existing Speak/Control actions (no new surface).
    AbsorbedTool("skills_list", action="skill.list"),
    AbsorbedTool("skill_view", action="skill.view"),
    AbsorbedTool("vision_analyze", action="vision.analyze_attachment"),
    # FFC-03 Unit 4a: absorb names that already have Speak/Control.
    AbsorbedTool("session_search", action="chat.search_past"),
    AbsorbedTool("skill_manage", action="skill.manage"),
    # FFC-03 Unit 4b: Hermes todo_list → host-attested todo.manage.
    AbsorbedTool("todo_list", action="todo.manage"),
    # FFC-03 Unit 4c: Hermes clarify → host ClarifyWait (resume yields ResumeTicket).
    AbsorbedTool("clarify", action="clarify.manage"),
    # FFC-03 Unit 4d: Hermes delegate_task → host DelegateSession (Engine.fork).
    AbsorbedTool("delegate_task", action="delegate.manage"),
    # FFC-03 Unit 5: residual honest absorbs (status / dispatcher / no fake payloads).
    AbsorbedTool("cronjob_manage", action="routine.manage"),
    AbsorbedTool("manage_connections", action="connections.status"),
    AbsorbedTool("computer_use", action="computer.surfaces"),
    AbsorbedTool("image_generate", action="image.status"),
    AbsorbedTool("text_to_speech", action="voice.tts_status"),
)


def model_names() -> frozenset[str]:
    return frozenset(t.model_name for t in ABSORBED_TOOLS)


def strip_only_names() -> frozenset[str]:
    return STRIP_ONLY_NAMES


def resolve_action(model_name: str, surface: str) -> str | None:
    name = (model_name or "").strip()
    name = INTERNAL_ALIASES.get(name, name)
    if not name or name in STRIP_ONLY_NAMES:
        return None
    for tool in ABSORBED_TOOLS:
        if tool.model_name != name:
            continue
        if tool.action:
            return tool.action
        if tool.by_surface:
            return tool.by_surface.get(surface) or None
        return None
    return None


def action_to_model_name(action: str) -> str | None:
    act = (action or "").strip()
    if not act:
        return None
    for tool in ABSORBED_TOOLS:
        if tool.action == act:
            return tool.model_name
        if tool.by_surface and act in tool.by_surface.values():
            return tool.model_name
    return None
