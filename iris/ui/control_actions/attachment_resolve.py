"""Shared attachment_id → absolute file / URL resolve for content and wiki actions."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from iris.runtime.attachment_store import AttachmentIdResolve, AttachmentStore
from iris.system.control_surface import err_result

_NEED_ATTACHMENT_ID = (
    "attachment_id가 필요합니다. attachment.list 또는 get_state의 id를 쓰세요."
)


def store_from_window(window: Any) -> AttachmentStore:
    session = getattr(window, "_chat_session", None)
    store = getattr(session, "attachments", None)
    if store is None:
        raise ValueError("현재 채팅의 첨부 저장소를 찾을 수 없습니다.")
    return store


def resolve_attachment_id(
    window: Any, token: str, action: str
) -> tuple[str | None, dict[str, Any] | None]:
    """Map uuid/unique basename via store.resolve_id; return (id, None) or (None, err)."""
    resolved: AttachmentIdResolve = store_from_window(window).resolve_id(token)
    if resolved.id:
        return resolved.id, None
    payload: dict[str, Any] = {}
    if resolved.candidates:
        payload["candidates"] = list(resolved.candidates)
    return None, err_result(
        action,
        resolved.error or "attachment_id를 확인할 수 없습니다.",
        payload or None,
    )


def _is_http_url(raw: str) -> bool:
    s = (raw or "").strip()
    if not s:
        return False
    try:
        parsed = urlparse(s)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def resolve_content_source(
    window: Any,
    args: dict[str, Any],
    action: str,
    *,
    allow_url: bool = True,
    allow_absolute: bool = True,
) -> tuple[str | None, dict[str, Any] | None]:
    """Prefer attachment_id → absolute Path; else URL; else absolute existing file.

    Returns (source_string, None) or (None, err_result dict).
    """
    aid = str(args.get("attachment_id") or args.get("attachment") or "").strip()
    if aid:
        resolved, err = resolve_attachment_id(window, aid, action)
        if err is not None:
            return None, err
        try:
            path = store_from_window(window).absolute_file_path(str(resolved))
        except ValueError as exc:
            return None, err_result(action, str(exc))
        return str(path), None

    legacy = str(
        args.get("source") or args.get("path") or args.get("url") or ""
    ).strip()
    if not legacy:
        return None, err_result(action, _NEED_ATTACHMENT_ID)

    if allow_url and _is_http_url(legacy):
        return legacy, None

    if allow_absolute:
        path = Path(legacy).expanduser()
        if path.is_absolute() and path.is_file():
            return str(path), None

    return None, err_result(action, _NEED_ATTACHMENT_ID)
