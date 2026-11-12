"""Local read scope; write permissions are intentionally separate."""

from __future__ import annotations

from iris.storage.database import Database

LOCAL_READ_SCOPE_KEY = "local_read_scope_v1"
WORKSPACE_ATTACHMENTS = "workspace_attachments"
SYSTEM = "system"
LOCAL_READ_SCOPES = (WORKSPACE_ATTACHMENTS, SYSTEM)


def load_local_read_scope(db: Database | None) -> str:
    if db is None:
        return WORKSPACE_ATTACHMENTS
    value = str(db.get_preference(LOCAL_READ_SCOPE_KEY, WORKSPACE_ATTACHMENTS) or "")
    return value if value in LOCAL_READ_SCOPES else WORKSPACE_ATTACHMENTS


def save_local_read_scope(db: Database, scope: str) -> None:
    value = str(scope or "")
    if value not in LOCAL_READ_SCOPES:
        raise ValueError(f"invalid local read scope: {value}")
    db.set_preference(LOCAL_READ_SCOPE_KEY, value)
