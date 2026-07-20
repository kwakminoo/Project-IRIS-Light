"""백엔드 상태 표시 — Hermes API 헬스 반영."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.config.settings import Settings


def external_backend_status_line(
    settings: "Settings | None",
    *,
    hermes_online: bool = False,
) -> str:
    """상태 칩용 한 줄 요약. OpenClaw는 Light에서 미사용."""
    if settings is None:
        return "OpenClaw (Unavailable) | Hermes (Unavailable)"
    if not settings.hermes_enabled:
        hermes = "Unavailable"
    elif hermes_online:
        hermes = "Connected"
    else:
        hermes = "Offline"
    return f"OpenClaw (Unavailable) | Hermes ({hermes})"
