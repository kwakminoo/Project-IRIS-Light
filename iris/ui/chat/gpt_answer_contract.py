"""실전 답변 계약 — display-only fence 승격 + plot markdown 병합."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_FENCE = re.compile(r"```([^\n]*)\n([\s\S]*?)```")
_BINARY_LINE = re.compile(r"^[01](?:[\s,]+[01])*$")
_CAPTION = re.compile(r"^#\s+.+$")


def normalize_binary_fences_for_display(md: str) -> str:
    """일반 0/1 fenced 블록을 ```matrix 로 승격 (display-only)."""

    def repl(match: re.Match[str]) -> str:
        lang = (match.group(1) or "").strip()
        body = match.group(2) or ""
        lang_l = lang.lower()
        if lang_l == "matrix":
            return match.group(0)
        # 명시 언어(python 등)는 유지. 빈/text/plain 만 후보.
        if lang_l and lang_l not in ("", "text", "plain", "txt"):
            return match.group(0)
        if not _is_binary_grid_body(body):
            return match.group(0)
        return f"```matrix\n{body.rstrip()}\n```"

    return _FENCE.sub(repl, md or "")


def _is_binary_grid_body(body: str) -> bool:
    rows: list[str] = []
    for raw in (body or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if _CAPTION.match(line) and not rows:
            continue
        if not _BINARY_LINE.match(line):
            return False
        rows.append(line)
    if len(rows) < 2:
        return False
    widths = []
    for line in rows:
        cells = re.split(r"[\s,]+", line.strip())
        if len(cells) < 2:
            return False
        widths.append(len(cells))
    return min(widths) == max(widths)


def maybe_attach_plot_markdown(
    assistant_text: str,
    tool_payload: dict[str, Any] | None,
) -> str:
    """chat.exec_python 성공 시 chat_markdown/png 를 답에 붙인다 (이미 있으면 유지)."""
    text = assistant_text or ""
    if not tool_payload:
        return text
    md = str(tool_payload.get("chat_markdown") or "").strip()
    paths = [str(p) for p in (tool_payload.get("png_paths") or []) if p]
    if not md and paths:
        md = "\n\n".join(f"![plot]({Path(p).resolve().as_posix()})" for p in paths)
    if not md:
        return text
    if md in text:
        return text
    # 경로·파일명이 이미 본문에 있으면 중복 삽입하지 않음
    for p in paths:
        name = Path(p).name
        posix = Path(p).resolve().as_posix()
        if name and name in text:
            return text
        if posix in text.replace("\\", "/"):
            return text
    return text.rstrip() + "\n\n" + md
