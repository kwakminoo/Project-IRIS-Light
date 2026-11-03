"""백엔드 상태 표시 — Iris Agent 헬스 반영."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.config.settings import Settings


def external_backend_status_line(
    settings: "Settings | None",
    *,
    hermes_online: bool = False,
) -> str:
    """상태 칩용 한 줄 요약."""
    if settings is None:
        return "Iris Agent (Unavailable)"
    if not settings.hermes_enabled:
        status = "Unavailable"
    elif hermes_online:
        status = "Connected"
    else:
        status = "Offline"
    return f"Iris Agent ({status})"
