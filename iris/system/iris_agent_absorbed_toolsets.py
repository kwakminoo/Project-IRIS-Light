"""Install-time overlay: empty Hermes ``terminal`` / ``browser`` toolset definitions.

Policy: those jobs belong to Iris SpeakTools (``project.run`` / ``shell.run`` /
engine iris tools). Upstream tool source files stay on disk; this only patches
``toolsets.py`` after the ``TOOLSETS`` dict so ``BUILTIN_TOOL_NAMES`` sees empties.
``ensure_hermes_disabled_terminal`` remains the config.yaml belt-and-suspenders.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

IRIS_ABSORBED_TOOLSETS = frozenset({"terminal", "browser"})
_MARKER = "iris: absorbed-toolsets"


def _repo_snippet_src() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "vendor"
        / "iris-agent-runtime"
        / "overlays"
        / "absorbed_toolsets"
        / "absorbed_toolsets_snippet.py"
    )


def toolsets_module_path(agent_root: Path) -> Path:
    return Path(agent_root) / "toolsets.py"


def absorbed_toolsets_overlay_present(agent_root: Path) -> bool:
    path = toolsets_module_path(agent_root)
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return _MARKER in text and "IRIS_ABSORBED_TOOLSETS" in text


def _find_toolsets_dict_end(text: str) -> int | None:
    """Return index of the newline after the closing ``}`` of ``TOOLSETS = {``."""
    match = re.search(r"(?m)^TOOLSETS\s*=\s*\{", text)
    if match is None:
        return None
    brace_at = text.find("{", match.start())
    depth = 0
    for i in range(brace_at, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                if end < len(text) and text[end] == "\r":
                    end += 1
                if end < len(text) and text[end] == "\n":
                    end += 1
                return end
    return None


def apply_absorbed_toolsets_overlay(agent_root: Path) -> list[str]:
    """Inject absorbed-toolsets snippet into ``toolsets.py``. Idempotent."""
    root = Path(agent_root)
    messages: list[str] = []
    src = _repo_snippet_src()
    if not src.is_file():
        messages.append(f"absorbed_toolsets overlay missing: {src}")
        return messages
    path = toolsets_module_path(root)
    if not path.is_file():
        messages.append(f"absorbed_toolsets: toolsets.py missing at {path}")
        return messages
    if absorbed_toolsets_overlay_present(root):
        messages.append("absorbed_toolsets overlay present")
        return messages
    try:
        text = path.read_text(encoding="utf-8")
        snippet = src.read_text(encoding="utf-8")
    except OSError as exc:
        messages.append(f"absorbed_toolsets read fail: {exc}")
        return messages
    insert_at = _find_toolsets_dict_end(text)
    if insert_at is None:
        messages.append("absorbed_toolsets: TOOLSETS dict anchor missing")
        log.warning("absorbed_toolsets overlay: TOOLSETS dict not found in %s", path)
        return messages
    # Snippet is a fragment; strip a leading module docstring if ever added.
    body = snippet
    if body.startswith('"""') or body.startswith("'''"):
        messages.append("absorbed_toolsets: unexpected docstring in snippet")
        return messages
    block = "\n" + body.rstrip() + "\n"
    new = text[:insert_at] + block + text[insert_at:]
    try:
        compile(new, str(path), "exec")
    except SyntaxError as exc:
        messages.append(f"absorbed_toolsets syntax check fail: {exc}")
        return messages
    try:
        path.write_text(new, encoding="utf-8", newline="")
    except OSError as exc:
        messages.append(f"absorbed_toolsets write fail: {exc}")
        return messages
    messages.append("absorbed_toolsets overlay applied")
    return messages


def load_toolsets_namespace(agent_root: Path) -> dict:
    """Exec ``toolsets.py`` in an isolated namespace (temp fixtures / self-check)."""
    path = toolsets_module_path(agent_root)
    text = path.read_text(encoding="utf-8")
    ns: dict = {"__name__": "toolsets_overlay_check", "frozenset": frozenset}
    exec(compile(text, str(path), "exec"), ns, ns)  # noqa: S102 — fixture check only
    if not isinstance(ns.get("TOOLSETS"), dict):
        raise AssertionError("TOOLSETS missing after exec")
    return ns
