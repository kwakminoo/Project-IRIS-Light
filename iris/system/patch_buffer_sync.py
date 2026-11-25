"""IDE buffer sync after a successful disk patch apply.

Dirty open editors refuse overwrite. Clean open buffers reload from disk via
Theia ``reloadFromDisk``. ``ide_refresh`` is never reported as success unless
a real sync status is returned.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Protocol

IdeRefresh = str  # "ok" | "conflict" | "unavailable" | "stub"


class PatchBufferSync(Protocol):
    def open_buffer_conflicts(self, root: str, paths: list[str]) -> list[dict[str, Any]]:
        """Dirty open buffers for target paths → structured conflicts (no disk write)."""

    def on_files_patched(self, root: str, paths: list[str]) -> IdeRefresh | None:
        """After disk commit: reload clean buffers. Return real ide_refresh status."""


_hook: PatchBufferSync | None = None
_VALID_REFRESH = frozenset({"ok", "conflict", "unavailable", "stub"})


def get_patch_buffer_sync() -> PatchBufferSync | None:
    return _hook


def set_patch_buffer_sync(hook: PatchBufferSync | None) -> None:
    global _hook
    _hook = hook


def idle_ide_refresh() -> IdeRefresh:
    """Status when no buffer sync ran. ``stub`` only if no hook is registered."""
    return "stub" if _hook is None else "unavailable"


def collect_open_buffer_conflicts(root: str, paths: list[str]) -> list[dict[str, Any]]:
    if _hook is None or not paths:
        return []
    fn = getattr(_hook, "open_buffer_conflicts", None)
    if not callable(fn):
        return []
    out = fn(str(root), list(paths))
    return list(out) if out else []


def notify_files_patched(root: str, paths: list[str]) -> IdeRefresh | None:
    """Invoke hook after disk commit. Returns status, or None when no hook."""
    if _hook is None or not paths:
        return None
    raw = _hook.on_files_patched(str(root), list(paths))
    if isinstance(raw, str) and raw in _VALID_REFRESH and raw != "stub":
        return raw
    # Hook present but did not report a real sync outcome.
    return "unavailable"


def _norm_path(value: str) -> str:
    return os.path.normcase(os.path.normpath(str(value or "").strip()))


def path_matches_editor(root: str, rel: str, editor_path: str) -> bool:
    """True when an open-editor path refers to root/rel (abs or suffix)."""
    rel_n = str(rel or "").replace("\\", "/").lstrip("/")
    if not rel_n:
        return False
    abs_target = _norm_path(str(Path(root) / rel_n))
    ep = _norm_path(editor_path)
    if not ep:
        return False
    if ep == abs_target:
        return True
    ep_slash = ep.replace("\\", "/")
    want = rel_n.replace("\\", "/").lower()
    got = ep_slash.lower()
    return got.endswith("/" + want) or got.endswith(want)


class IdePatchBufferSync:
    """Product PatchBufferSync backed by IrisIdeClient."""

    def __init__(self, client_factory: Callable[[], Any | None]) -> None:
        self._client_factory = client_factory

    def open_buffer_conflicts(self, root: str, paths: list[str]) -> list[dict[str, Any]]:
        client = self._safe_client()
        if client is None:
            return []
        try:
            payload = client.get_open_editors()
        except Exception:
            return []
        editors = payload.get("editors") if isinstance(payload, dict) else None
        if not isinstance(editors, list):
            return []
        conflicts: list[dict[str, Any]] = []
        seen: set[str] = set()
        for ed in editors:
            if not isinstance(ed, dict) or not ed.get("dirty"):
                continue
            epath = str(ed.get("path") or ed.get("uri") or "")
            for rel in paths:
                key = str(rel)
                if key in seen:
                    continue
                if path_matches_editor(root, rel, epath):
                    seen.add(key)
                    conflicts.append(
                        {
                            "path": key,
                            "reason": "open editor buffer is dirty",
                        }
                    )
        return conflicts

    def on_files_patched(self, root: str, paths: list[str]) -> IdeRefresh:
        client = self._safe_client()
        if client is None:
            return "unavailable"
        abs_paths: list[str] = []
        for rel in paths:
            try:
                abs_paths.append(str((Path(root) / rel).resolve()))
            except OSError:
                abs_paths.append(str(Path(root) / rel))
        try:
            result = client.reload_from_disk(abs_paths)
        except Exception:
            return "unavailable"
        if not isinstance(result, dict):
            return "unavailable"
        rows = result.get("results")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and row.get("reason") == "dirty":
                    return "conflict"
                if isinstance(row, dict) and row.get("reloaded") is False and not row.get("skipped"):
                    return "conflict"
        refused = result.get("refused")
        if isinstance(refused, int) and refused > 0:
            return "conflict"
        return "ok"

    def _safe_client(self) -> Any | None:
        try:
            return self._client_factory()
        except Exception:
            return None
