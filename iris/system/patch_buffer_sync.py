"""Disk-side hook after a successful patch apply.

Theia / IDE buffer notify is not available in-repo. Callers may register a
callback; until a real Theia path is wired this remains a stub — disk updates
do not imply editor buffers are synced.
"""

from __future__ import annotations

from typing import Protocol


class PatchBufferSync(Protocol):
    def on_files_patched(self, root: str, paths: list[str]) -> None:
        """Invoked after disk commit; IDE refresh is the caller's responsibility."""


_hook: PatchBufferSync | None = None


def get_patch_buffer_sync() -> PatchBufferSync | None:
    return _hook


def set_patch_buffer_sync(hook: PatchBufferSync | None) -> None:
    global _hook
    _hook = hook


def notify_files_patched(root: str, paths: list[str]) -> None:
    if _hook is None or not paths:
        return
    _hook.on_files_patched(str(root), list(paths))
