"""Recommended local (Ollama) model catalog — frozen registry + pure joins. No UI/HTTP."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Sequence

CatalogModality = Literal["chat", "vision", "embedding"]

OLLAMA_LIBRARY_URL = "https://ollama.com/library"


@dataclass(frozen=True)
class LocalCatalogEntry:
    pull_name: str
    brand_id: str
    display_name: str
    approx_size_gb: float
    modality: CatalogModality


# Iris setup / vision / history defaults stay in sync with these pull names.
RECOMMENDED_LOCAL_MODELS: tuple[LocalCatalogEntry, ...] = (
    LocalCatalogEntry(
        pull_name="gemma4:e2b",
        brand_id="gemma",
        display_name="Gemma 4 E2B",
        approx_size_gb=1.9,
        modality="chat",
    ),
    LocalCatalogEntry(
        pull_name="llama3.2:3b",
        brand_id="llama",
        display_name="Llama 3.2 3B",
        approx_size_gb=2.0,
        modality="chat",
    ),
    LocalCatalogEntry(
        pull_name="qwen2.5vl:3b",
        brand_id="qwen",
        display_name="Qwen2.5-VL 3B",
        approx_size_gb=3.2,
        modality="vision",
    ),
    LocalCatalogEntry(
        pull_name="bge-m3",
        brand_id="bge",
        display_name="BGE-M3",
        approx_size_gb=1.2,
        modality="embedding",
    ),
)


def brand_id_from_pull_name(name: str) -> str:
    """Family prefix before `:` / digits (gemma4 → gemma, qwen2.5vl → qwen)."""
    base = (name or "").split(":", 1)[0].strip().lower()
    if not base:
        return ""
    m = re.match(r"^([a-z]+)", base)
    return m.group(1) if m else base


def group_by_brand(
    entries: Sequence[LocalCatalogEntry],
) -> list[tuple[str, list[LocalCatalogEntry]]]:
    """Stable brand order = first appearance in ``entries``."""
    order: list[str] = []
    buckets: dict[str, list[LocalCatalogEntry]] = {}
    for entry in entries:
        bid = entry.brand_id or brand_id_from_pull_name(entry.pull_name)
        if bid not in buckets:
            buckets[bid] = []
            order.append(bid)
        buckets[bid].append(entry)
    return [(bid, buckets[bid]) for bid in order]


def _alias_names(name: str) -> frozenset[str]:
    """Exact tag plus bare↔`:latest` aliases. Other tags stay distinct."""
    text = (name or "").strip()
    if not text:
        return frozenset()
    if ":" not in text:
        return frozenset({text, f"{text}:latest"})
    base, tag = text.split(":", 1)
    if tag == "latest":
        return frozenset({text, base})
    return frozenset({text})


def is_installed(
    pull_name: str,
    installed_names: set[str] | Sequence[str],
) -> bool:
    want = _alias_names(pull_name)
    if not want:
        return False
    have: set[str] = set()
    for raw in installed_names:
        have |= _alias_names(str(raw))
    return bool(want & have)


def with_install_flags(
    entries: Sequence[LocalCatalogEntry],
    installed_names: set[str] | Sequence[str],
) -> list[tuple[LocalCatalogEntry, bool]]:
    return [(entry, is_installed(entry.pull_name, installed_names)) for entry in entries]


# Model id with optional :tag — letters/digits/._-/ only (no spaces / shell metachar).
_OLLAMA_CLI_NAME = r"[A-Za-z0-9._/-]+(?::[A-Za-z0-9._/-]+)?"
_OLLAMA_CLI_RE = re.compile(
    rf"^\s*\$?\s*ollama\s+(?:pull|run)\s+({_OLLAMA_CLI_NAME})\s*$",
    re.IGNORECASE,
)


def parse_ollama_cli(text: str) -> str | None:
    """Return pull_name from pasted Ollama CLI, or None if invalid.

    Accepts: ``ollama pull NAME``, ``ollama run NAME``, optional leading ``$``,
    whitespace. NAME = model id with optional ``:tag`` (letters/digits/._-/).
    Rejects empty, multi-arg shells, non-ollama commands.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    m = _OLLAMA_CLI_RE.match(raw)
    if not m:
        return None
    name = (m.group(1) or "").strip()
    return name or None
