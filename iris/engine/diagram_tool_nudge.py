"""Soft redirect when the model writes standalone HTML diagrams instead of diagram.render."""

from __future__ import annotations

import json
from dataclasses import dataclass, field


HINT = (
    "Iris diagram path: call SpeakTools diagram.render with kind "
    "(architecture|workflow|sequence|dataflow|lifecycle) and ir JSON. "
    "Do not write standalone .html diagram files with write_file, patch, "
    "or execute_code."
)

_MISUSE_TOOLS = frozenset(
    {
        "write_file",
        "patch",
        "execute_code",
        "create_file",
        "edit_file",
    }
)


def _error_text(result: object) -> str:
    raw: object = result
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return ""
        try:
            raw = json.loads(text)
        except (TypeError, ValueError):
            return text
    if not isinstance(raw, dict):
        return str(result or "")
    if raw.get("ok") is True and not raw.get("error"):
        return ""
    if raw.get("error"):
        return " ".join(str(raw["error"]).split())
    if raw.get("ok") is False:
        return " ".join(str(raw.get("output") or raw.get("status") or "ok=false").split())
    return ""


def _args_blob(args: object) -> str:
    try:
        return json.dumps(args or {}, ensure_ascii=False, default=str).lower()
    except (TypeError, ValueError):
        return repr(args).lower()


def looks_like_html_diagram_misuse(name: str, args: object, result: object) -> bool:
    tool = (name or "").strip().lower()
    if tool not in _MISUSE_TOOLS:
        return False
    err = _error_text(result).lower()
    if not err and tool != "execute_code":
        return False
    blob = _args_blob(args)
    hay = f"{blob}\n{err}"
    if ".html" in hay or "diagram" in hay:
        return True
    if tool == "execute_code" and any(
        token in hay for token in ("<!doctype", "<html", "svg", "canvas")
    ):
        return True
    return False


@dataclass
class DiagramToolNudge:
    """One soft hint per turn after repeated HTML-diagram tool misuse."""

    threshold: int = 2
    misuse_errors: int = 0
    fired: bool = False
    last_hint: str = ""
    events: list[str] = field(default_factory=list)

    def observe(self, name: str, args: object, result: object) -> str:
        if self.fired:
            return ""
        if not looks_like_html_diagram_misuse(name, args, result):
            return ""
        self.misuse_errors += 1
        self.events.append(str(name or "tool"))
        if self.misuse_errors < self.threshold:
            return ""
        self.fired = True
        self.last_hint = HINT
        return HINT


def append_hint_to_last_tool_result(agent: object, hint: str) -> bool:
    """Append redirect text to the latest tool role message so the next API call sees it."""
    text = (hint or "").strip()
    if not text:
        return False
    msgs = getattr(agent, "_session_messages", None)
    if not isinstance(msgs, list):
        return False
    for message in reversed(msgs):
        if not isinstance(message, dict):
            continue
        if message.get("role") != "tool":
            continue
        content = str(message.get("content") or "")
        if text in content:
            return False
        sep = "\n\n" if content.strip() else ""
        message["content"] = content + sep + text
        return True
    return False


def _self_check() -> None:
    failed = '{"error": "Refusing to overwrite /c/Users/x/Desktop/neuron-synapse-diagram.html"}'
    assert looks_like_html_diagram_misuse(
        "write_file", {"path": "C:/Users/x/Desktop/neuron-synapse-diagram.html"}, failed
    )
    assert not looks_like_html_diagram_misuse(
        "read_file", {"path": "C:/Users/x/Desktop/neuron-synapse-diagram.html"}, failed
    )
    nudge = DiagramToolNudge()
    assert nudge.observe("write_file", {"path": "a.html"}, failed) == ""
    assert HINT in nudge.observe("write_file", {"path": "a.html"}, failed)
    assert nudge.observe("write_file", {"path": "a.html"}, failed) == ""

    agent = type("A", (), {"_session_messages": [{"role": "tool", "content": '{"error": "x"}'}]})()
    assert append_hint_to_last_tool_result(agent, HINT) is True
    assert HINT in agent._session_messages[0]["content"]
    assert append_hint_to_last_tool_result(agent, HINT) is False


if __name__ == "__main__":
    _self_check()
    print("diagram tool nudge ok")
