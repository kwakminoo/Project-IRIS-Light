"""Soft hint after a successful shell/terminal tool so the next reply quotes stdout."""

from __future__ import annotations

import json
from dataclasses import dataclass, field


HINT = (
    "Quote the tool stdout/output verbatim in your next reply. "
    "Do not invent GitHub/octokit output."
)

_SHELL_TOOLS = frozenset(
    {
        "terminal",
        "shell.run",
        "shell_run",
        "shell",
    }
)

_MARKER_TOKENS = ("IRIS_ACF_", "IRIS_SHELL_")


def _as_payload(result: object) -> dict | None:
    raw: object = result
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            raw = json.loads(text)
        except (TypeError, ValueError):
            return {"ok": True, "stdout": text, "output": text}
    if isinstance(raw, dict):
        return raw
    return None


def _stdout_blob(payload: dict) -> str:
    chunks: list[str] = []
    for key in ("stdout", "output"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            chunks.append(str(value))
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("stdout", "output"):
            value = data.get(key)
            if value is not None and str(value).strip():
                chunks.append(str(value))
    return "\n".join(chunks)


def _exit_ok(payload: dict) -> bool:
    for source in (payload, payload.get("data") if isinstance(payload.get("data"), dict) else None):
        if not isinstance(source, dict) or "exit_code" not in source:
            continue
        try:
            if int(source["exit_code"]) != 0:
                return False
        except (TypeError, ValueError):
            return False
    return True


def result_is_shell_success(result: object) -> bool:
    payload = _as_payload(result)
    if payload is None:
        return False
    if payload.get("error"):
        return False
    if payload.get("ok") is False:
        return False
    status = str(payload.get("status") or "").strip().lower()
    if status in {"error", "failed", "fail", "failure"}:
        return False
    if not _exit_ok(payload):
        return False
    if payload.get("ok") is True:
        return True
    if status in {"success", "ok", "succeeded", "completed"}:
        return True
    # Bare stdout / tool payload without explicit ok=false.
    return bool(_stdout_blob(payload).strip())


def looks_like_shell_assist_target(name: str, result: object) -> bool:
    tool = (name or "").strip().lower()
    if tool not in _SHELL_TOOLS:
        return False
    if not result_is_shell_success(result):
        return False
    payload = _as_payload(result) or {}
    blob = _stdout_blob(payload)
    if blob.strip():
        return True
    hay = blob
    if isinstance(result, str):
        hay = f"{hay}\n{result}"
    return any(token in hay for token in _MARKER_TOKENS)


@dataclass
class ShellAssistNudge:
    """One soft verbatim-stdout hint per nudge instance after a successful shell tool."""

    fired: bool = False
    last_hint: str = ""
    events: list[str] = field(default_factory=list)

    def observe(self, name: str, args: object, result: object) -> str:
        del args  # signature matches DiagramToolNudge.observe
        if self.fired:
            return ""
        if not looks_like_shell_assist_target(name, result):
            return ""
        self.fired = True
        self.last_hint = HINT
        self.events.append(str(name or "tool"))
        return HINT
