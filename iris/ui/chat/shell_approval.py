"""One approval record for shell cards. Pure choice plus a JSON file."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from iris.ui.chat.card_models import RUN_MODES

_MODE_IDS = frozenset(mode_id for mode_id, _label, _description in RUN_MODES)
_DEFAULT_MODE_ID = "ask_every_time"


@dataclass(frozen=True)
class ApprovalState:
    mode_id: str = _DEFAULT_MODE_ID
    allowlist: tuple[str, ...] = ()


def default_approval_path() -> Path:
    return Path.home() / ".iris-light" / "shell_approval.json"


def command_prefix(command: str) -> str:
    text = (command or "").strip()
    if not text:
        return ""
    return text.split(None, 1)[0].strip("\"'")


def should_auto_run(state: ApprovalState, command: str) -> bool:
    if state.mode_id == "run_everything":
        return True
    if state.mode_id == "use_allowlist":
        prefix = command_prefix(command)
        return bool(prefix) and prefix in state.allowlist
    return False


def preview_command(args: dict) -> str:
    if isinstance(args, dict):
        command = args.get("command")
        if isinstance(command, str) and command.strip():
            return command.strip()
        for key in ("file", "rel_path"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "project.run"


def choose(state: ApprovalState, action: str, command: str) -> ApprovalState:
    act = action if isinstance(action, str) else ""
    if act in _MODE_IDS:
        if act == state.mode_id:
            return state
        return ApprovalState(mode_id=act, allowlist=state.allowlist)
    if act == "always":
        prefix = command_prefix(command)
        if not prefix or prefix in state.allowlist:
            return state
        return ApprovalState(mode_id=state.mode_id, allowlist=(*state.allowlist, prefix))
    return state


def load(path: Path | None = None) -> ApprovalState:
    target = default_approval_path() if path is None else path
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ApprovalState()
    if not isinstance(raw, dict):
        return ApprovalState()
    mode = raw.get("mode_id")
    if not isinstance(mode, str) or mode not in _MODE_IDS:
        mode = _DEFAULT_MODE_ID
    found: list[str] = []
    allow = raw.get("allowlist")
    if isinstance(allow, list):
        for item in allow:
            if isinstance(item, str) and item and item not in found:
                found.append(item)
    return ApprovalState(mode_id=mode, allowlist=tuple(found))


def save(state: ApprovalState, path: Path | None = None) -> None:
    target = default_approval_path() if path is None else path
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(
            {"mode_id": state.mode_id, "allowlist": list(state.allowlist)},
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    # A crash mid-write must not replace a good file with a partial document.
    try:
        if target.read_text(encoding="utf-8") == payload:
            return
    except OSError:
        pass
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(target)
