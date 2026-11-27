"""Read-only local filesystem actions guarded by the configured scope."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from iris.storage.local_access_prefs import SYSTEM, load_local_read_scope
from iris.system.control_surface import ActionRegistry, err_result, ok_result

_MAX_READ_BYTES = 1_048_576


def _inside(path: Path, root: Path) -> bool:
    from iris.system.execution_policy import check_path_allowed

    return check_path_allowed(root, path, write=False).allowed


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
    from iris.runtime.attachment_store import AttachmentStore
    from iris.ui.control_bindings import trusted_execution_context

    scope = trusted_execution_context(window)
    for root in getattr(store, "roots", {}).values():
        attached = Path(root.path)
        if isinstance(store, AttachmentStore) and (
            not store.in_workspace(root, scope.workspace_root)
            or attached.resolve() != root.resolved_path
            or scope.effective_session_id() != str(getattr(window._chat_session, "conversation_id", ""))
        ):
            continue
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


def register_local_file_actions(window: Any, reg: ActionRegistry) -> None:
    def local_read_file(args: dict[str, Any]) -> dict[str, Any]:
        from iris.system.file_patch import read_text_range

        path = _absolute(args.get("path"))
        if not _allowed(window, path):
            return err_result(
                "local.read_file",
                "설정된 읽기 범위 밖입니다. 설정에서 로컬 읽기 범위를 System으로 바꾸거나 파일을 첨부하세요.",
            )
        limit = max(1, min(int(args.get("max_bytes") or _MAX_READ_BYTES), _MAX_READ_BYTES))
        start = args.get("start_line")
        end = args.get("end_line")
        # Full-file path without range keeps hard size fail (compat with prior contract).
        if start is None and end is None and path.stat().st_size > limit:
            return err_result("local.read_file", f"파일이 읽기 한도({limit} bytes)를 넘습니다.")
        try:
            payload = read_text_range(
                path,
                start_line=int(start) if start is not None else None,
                end_line=int(end) if end is not None else None,
                max_bytes=limit,
            )
        except (OSError, ValueError) as exc:
            return err_result("local.read_file", str(exc))
        return ok_result("local.read_file", payload)

    def local_search_files(args: dict[str, Any]) -> dict[str, Any]:
        from iris.system.file_patch import search_files

        root = _absolute(args.get("root"), directory=True)
        if not _allowed(window, root):
            return err_result(
                "local.search_files",
                "설정된 읽기 범위 밖입니다. 검색 루트를 명시하고 로컬 읽기 범위를 확인하세요.",
            )
        query = str(args.get("query") or "").strip()
        if not query:
            return err_result("local.search_files", "query가 필요합니다.")
        mode = str(args.get("mode") or "name").strip().lower() or "name"
        if mode not in ("name", "content"):
            return err_result("local.search_files", "mode must be name or content")
        try:
            payload = search_files(
                root,
                query,
                mode=mode,  # type: ignore[arg-type]
                limit=int(args.get("limit") or 50),
            )
        except (OSError, ValueError) as exc:
            return err_result("local.search_files", str(exc))
        return ok_result("local.search_files", payload)

    reg.register(
        "local.read_file",
        local_read_file,
        summary=(
            "Read one absolute local text path within the configured System or Workspace + "
            "Attachments scope (optional start_line/end_line; max_bytes)."
        ),
        risk="low",
    )
    reg.register(
        "local.search_files",
        local_search_files,
        summary=(
            "Search under one absolute root within the local read scope. "
            "mode=name (default) matches paths; mode=content matches file text."
        ),
        risk="low",
    )
