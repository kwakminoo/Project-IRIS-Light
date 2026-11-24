"""Install-time overlay: empty Hermes absorbed toolset definitions.

Policy: terminal / browser / file / web jobs belong to Iris SpeakTools
(``project.run`` / ``shell.run`` / ``web.run_*`` / engine iris tools).
Upstream tool source files stay on disk; this only patches ``toolsets.py``
after the ``TOOLSETS`` dict so ``BUILTIN_TOOL_NAMES`` sees empties.
``ensure_iris_agent_disabled_terminal`` remains the config.yaml belt-and-suspenders.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

IRIS_ABSORBED_TOOLSETS = frozenset({"terminal", "browser", "file", "web"})
_MARKER = "iris: absorbed-toolsets"
_END_MARKER = "iris: absorbed-toolsets end"
# Leading \n? matches the blank line inject puts before the block.
# Legacy block (pre end-marker) ends at the NameError guard.
_LEGACY_BLOCK_RE = re.compile(
    r"(?ms)\n?#\s*iris:\s*absorbed-toolsets\b.*?^except NameError:\n    pass\n?"
)
_BLOCK_RE = re.compile(
    r"(?ms)\n?#\s*iris:\s*absorbed-toolsets\b.*?^#\s*iris:\s*absorbed-toolsets end\s*\n?"
)


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


def _snippet_body(snippet: str) -> str | None:
    """Return snippet body, or None if it has an unexpected leading docstring."""
    if snippet.startswith('"""') or snippet.startswith("'''"):
        return None
    return snippet.rstrip() + "\n"


def _strip_overlay_block(text: str) -> str:
    """Remove an injected absorbed-toolsets block (current or legacy form)."""
    if _END_MARKER in text:
        return _BLOCK_RE.sub("", text, count=1)
    if _MARKER in text:
        return _LEGACY_BLOCK_RE.sub("", text, count=1)
    return text


def _extract_overlay_block(text: str) -> str | None:
    """Return the on-disk overlay block body, or None if absent."""
    if _END_MARKER in text:
        match = _BLOCK_RE.search(text)
        return match.group(0) if match else None
    if _MARKER in text:
        match = _LEGACY_BLOCK_RE.search(text)
        return match.group(0) if match else None
    return None


def _inject_overlay(text: str, body: str) -> str | None:
    """Insert overlay body after TOOLSETS dict. Returns None if anchor missing."""
    insert_at = _find_toolsets_dict_end(text)
    if insert_at is None:
        return None
    block = "\n" + body
    if not block.endswith("\n"):
        block += "\n"
    return text[:insert_at] + block + text[insert_at:]


def apply_absorbed_toolsets_overlay(agent_root: Path) -> list[str]:
    """Inject or refresh absorbed-toolsets snippet in ``toolsets.py``.

    Idempotent when the on-disk block matches the repo snippet. When the
    marker is present but the block differs, replace the whole marker block
    (no double-insert).
    """
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
    try:
        text = path.read_text(encoding="utf-8")
        snippet = src.read_text(encoding="utf-8")
    except OSError as exc:
        messages.append(f"absorbed_toolsets read fail: {exc}")
        return messages
    body = _snippet_body(snippet)
    if body is None:
        messages.append("absorbed_toolsets: unexpected docstring in snippet")
        return messages
    if _MARKER not in body or _END_MARKER not in body:
        messages.append("absorbed_toolsets: snippet missing start/end markers")
        return messages

    had_overlay = _MARKER in text and "IRIS_ABSORBED_TOOLSETS" in text
    if had_overlay:
        existing = _extract_overlay_block(text)
        if existing is not None and existing.strip() == body.strip():
            messages.append("absorbed_toolsets overlay present")
            return messages

    base = _strip_overlay_block(text) if had_overlay else text
    new = _inject_overlay(base, body)
    if new is None:
        messages.append("absorbed_toolsets: TOOLSETS dict anchor missing")
        log.warning("absorbed_toolsets overlay: TOOLSETS dict not found in %s", path)
        return messages

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
    if had_overlay:
        messages.append("absorbed_toolsets overlay refreshed")
    else:
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
