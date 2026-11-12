"""Hermes tool-choice setting + ``respond`` exit overlay.

Install/update overlay copies vendor tool_choice.py and wires three call sites.
The product default is ``auto``; users can opt into ``required``. Provider 400
demotion lives in the overlay module (auto for that base_url only).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_MARKER_IMPORT = "from agent.tool_choice import apply_tool_choice"
_MARKER_APPLY = "tools_for_api, request_overrides = apply_tool_choice("
_MARKER_UNWRAP_IMPORT = "from agent.tool_choice import unwrap_respond_call"
_MARKER_UNWRAP_CALL = "unwrap_respond_call(assistant_message)"
_MARKER_INIT = 'agent._tool_choice = _agent_section.get("tool_choice", "auto")'
_MARKER_DEFAULT = '"tool_choice": "auto"'
_MARKER_SIDE = "unwrap_respond_call(assistant_message)  # parent's tool_choice"
TOOL_CHOICE_AUTO = "auto"
TOOL_CHOICE_REQUIRED = "required"
TOOL_CHOICE_VALUES = (TOOL_CHOICE_AUTO, TOOL_CHOICE_REQUIRED)


def _repo_overlay_src() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "vendor"
        / "iris-agent-runtime"
        / "overlays"
        / "tool_choice"
        / "tool_choice.py"
    )


def tool_choice_module_path(agent_root: Path) -> Path:
    return Path(agent_root) / "agent" / "tool_choice.py"


def tool_choice_overlay_present(agent_root: Path) -> bool:
    path = tool_choice_module_path(agent_root)
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return "RESPOND_TOOL_NAME" in text and "apply_tool_choice" in text


def _insert_after(text: str, needle: str, insert: str) -> str | None:
    if insert.strip() in text:
        return text
    idx = text.find(needle)
    if idx < 0:
        return None
    end = idx + len(needle)
    # keep newline after needle
    if end < len(text) and text[end] == "\n":
        end += 1
    return text[:end] + insert + text[end:]


def _ensure_chat_helpers(agent_root: Path) -> str:
    path = Path(agent_root) / "agent" / "chat_completion_helpers.py"
    if not path.is_file():
        return "chat_completion_helpers missing"
    text = path.read_text(encoding="utf-8")
    changed = False
    if _MARKER_IMPORT not in text:
        needle = "from agent.fast_mode import effective_request_overrides\n"
        nxt = _insert_after(text, needle, _MARKER_IMPORT + "\n")
        if nxt is None:
            return "chat_completion_helpers: import anchor missing"
        text = nxt
        changed = True
    if _MARKER_APPLY not in text:
        needle = "    request_overrides = effective_request_overrides(agent)\n"
        insert = f"    {_MARKER_APPLY}agent, tools_for_api, request_overrides)\n"
        nxt = _insert_after(text, needle, insert)
        if nxt is None:
            return "chat_completion_helpers: apply anchor missing"
        text = nxt
        changed = True
    if changed:
        path.write_text(text, encoding="utf-8")
        return "chat_completion_helpers patched (apply_tool_choice)"
    return "chat_completion_helpers already wired"


def _ensure_intake(agent_root: Path) -> str:
    path = Path(agent_root) / "agent" / "turn_response_intake.py"
    if not path.is_file():
        return "turn_response_intake missing"
    text = path.read_text(encoding="utf-8")
    changed = False
    if _MARKER_UNWRAP_IMPORT not in text:
        needle = "from agent.provider_projection import splice_provider_projection\n"
        nxt = _insert_after(text, needle, _MARKER_UNWRAP_IMPORT + "\n")
        if nxt is None:
            return "turn_response_intake: import anchor missing"
        text = nxt
        changed = True
    if _MARKER_UNWRAP_CALL not in text:
        needle = "    assistant_message = normalize_response_for_agent(agent, response)\n"
        insert = (
            "    # agent.tool_choice: required — respond-only → plain text before finish_reason\n"
            f"    {_MARKER_UNWRAP_CALL}\n"
        )
        nxt = _insert_after(text, needle, insert)
        if nxt is None:
            return "turn_response_intake: unwrap anchor missing"
        text = nxt
        changed = True
    if changed:
        path.write_text(text, encoding="utf-8")
        return "turn_response_intake patched (unwrap_respond_call)"
    return "turn_response_intake already wired"


def _ensure_agent_init(agent_root: Path) -> str:
    path = Path(agent_root) / "agent" / "agent_init.py"
    if not path.is_file():
        return "agent_init missing"
    text = path.read_text(encoding="utf-8")
    if _MARKER_INIT in text:
        return "agent_init already wired"
    needle = '    agent._tool_use_enforcement = _agent_section.get("tool_use_enforcement", "auto")\n'
    insert = f"    {_MARKER_INIT}  # agent/tool_choice.py\n"
    nxt = _insert_after(text, needle, insert)
    if nxt is None:
        return "agent_init: tool_use_enforcement anchor missing"
    path.write_text(nxt, encoding="utf-8")
    return "agent_init patched (_tool_choice)"


def _ensure_side_question(agent_root: Path) -> str:
    path = Path(agent_root) / "agent" / "side_question_request.py"
    if not path.is_file():
        return "side_question_request missing"
    text = path.read_text(encoding="utf-8")
    if _MARKER_UNWRAP_CALL in text and "side_question" in path.name:
        # already has unwrap somewhere in function
        if "unwrap_respond_call(assistant_message)" in text:
            return "side_question_request already wired"
    changed = False
    if _MARKER_UNWRAP_IMPORT not in text:
        # insert inside _answer_text when present
        needle = '    from agent.message_content import flatten_message_text\n'
        insert = f"    {_MARKER_UNWRAP_IMPORT}\n"
        nxt = _insert_after(text, needle, insert)
        if nxt is None:
            return "side_question_request: import anchor missing"
        text = nxt
        changed = True
    if "unwrap_respond_call(assistant_message)" not in text:
        needle = '    from agent.message_content import flatten_message_text\n'
        # after imports in function
        if _MARKER_UNWRAP_IMPORT in text:
            needle = f"    {_MARKER_UNWRAP_IMPORT}\n"
        insert = (
            "    unwrap_respond_call(assistant_message)  "
            "# parent's tool_choice=required -> reply via respond\n"
        )
        nxt = _insert_after(text, needle, insert)
        if nxt is None:
            return "side_question_request: unwrap anchor missing"
        text = nxt
        changed = True
    if changed:
        path.write_text(text, encoding="utf-8")
        return "side_question_request patched (unwrap)"
    return "side_question_request already wired"


def _ensure_config_defaults(agent_root: Path) -> str:
    path = Path(agent_root) / "hermes_cli" / "config_defaults.py"
    if not path.is_file():
        return "config_defaults missing"
    text = path.read_text(encoding="utf-8")
    if _MARKER_DEFAULT in text:
        return "config_defaults already has tool_choice"
    needle = '        "tool_use_enforcement": "auto",\n'
    insert = (
        '        "tool_choice": "auto",  '
        '# "required": force tool call + respond exit (agent/tool_choice.py)\n'
    )
    nxt = _insert_after(text, needle, insert)
    if nxt is None:
        return "config_defaults: tool_use_enforcement anchor missing"
    path.write_text(nxt, encoding="utf-8")
    return "config_defaults patched (tool_choice default)"


def apply_hermes_tool_choice_overlay(agent_root: Path) -> list[str]:
    """Copy tool_choice.py and wire call sites. Idempotent."""
    root = Path(agent_root)
    messages: list[str] = []
    src = _repo_overlay_src()
    if not src.is_file():
        messages.append(f"tool_choice overlay missing: {src}")
        return messages
    dest = tool_choice_module_path(root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src, dest)
        messages.append("tool_choice.py installed")
    except OSError as exc:
        messages.append(f"tool_choice.py copy fail: {exc}")
        return messages
    for fn in (
        _ensure_chat_helpers,
        _ensure_intake,
        _ensure_agent_init,
        _ensure_side_question,
        _ensure_config_defaults,
    ):
        try:
            messages.append(fn(root))
        except OSError as exc:
            messages.append(f"{fn.__name__} fail: {exc}")
    return messages


def load_hermes_tool_choice(*, home: Path | None = None) -> str:
    """Return the configured choice, falling back to the product default."""
    try:
        import yaml  # type: ignore
    except ImportError:
        return TOOL_CHOICE_AUTO

    if home is None:
        from iris.infrastructure.iris_agent_credentials import hermes_home

        home = hermes_home()
    path = Path(home) / "config.yaml"
    if not path.is_file():
        return TOOL_CHOICE_AUTO
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
    except Exception:  # noqa: BLE001
        return TOOL_CHOICE_AUTO
    agent = data.get("agent") if isinstance(data, dict) else None
    value = str((agent or {}).get("tool_choice") or TOOL_CHOICE_AUTO).strip().lower()
    return value if value in TOOL_CHOICE_VALUES else TOOL_CHOICE_AUTO


def set_hermes_tool_choice(value: str) -> tuple[bool, str]:
    """Persist ``auto`` or ``required``. Returns ``(changed, status)``."""
    choice = str(value or "").strip().lower()
    if choice not in TOOL_CHOICE_VALUES:
        return False, f"invalid agent.tool_choice: {value!r}"
    try:
        import yaml  # type: ignore
    except ImportError:
        return False, "PyYAML missing — cannot set agent.tool_choice"

    from iris.infrastructure.iris_agent_credentials import hermes_home

    path = hermes_home() / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
        except Exception as exc:  # noqa: BLE001
            return False, f"config.yaml parse error: {exc}"
        if not isinstance(data, dict):
            data = {}
    else:
        data = {}

    agent = data.get("agent")
    if not isinstance(agent, dict):
        agent = {}
    current = str(agent.get("tool_choice") or TOOL_CHOICE_AUTO).strip().lower()
    if current == choice and path.is_file():
        return False, f"hermes agent.tool_choice already {choice}"
    agent["tool_choice"] = choice
    data["agent"] = agent
    bak = path.with_name("config.yaml.bak-iris-tool-choice")
    if path.is_file() and not bak.is_file():
        try:
            shutil.copy2(path, bak)
        except OSError:
            pass
    try:
        path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    except OSError as exc:
        return False, f"config.yaml write failed: {exc}"
    written = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
    written_value = str(
        (written.get("agent") or {}).get("tool_choice") or ""
    ).strip().lower()
    if written_value != choice:
        return False, f"hermes agent.tool_choice write missing {choice}"
    return True, f"hermes agent.tool_choice: {choice}"


def iris_tool_force_policy() -> dict[str, Any]:
    """Iris-side ToolForcePolicy snapshot for self-checks / UI notes."""
    choice = load_hermes_tool_choice()
    return {
        "first_llm_step": choice,
        "exit_tool": "respond" if choice == TOOL_CHOICE_REQUIRED else "",
        "after_real_tools": (
            "required+respond" if choice == TOOL_CHOICE_REQUIRED else TOOL_CHOICE_AUTO
        ),
        "api_modes": ("chat_completions",),
        "unsupported_fallback": "auto",
    }


def note_tool_choice_400(
    error: str,
    *,
    provider: str = "",
    base_url: str = "",
) -> str:
    """If ``error`` is a tool_choice 400, demote that endpoint and return one activity line.

    Never raises. Empty string means no demotion.
    """
    try:
        from types import SimpleNamespace

        agent_root = hermes_home_agent_root()
        if not tool_choice_overlay_present(agent_root):
            return ""
        # Load installed overlay (same demotion file Hermes uses).
        import importlib.util

        path = tool_choice_module_path(agent_root)
        spec = importlib.util.spec_from_file_location("hermes_agent_tool_choice", path)
        if not spec or not spec.loader:
            return ""
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if not mod.looks_like_tool_choice_rejection(error):
            return ""
        agent = SimpleNamespace(
            provider=provider,
            base_url=base_url,
            _tool_choice="required",
            _tool_choice_disabled=False,
        )
        return mod.demote_tool_choice_for_endpoint(agent, reason=str(error)[:200])
    except Exception:  # noqa: BLE001
        return ""


def hermes_home_agent_root() -> Path:
    from iris.infrastructure.iris_agent_credentials import hermes_home

    return hermes_home() / "hermes-agent"
