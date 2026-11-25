"""IDE buffer sync after a successful disk patch apply.

Dirty open editors refuse overwrite. Clean open buffers reload from disk via
Theia ``reloadFromDisk``. ``ide_refresh`` is never reported as success unless
a real sync status is returned.

Probe failures (disconnected / query error) are fail-closed: they are never
reported as an empty conflict list.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Protocol
from urllib.parse import unquote, urlparse

IdeRefresh = str  # "ok" | "conflict" | "unavailable" | "stub"

BufferProbeStatus = Literal[
    "none",
    "dirty",
    "ide_disconnected",
    "ide_query_failed",
    "version_mismatch",
    "workspace_mismatch",
]

@dataclass(frozen=True)
class BufferProbeResult:
    """Structured open-buffer probe. ``conflicts`` empty only when status is ``none``."""

    status: BufferProbeStatus
    conflicts: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.status == "none" and self.conflicts:
            object.__setattr__(self, "conflicts", ())
        if self.status != "none" and not self.conflicts:
            object.__setattr__(
                self,
                "conflicts",
                ({"path": "", "reason": _default_reason(self.status)},),
            )

    @property
    def ok(self) -> bool:
        return self.status == "none"

    @property
    def refuse_apply(self) -> bool:
        return self.status != "none"


def _default_reason(status: BufferProbeStatus) -> str:
    return {
        "dirty": "open editor buffer is dirty",
        "ide_disconnected": "IDE bridge disconnected",
        "ide_query_failed": "IDE open-editors query failed",
        "version_mismatch": "open editor version mismatch",
        "workspace_mismatch": "IDE workspace does not match patch root",
        "none": "",
    }.get(status, status)


class PatchBufferSync(Protocol):
    def open_buffer_conflicts(
        self, root: str, paths: list[str]
    ) -> BufferProbeResult | list[dict[str, Any]]:
        """Probe open buffers for target paths.

        Return ``BufferProbeResult`` (preferred) or a legacy conflict list.
        Empty list means verified clean only when the implementation actually
        queried the IDE; ``IdePatchBufferSync`` never returns ``[]`` on probe failure.
        """

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


def normalize_buffer_probe(raw: Any) -> BufferProbeResult:
    """Coerce hook output into a structured probe result."""
    if isinstance(raw, BufferProbeResult):
        return raw
    if isinstance(raw, dict) and "status" in raw:
        status = str(raw.get("status") or "").strip()
        allowed: set[str] = {
            "none",
            "dirty",
            "ide_disconnected",
            "ide_query_failed",
            "version_mismatch",
            "workspace_mismatch",
        }
        if status not in allowed:
            return BufferProbeResult(
                "ide_query_failed",
                ({"path": "", "reason": "invalid buffer probe status"},),
            )
        conflicts_raw = raw.get("conflicts")
        conflicts: tuple[dict[str, Any], ...] = ()
        if isinstance(conflicts_raw, list):
            conflicts = tuple(c for c in conflicts_raw if isinstance(c, dict))
        return BufferProbeResult(status, conflicts)  # type: ignore[arg-type]
    if isinstance(raw, list):
        # Legacy hooks: non-empty = dirty; empty = verified clean.
        rows = tuple(c for c in raw if isinstance(c, dict))
        if rows:
            return BufferProbeResult("dirty", rows)
        return BufferProbeResult("none")
    return BufferProbeResult(
        "ide_query_failed",
        ({"path": "", "reason": "invalid buffer probe result"},),
    )


def probe_open_buffers(root: str, paths: list[str]) -> BufferProbeResult:
    """Probe IDE open buffers. No hook → ``none`` (no IDE to conflict with)."""
    if _hook is None or not paths:
        return BufferProbeResult("none")
    fn = getattr(_hook, "open_buffer_conflicts", None)
    if not callable(fn):
        return BufferProbeResult("none")
    try:
        out = fn(str(root), list(paths))
    except Exception:
        return BufferProbeResult(
            "ide_query_failed",
            ({"path": "", "reason": "IDE open-editors probe raised"},),
        )
    return normalize_buffer_probe(out)


def collect_open_buffer_conflicts(root: str, paths: list[str]) -> list[dict[str, Any]]:
    """Return conflict rows. Empty only when probe status is ``none``."""
    probe = probe_open_buffers(root, paths)
    if probe.status == "none":
        return []
    return [dict(row) for row in probe.conflicts]


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


def _editor_fs_path(editor_path: str) -> str:
    raw = str(editor_path or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("file:"):
        parsed = urlparse(raw)
        path = unquote(parsed.path or "")
        # file:///C:/foo → /C:/foo on Windows; strip leading slash before drive.
        if os.name == "nt" and len(path) >= 3 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        return path
    return raw


def path_matches_editor(root: str, rel: str, editor_path: str) -> bool:
    """True when an open-editor path is the same file as root/rel.

    Prefers absolute equality under the patch root. Cross-workspace suffix
    matches (e.g. other_project/app.py vs this_root/app.py) are rejected.
    """
    rel_n = str(rel or "").replace("\\", "/").lstrip("/")
    if not rel_n:
        return False
    try:
        root_resolved = Path(root).resolve()
    except OSError:
        root_resolved = Path(root)
    abs_target = _norm_path(str(root_resolved / Path(*rel_n.split("/"))))
    ep = _norm_path(_editor_fs_path(editor_path))
    if not ep:
        return False
    if ep == abs_target:
        return True
    root_n = _norm_path(str(root_resolved))
    # Also accept forward slash after normpath on Windows (normpath may keep \).
    prefixes = (root_n + os.sep, root_n + "/", root_n + "\\")
    if not any(ep.startswith(p) for p in prefixes) and ep != root_n:
        return False
    try:
        rel_got = Path(ep).relative_to(Path(root_n))
    except ValueError:
        # normcase mismatch on relative_to — compare string suffix under root.
        for p in prefixes:
            if ep.startswith(p):
                got = ep[len(p) :].replace("\\", "/")
                return got == rel_n.replace("\\", "/")
        return False
    return rel_got.as_posix().lower() == rel_n.replace("\\", "/").lower()


def _probe_workspace(client: Any, root: str) -> BufferProbeResult | None:
    get_ws = getattr(client, "get_workspace", None)
    if not callable(get_ws):
        return None
    try:
        payload = get_ws()
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    ws_root = payload.get("root") or payload.get("workspace")
    if not ws_root:
        return None
    try:
        patch_root = _norm_path(str(Path(root).resolve()))
        ide_root = _norm_path(str(Path(str(ws_root)).resolve()))
    except OSError:
        patch_root = _norm_path(root)
        ide_root = _norm_path(str(ws_root))
    if patch_root != ide_root:
        return BufferProbeResult(
            "workspace_mismatch",
            (
                {
                    "path": "",
                    "reason": "IDE workspace does not match patch root",
                    "ide_workspace": str(ws_root),
                    "patch_root": str(root),
                },
            ),
        )
    return None


class IdePatchBufferSync:
    """Product PatchBufferSync backed by IrisIdeClient."""

    def __init__(self, client_factory: Callable[[], Any | None]) -> None:
        self._client_factory = client_factory

    def open_buffer_conflicts(self, root: str, paths: list[str]) -> BufferProbeResult:
        client = self._safe_client()
        if client is None:
            return BufferProbeResult(
                "ide_disconnected",
                ({"path": "", "reason": "IDE bridge disconnected"},),
            )
        ws_miss = _probe_workspace(client, root)
        if ws_miss is not None:
            return ws_miss
        try:
            payload = client.get_open_editors()
        except Exception as exc:
            return BufferProbeResult(
                "ide_query_failed",
                ({"path": "", "reason": f"IDE open-editors query failed: {exc}"},),
            )
        if not isinstance(payload, dict):
            return BufferProbeResult(
                "ide_query_failed",
                ({"path": "", "reason": "IDE open-editors payload invalid"},),
            )
        editors = payload.get("editors")
        if not isinstance(editors, list):
            return BufferProbeResult(
                "ide_query_failed",
                ({"path": "", "reason": "IDE open-editors missing editors list"},),
            )

        dirty: list[dict[str, Any]] = []
        version_hits: list[dict[str, Any]] = []
        seen: set[str] = set()
        for ed in editors:
            if not isinstance(ed, dict):
                continue
            epath = str(ed.get("path") or ed.get("uri") or "")
            matched_rels = [
                str(rel)
                for rel in paths
                if str(rel) not in seen and path_matches_editor(root, rel, epath)
            ]
            if not matched_rels:
                continue
            base_v = ed.get("base_version", ed.get("disk_version"))
            cur_v = ed.get("version")
            version_stale = False
            if base_v is not None and cur_v is not None:
                try:
                    version_stale = int(base_v) != int(cur_v)
                except (TypeError, ValueError):
                    version_stale = str(base_v) != str(cur_v)
            if ed.get("dirty"):
                for key in matched_rels:
                    seen.add(key)
                    dirty.append(
                        {
                            "path": key,
                            "reason": "open editor buffer is dirty",
                        }
                    )
            elif version_stale:
                for key in matched_rels:
                    seen.add(key)
                    version_hits.append(
                        {
                            "path": key,
                            "reason": "open editor version mismatch",
                        }
                    )

        if dirty:
            return BufferProbeResult("dirty", tuple(dirty))
        if version_hits:
            return BufferProbeResult("version_mismatch", tuple(version_hits))
        # Verified query succeeded with no matching dirty/version conflicts.
        return BufferProbeResult("none")

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
