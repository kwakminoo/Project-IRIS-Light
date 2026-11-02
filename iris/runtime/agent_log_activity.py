"""Hermes agent.log → Live Activity 줄 (필터·truncate·턴 범위 tail).

파이프라인 로그 본문만 통과시킨다. UX 카피 문장은 만들지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from iris.infrastructure.agent_runtime import iris_agent_home

AGENT_LOG_MAX_CHARS = 240
AGENT_LOG_POLL_MS = 400

_ALLOWED_LOGGERS = (
    "agent.conversation_loop",
    "agent.tool_executor",
    "agent.chat_completion_helpers",
)

_LOGGER_RE = re.compile(
    r"\b(" + "|".join(re.escape(name) for name in _ALLOWED_LOGGERS) + r")\s*:\s*(.*)$"
)
_LEVEL_RE = re.compile(r"\b(WARNING|ERROR)\b")


@dataclass(frozen=True)
class AgentLogLine:
    text: str
    kind: str  # api | tool | turn | warn


def default_agent_log_path() -> Path:
    return iris_agent_home() / "logs" / "agent.log"


def truncate_activity_line(text: str, max_chars: int = AGENT_LOG_MAX_CHARS) -> str:
    s = (text or "").strip()
    if len(s) <= max_chars:
        return s
    if max_chars <= 1:
        return s[:max_chars]
    return s[: max_chars - 1] + "…"


def _display_body(raw: str) -> str:
    m = _LOGGER_RE.search(raw)
    if m:
        return m.group(2).strip()
    return raw.strip()


def classify_agent_log_line(raw: str) -> AgentLogLine | None:
    """Allowlist만 통과. 노이즈(gateway, hermes_state, tools.registry …)는 None."""
    line = (raw or "").rstrip("\r\n")
    if not line.strip():
        return None
    m = _LOGGER_RE.search(line)
    if m is None:
        return None
    logger = m.group(1)
    body = m.group(2).strip()
    if not body:
        return None

    if "API call #" in body:
        kind = "api"
    elif body.startswith("Turn ended") or "Turn ended:" in body:
        kind = "turn"
    elif logger == "agent.tool_executor":
        kind = "tool"
    elif _LEVEL_RE.search(line) is not None:
        # Clean EOF 등 — allowlisted logger의 WARNING/ERROR만
        kind = "warn"
    else:
        return None

    return AgentLogLine(text=truncate_activity_line(body), kind=kind)


class AgentLogTailer:
    """턴 시작 시 EOF로 맞춘 뒤, poll마다 새 줄만 필터링해 반환."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or default_agent_log_path()
        self._offset = 0
        self._pending = ""

    @property
    def path(self) -> Path:
        return self._path

    def reset_to_eof(self) -> None:
        self._pending = ""
        try:
            self._offset = self._path.stat().st_size
        except OSError:
            self._offset = 0

    def poll(self) -> list[AgentLogLine]:
        path = self._path
        try:
            size = path.stat().st_size
        except OSError:
            return []
        if size < self._offset:
            # rotate / truncate
            self._offset = 0
            self._pending = ""
        if size == self._offset:
            return []
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                fh.seek(self._offset)
                chunk = fh.read()
                self._offset = fh.tell()
        except OSError:
            return []
        if not chunk:
            return []
        data = self._pending + chunk
        if "\n" not in data:
            self._pending = data
            return []
        *complete, self._pending = data.split("\n")
        out: list[AgentLogLine] = []
        for raw in complete:
            item = classify_agent_log_line(raw)
            if item is not None:
                out.append(item)
        return out
