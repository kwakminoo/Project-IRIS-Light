"""Lexical app recommendations from composer context (no LLM).

Owns: token overlap ranking for App Directory entries.
Does not: render UI, call models, or mutate the directory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from iris.apps.directory import AppDirectoryEntry

_TOKEN_RE = re.compile(r"[0-9A-Za-z]+|[가-힣]+")


@dataclass(frozen=True)
class RecommendQuery:
    context: str


def _tokens(text: str) -> frozenset[str]:
    return frozenset(m.group(0).casefold() for m in _TOKEN_RE.finditer(text or ""))


def _score(entry: AppDirectoryEntry, tokens: frozenset[str]) -> int:
    if not tokens:
        return 0
    hay = _tokens(f"{entry.id} {entry.title} {entry.summary}")
    return len(tokens & hay)


def recommend_apps(
    context: str,
    entries: list[AppDirectoryEntry],
    *,
    limit: int = 3,
) -> list[AppDirectoryEntry]:
    """Rank entries by token overlap with context. Empty / zero → []."""
    tokens = _tokens(context)
    if not tokens or limit <= 0:
        return []
    scored = [(_score(e, tokens), e) for e in entries]
    positive = [(s, e) for s, e in scored if s > 0]
    if not positive:
        return []
    positive.sort(key=lambda pair: (-pair[0], pair[1].id))
    return [e for _, e in positive[:limit]]
