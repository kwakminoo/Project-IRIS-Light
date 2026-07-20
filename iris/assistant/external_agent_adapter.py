"""백엔드 상태 표시용 스텁 — Light에서는 Ollama/Hermes 연결 문자열만."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.config.settings import Settings


def external_backend_status_line(settings: "Settings | None") -> str:
    """상태 칩용 한 줄 요약. OpenClaw는 Light에서 미사용."""
    if settings is None:
        return "OpenClaw (Unavailable) | Hermes (Unavailable)"
    hermes = "Connected" if settings.hermes_enabled else "Unavailable"
    return f"OpenClaw (Unavailable) | Hermes ({hermes})"
