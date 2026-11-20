"""Local filesystem actions guarded by the configured scope (read / search / write)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from iris.runtime.attachment_context import EXCLUDED, _is_link
from iris.storage.local_access_prefs import SYSTEM, load_local_read_scope
from iris.system.control_surface import ActionRegistry, err_result, ok_result

_MAX_READ_BYTES = 1_048_576
_MAX_WRITE_BYTES = 1_048_576
_MAX_SEARCH_ENTRIES = 20_000


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _allowed(window: Any, path: Path) -> bool:
    if load_local_read_scope(getattr(window, "_db", None)) == SYSTEM:
        return True
    try:
        from iris.ui.control_bindings import resolve_bound_work_root

        workspace, error = resolve_bound_work_root(window, {})
        if not error and workspace and _inside(path, Path(workspace)):
            return True
    except Exception:
        pass
    store = getattr(getattr(window, "_chat_session", None), "attachments", None)
    for root in getattr(store, "roots", {}).values():
        attached = Path(root.path)
        if path.resolve() == attached.resolve() or (root.directory and _inside(path, attached)):
            return True
    return False


def _absolute(raw: object, *, directory: bool = False) -> Path:
    path = Path(str(raw or "").strip()).expanduser()
    if not path.is_absolute():
        raise ValueError("절대경로가 필요합니다. Iris는 기본 CWD를 사용하지 않습니다.")
    if directory and not path.is_dir():
        raise NotADirectoryError(str(path))
    if not directory and not path.is_file():
        raise FileNotFoundError(str(path))
    return path


def _absolute_write_target(raw: object) -> Path:
    """Absolute file path for write; parent must exist; target may be new."""
    path = Path(str(raw or "").strip()).expanduser()
    if not path.is_absolute():
        raise ValueError("절대경로가 필요합니다. Iris는 기본 CWD를 사용하지 않습니다.")
    resolved = path.resolve()
    if resolved.exists() and resolved.is_dir():
        raise IsADirectoryError(str(resolved))
    parent = resolved.parent
    if not parent.is_dir():
        raise NotADirectoryError(str(parent))
    return resolved


def register_local_file_actions(window: Any, reg: ActionRegistry) -> None:
    def local_read_file(args: dict[str, Any]) -> dict[str, Any]:
        path = _absolute(args.get("path"))
        if path.suffix.casefold() == ".pdf":
            return err_result(
                "local.read_file",
                "PDF is not readable via local.read_file; "
                "use content.dump_lab_scripts or content.extract",
            )
        if not _allowed(window, path):
            return err_result(
                "local.read_file",
                "설정된 읽기 범위 밖입니다. 설정에서 로컬 읽기 범위를 System으로 바꾸거나 파일을 첨부하세요.",
            )
        limit = max(1, min(int(args.get("max_bytes") or _MAX_READ_BYTES), _MAX_READ_BYTES))
        size = path.stat().st_size
        if size > limit:
            return err_result("local.read_file", f"파일이 읽기 한도({limit} bytes)를 넘습니다.")
        data = path.read_bytes()
        if b"\x00" in data:
            return err_result("local.read_file", "바이너리 파일은 읽을 수 없습니다.")
        return ok_result(
            "local.read_file",
            {"path": str(path), "content": data.decode("utf-8-sig", errors="replace"), "bytes": size},
        )

    def local_write_file(args: dict[str, Any]) -> dict[str, Any]:
        try:
            path = _absolute_write_target(args.get("path"))
        except (IsADirectoryError, NotADirectoryError, OSError, ValueError) as exc:
            return err_result("local.write_file", str(exc))
        if not _allowed(window, path):
            return err_result(
                "local.write_file",
                "설정된 읽기 범위 밖입니다. 설정에서 로컬 읽기 범위를 System으로 바꾸거나 파일을 첨부하세요.",
            )
        if "content" not in args or args.get("content") is None:
            return err_result("local.write_file", "content required")
        content = args.get("content")
        text = content if isinstance(content, str) else str(content)
        data = text.encode("utf-8")
        if len(data) > _MAX_WRITE_BYTES:
            return err_result(
                "local.write_file",
                f"내용이 쓰기 한도({_MAX_WRITE_BYTES} bytes)를 넘습니다.",
            )
        path.write_bytes(data)
        return ok_result(
            "local.write_file",
            {"path": str(path), "bytes": len(data)},
        )

    def local_search_files(args: dict[str, Any]) -> dict[str, Any]:
        root = _absolute(args.get("root"), directory=True)
        if not _allowed(window, root):
            return err_result(
                "local.search_files",
                "설정된 읽기 범위 밖입니다. 검색 루트를 명시하고 로컬 읽기 범위를 확인하세요.",
            )
        query = str(args.get("query") or "").strip().casefold()
        if not query:
            return err_result("local.search_files", "query가 필요합니다.")
        limit = max(1, min(int(args.get("limit") or 50), 200))
        matches: list[str] = []
        visited = 0
        truncated = False
        # ponytail: external search is filename-only; use attachments/project search for content.
        for directory, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(
                d
                for d in dirs
                if d.casefold() not in EXCLUDED and not _is_link(Path(directory) / d)
            )
            for name in sorted(files):
                visited += 1
                if visited > _MAX_SEARCH_ENTRIES:
                    truncated = True
                    break
                candidate = Path(directory) / name
                if _is_link(candidate):
                    continue
                relative = candidate.relative_to(root).as_posix()
                if query in relative.casefold():
                    matches.append(relative)
                    if len(matches) >= limit:
                        truncated = True
                        break
            if truncated:
                break
        return ok_result(
            "local.search_files",
            {"root": str(root), "matches": matches, "count": len(matches), "truncated": truncated},
        )

    reg.register(
        "local.read_file",
        local_read_file,
        summary="Read one absolute local text path within the configured System or Workspace + Attachments scope.",
        risk="low",
    )
    reg.register(
        "local.write_file",
        local_write_file,
        summary=(
            "Write one absolute local text path within the configured System or "
            "Workspace + Attachments scope. Required: path, content."
        ),
        risk="medium",
        confirm_required=True,
    )
    reg.register(
        "local.search_files",
        local_search_files,
        summary="Search filenames under one explicit absolute root within the configured local read scope.",
        risk="low",
    )
