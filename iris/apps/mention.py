"""@app:<id> mentions in composer text.

Owns: parse / resolve / active-span helpers for App Directory mentions.
Does not: render Qt UI or open App Host cards.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from iris.apps.directory import AppDirectory, AppDirectoryEntry

_MENTION_RE = re.compile(r"@app:([A-Za-z0-9][\w.-]*)")
_APP_TOKEN_PREFIX = "@app"


@dataclass(frozen=True)
class AppMention:
    id: str


def parse_app_mentions(text: str) -> list[str]:
    """Unique app ids from `@app:<id>` tokens, first-appearance order."""
    seen: set[str] = set()
    out: list[str] = []
    for match in _MENTION_RE.finditer(text or ""):
        app_id = match.group(1)
        if app_id in seen:
            continue
        seen.add(app_id)
        out.append(app_id)
    return out


def resolve_app_mentions(text: str, directory: AppDirectory) -> list[AppDirectoryEntry]:
    """Directory entries for known mention ids; unknown ids dropped."""
    out: list[AppDirectoryEntry] = []
    for app_id in parse_app_mentions(text):
        entry = directory.get(app_id)
        if entry is not None:
            out.append(entry)
    return out


def active_app_mention_span(text: str, cursor: int) -> tuple[int, int, str] | None:
    """If the cursor sits in `@app` / `@app:` / `@app:partial`, return span + filter query."""
    raw = text or ""
    pos = max(0, min(int(cursor), len(raw)))
    start = pos
    while start > 0 and not raw[start - 1].isspace():
        start -= 1
    token = raw[start:pos]
    if token == _APP_TOKEN_PREFIX:
        return start, pos, ""
    if token.startswith(f"{_APP_TOKEN_PREFIX}:"):
        return start, pos, token[len(_APP_TOKEN_PREFIX) + 1 :]
    return None


def mention_candidates(directory: AppDirectory, query: str) -> list[AppDirectoryEntry]:
    """Filter directory apps by id/title substring (case-insensitive)."""
    needle = (query or "").strip().lower()
    rows = directory.list()
    if not needle:
        return rows
    return [
        entry
        for entry in rows
        if needle in entry.id.lower() or needle in entry.title.lower()
    ]


def apply_app_mention(text: str, cursor: int, app_id: str) -> tuple[str, int]:
    """Replace the active `@app` span (or append) with `@app:<id> `. Returns text + new cursor."""
    clean_id = (app_id or "").strip()
    token = f"@app:{clean_id} "
    raw = text or ""
    pos = max(0, min(int(cursor), len(raw)))
    span = active_app_mention_span(raw, pos)
    if span is None:
        sep = "" if not raw or raw.endswith(" ") else " "
        new_text = f"{raw}{sep}{token}"
        return new_text, len(new_text)
    start, end, _ = span
    new_text = f"{raw[:start]}{token}{raw[end:]}"
    return new_text, start + len(token)
