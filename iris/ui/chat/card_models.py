"""Chat card view models. Fence info in, display fields out. No HTML."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FenceInfo:
    """Parsed markdown/stream fence info string. Pure domain; no HTML."""

    language: str = ""
    path: str = ""
    start_line: int | None = None
    end_line: int | None = None


@dataclass(frozen=True)
class CodeCardModel:
    """What a code card shows. The painter reads this and does not re-parse the fence."""

    body: str
    lang_id: str
    header_primary: str
    header_secondary: str
    copy_payload: str
    open_path: str
    end_line: int | None = None


RUN_MODES = (
    (
        "ask_every_time",
        "Ask Every Time",
        "Ask for permission before running each operation.",
    ),
    (
        "use_allowlist",
        "Allowlist",
        "Automatically run operations after you approve them once.",
    ),
    (
        "run_everything",
        "Run Everything",
        "Automatically run all operations without asking for permission.",
    ),
)


@dataclass(frozen=True)
class ShellCardModel:
    """What a shell card shows. Copy payload is the command text."""

    title: str
    command: str
    output: str
    status_kind: str
    status_label: str
    block_id: str
    collapsed: bool
    show_command_copy: bool
    copy_payload: str
    phase: str = "done"


class _CodeBlock(Protocol):
    code: str
    language: str


class _ShellBlock(Protocol):
    title: str
    command: str
    output: str
    status: str
    block_id: str
    collapsed: bool


_LANG_DISPLAY_NAMES = {
    "py": "Python",
    "python": "Python",
    "js": "JavaScript",
    "javascript": "JavaScript",
    "jsx": "JSX",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "tsx": "TSX",
    "json": "JSON",
    "html": "HTML",
    "css": "CSS",
    "sql": "SQL",
    "sh": "Bash",
    "bash": "Bash",
    "shell": "Shell",
    "zsh": "Zsh",
    "yml": "YAML",
    "yaml": "YAML",
    "md": "Markdown",
    "markdown": "Markdown",
    "kt": "Kotlin",
    "cs": "C#",
    "cpp": "C++",
    "c++": "C++",
    "ps1": "PowerShell",
    "powershell": "PowerShell",
}

_OK_STATUS = frozenset({"ok", "success", "done"})


def display_lang_name(language: str) -> str:
    lang = (language or "").strip()
    if not lang:
        return ""
    return _LANG_DISPLAY_NAMES.get(lang.lower(), lang.capitalize())


def _looks_like_lang(token: str) -> bool:
    s = (token or "").strip()
    if not s or "/" in s or "\\" in s or "." in s:
        return False
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_+#-]*", s))


def _looks_like_path(token: str) -> bool:
    s = (token or "").strip()
    if not s:
        return False
    if "/" in s or "\\" in s:
        return True
    return bool(re.search(r"\.[A-Za-z0-9]{1,8}\Z", s))


def parse_fence_info(info: str) -> FenceInfo:
    """Pure boundary parse for fence info / language-class strings. Never raises."""
    raw = (info or "").strip()
    if not raw:
        return FenceInfo()

    # "python path/to/file.py" — single space separator (lang has no colon)
    if " " in raw:
        left, _, right = raw.partition(" ")
        left, right = left.strip(), right.strip()
        if left and right and ":" not in left and _looks_like_lang(left) and _looks_like_path(right):
            return FenceInfo(language=left, path=right.replace("\\", "/"))

    parts = raw.split(":")
    # "python:12:40:path/to/file.py"
    if len(parts) >= 4 and parts[1].isdigit() and parts[2].isdigit():
        lang = parts[0].strip()
        path = ":".join(parts[3:]).strip().replace("\\", "/")
        if lang and path and (_looks_like_lang(lang) or not parts[0].isdigit()):
            try:
                start_line = int(parts[1])
                end_line = int(parts[2])
            except ValueError:
                start_line = end_line = None
            return FenceInfo(
                language=lang,
                path=path,
                start_line=start_line,
                end_line=end_line,
            )

    # "12:40:path/to/file.py"
    if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():
        path = ":".join(parts[2:]).strip().replace("\\", "/")
        if path:
            try:
                start_line = int(parts[0])
                end_line = int(parts[1])
            except ValueError:
                start_line = end_line = None
            return FenceInfo(
                language="",
                path=path,
                start_line=start_line,
                end_line=end_line,
            )

    # "python:path/to/file.py"
    if len(parts) >= 2:
        lang = parts[0].strip()
        path = ":".join(parts[1:]).strip().replace("\\", "/")
        if _looks_like_lang(lang) and _looks_like_path(path):
            return FenceInfo(language=lang, path=path)

    if _looks_like_path(raw):
        return FenceInfo(path=raw.replace("\\", "/"))

    return FenceInfo(language=raw)


def _open_path(path: str, start_line: int | None) -> str:
    if not path:
        return ""
    if start_line is None:
        return path
    return f"{path}:{start_line}"


def to_code_card(block: _CodeBlock) -> CodeCardModel:
    meta = parse_fence_info(block.language or "")
    body = block.code or ""
    path = meta.path
    lang = meta.language
    start = meta.start_line
    end = meta.end_line
    return CodeCardModel(
        body=body,
        lang_id=lang,
        header_primary=path.rsplit("/", 1)[-1] if path else "",
        header_secondary=display_lang_name(lang),
        copy_payload=body,
        open_path=_open_path(path, start),
        end_line=end,
    )


def _block_phase(block: _ShellBlock) -> str:
    raw = getattr(block, "phase", None)
    if not isinstance(raw, str):
        return "done"
    return raw.strip() or "done"


def to_shell_card(block: _ShellBlock) -> ShellCardModel:
    status = (block.status or "ok").strip().lower()
    kind = "ok" if status in _OK_STATUS else "error"
    if status == "skipped":
        label = "Skipped"
    elif kind == "ok":
        label = "성공"
    else:
        label = "실패"
    command = block.command or ""
    return ShellCardModel(
        title=block.title or "",
        command=command,
        output=block.output or "",
        status_kind=kind,
        status_label=label,
        block_id=block.block_id or "",
        collapsed=bool(block.collapsed),
        show_command_copy=bool(command),
        copy_payload=command,
        phase=_block_phase(block),
    )
