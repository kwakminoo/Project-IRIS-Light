"""One approval record for shell cards. Pure choice plus a JSON file."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from iris.ui.chat.card_models import RUN_MODES

_MODE_IDS = frozenset(mode_id for mode_id, _label, _description in RUN_MODES)
_DEFAULT_MODE_ID = "ask_every_time"

# Bare interpreter on allowlist must not auto-approve arbitrary code.
_INTERPRETER_NAMES = frozenset(
    {
        "python",
        "python3",
        "py",
        "node",
        "nodejs",
        "powershell",
        "pwsh",
        "cmd",
        "bash",
        "sh",
        "zsh",
        "ruby",
        "perl",
        "lua",
        "deno",
        "bun",
    }
)

# Compound / shell metacharacters → ask (use_allowlist never auto).
_UNSAFE_SHELL_RE = re.compile(
    r"(?:&&|\|\||[;|`\n\r]|\$\(|\$\{|(?<![>\d])>(?!>)|(?<![<\d])<(?!<))"
)


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


def is_compound_or_unsafe(command: str) -> bool:
    """True when shell metacharacters prevent a single allowlist scope."""
    text = (command or "").strip()
    if not text:
        return True
    return bool(_UNSAFE_SHELL_RE.search(text))


def allowlist_key(command: str) -> str:
    """Stable allowlist scope for Always Allow / use_allowlist matching.

    Interpreters require a scoped key (module or script). Bare interpreter names
    are never returned — legacy allowlist entries of only ``python`` do not auto-run.
    Compound or unsafe commands return \"\" (must ask).
    """
    text = (command or "").strip()
    if not text or is_compound_or_unsafe(text):
        return ""
    tokens = [t.strip("\"'") for t in text.split() if t.strip("\"'")]
    if not tokens:
        return ""
    head = tokens[0].lower()
    base = Path(head).name.lower()
    if base.endswith(".exe"):
        base = base[:-4]
    if base in _INTERPRETER_NAMES or head in _INTERPRETER_NAMES:
        for i, tok in enumerate(tokens[1:], start=1):
            tl = tok.lower()
            if tl in ("-c", "-e", "--eval", "/c", "-command", "-encodedcommand"):
                return ""
            if tl == "-m" and i + 1 < len(tokens):
                return f"{tokens[0]} -m {tokens[i + 1]}"
            if not tl.startswith("-"):
                return f"{tokens[0]} {tok}"
        return ""
    return tokens[0]


def should_auto_run(state: ApprovalState, command: str) -> bool:
    if state.mode_id == "run_everything":
        return True
    if state.mode_id == "use_allowlist":
        key = allowlist_key(command)
        return bool(key) and key in state.allowlist
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
        # Compound/unsafe → no allowlist widen (do not fall back to bare prefix).
        key = allowlist_key(command)
        if not key:
            return state
        allowlist = state.allowlist if key in state.allowlist else (*state.allowlist, key)
        next_state = ApprovalState(mode_id="use_allowlist", allowlist=allowlist)
        return state if next_state == state else next_state
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
