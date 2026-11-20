"""Rerunnable inventory: what the model sees vs ActionRegistry vs skills.

One lever so SpeakTools / teaching / skills cannot drift from each other silently.
Prefer ``integrations/iris-skills`` when present; else ``hermes-skills`` (rename race).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from iris.infrastructure.tool_capability import PHASE4_ALLOWLIST, default_agent_tools
from iris.system.iris_agent_control_sync import SKILL_NAMES, project_root

_MCP_TRIPLE = ("iris_get_state", "iris_get_catalog", "iris_invoke")
_REGISTER_NAME = re.compile(
    r"""\.register\(\s*['\"]([a-zA-Z_][\w.]*)['\"]"""
)
_TEACHING_FILES = (
    Path("iris") / "ui" / "window" / "main_window.py",
)


@dataclass(frozen=True)
class AgentSurfaceInventory:
    """Frozen snapshot of the three agent-facing surfaces."""

    speak_tools: tuple[str, ...]
    control_action_count: int
    control_action_sample: tuple[str, ...]
    skill_names: tuple[str, ...]
    skills_root: str
    forbidden_mcp_triple_in_teaching: bool


def resolve_skills_root(repo: Path | None = None) -> Path:
    """Prefer iris-skills; fall back to hermes-skills during rename races."""
    root = Path(repo) if repo is not None else project_root()
    iris = root / "integrations" / "iris-skills"
    if iris.is_dir():
        return iris
    return root / "integrations" / "hermes-skills"


def _control_names_from_registry(registry: Any) -> tuple[str, ...]:
    if registry is None:
        return ()
    catalog = getattr(registry, "catalog", None)
    if not callable(catalog):
        return ()
    rows = catalog()
    names = sorted(
        str(row.get("name") or "")
        for row in rows
        if isinstance(row, dict) and row.get("name")
    )
    return tuple(n for n in names if n)


def _control_names_from_modules(repo: Path) -> tuple[str, ...]:
    folder = repo / "iris" / "ui" / "control_actions"
    if not folder.is_dir():
        return ()
    found: set[str] = set()
    for path in folder.glob("*.py"):
        if path.name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8")
        found.update(_REGISTER_NAME.findall(text))
    return tuple(sorted(found))


def _live_registry() -> Any | None:
    """Bound ControlSurface.registry when Iris UI is up; else None → module scan."""
    try:
        from iris.infrastructure.tool_capability import _live_control_surface
    except ImportError:
        return None
    try:
        surface = _live_control_surface()
    except Exception:
        return None
    if surface is None:
        return None
    return getattr(surface, "registry", None)


def _skill_names_on_disk(skills_root: Path) -> tuple[str, ...]:
    control = skills_root / "iris-agent"
    if not control.is_dir():
        control = skills_root / "iris-control"
    if not control.is_dir():
        return tuple(SKILL_NAMES)
    on_disk = tuple(
        sorted(
            p.name
            for p in control.iterdir()
            if p.is_dir() and (p / "SKILL.md").is_file()
        )
    )
    return on_disk or tuple(SKILL_NAMES)


def _teaching_texts(repo: Path, skills_root: Path) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for rel in _TEACHING_FILES:
        path = repo / rel
        if path.is_file():
            out.append((rel.as_posix(), path.read_text(encoding="utf-8")))
    if skills_root.is_dir():
        for path in skills_root.rglob("SKILL.md"):
            try:
                rel = path.relative_to(repo).as_posix()
            except ValueError:
                rel = str(path)
            out.append((rel, path.read_text(encoding="utf-8")))
    return out


def scan_forbidden_mcp_triple_in_teaching(
    repo: Path | None = None,
    skills_root: Path | None = None,
) -> bool:
    """True when teaching/skills still name the obsolete MCP triple as tools."""
    root = Path(repo) if repo is not None else project_root()
    skills = skills_root if skills_root is not None else resolve_skills_root(root)
    for _label, text in _teaching_texts(root, skills):
        for bad in _MCP_TRIPLE:
            if bad in text:
                return True
    return False


def build_inventory(
    *,
    repo: Path | None = None,
    registry: Any | None = None,
) -> AgentSurfaceInventory:
    """Collect speak tools, control actions, skills, and teaching scrub flag."""
    root = Path(repo) if repo is not None else project_root()
    speak = default_agent_tools().engine_names()
    if not speak:
        speak = PHASE4_ALLOWLIST.names()

    reg = registry if registry is not None else _live_registry()
    control_names = _control_names_from_registry(reg)
    if not control_names:
        control_names = _control_names_from_modules(root)

    skills = resolve_skills_root(root)
    skill_names = _skill_names_on_disk(skills)
    # Prefer the declared product list when both exist and declared is non-empty.
    if SKILL_NAMES:
        skill_names = tuple(SKILL_NAMES)

    forbidden = scan_forbidden_mcp_triple_in_teaching(root, skills)
    sample = control_names[:12]
    return AgentSurfaceInventory(
        speak_tools=tuple(speak),
        control_action_count=len(control_names),
        control_action_sample=sample,
        skill_names=skill_names,
        skills_root=skills.as_posix() if skills.is_absolute() else str(skills),
        forbidden_mcp_triple_in_teaching=forbidden,
    )


def format_summary(inv: AgentSurfaceInventory) -> str:
    sample = ", ".join(inv.control_action_sample) or "(none)"
    skills = ", ".join(inv.skill_names[:8])
    if len(inv.skill_names) > 8:
        skills += ", …"
    return (
        f"speak_tools={len(inv.speak_tools)} "
        f"control_actions={inv.control_action_count} "
        f"skills={len(inv.skill_names)} "
        f"forbidden_mcp_in_teaching={inv.forbidden_mcp_triple_in_teaching}\n"
        f"  speak sample: {', '.join(inv.speak_tools[:8])}"
        f"{', …' if len(inv.speak_tools) > 8 else ''}\n"
        f"  control sample: {sample}\n"
        f"  skills ({Path(inv.skills_root).name}): {skills}\n"
        f"  control.invoke in speak: "
        f"{'control.invoke' in inv.speak_tools}"
    )


def main() -> None:
    inv = build_inventory()
    print(format_summary(inv))


if __name__ == "__main__":
    main()
