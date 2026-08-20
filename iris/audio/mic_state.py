"""마이크 하드웨어 상태. UI는 이 enum만 구독한다."""

from __future__ import annotations

from enum import Enum


class MicState(Enum):
    OFF = "off"
    STARTING = "starting"
    LISTENING = "listening"
    SPEECH = "speech"
    SUSPENDED = "suspended"
    ERROR = "error"

    def is_hardware_open(self) -> bool:
        return self in (MicState.STARTING, MicState.LISTENING, MicState.SPEECH, MicState.SUSPENDED)

    def is_listening_ui(self) -> bool:
        """파란 아이콘 — 실제 capture가 열린 청취 계열."""
        return self in (MicState.LISTENING, MicState.SPEECH, MicState.SUSPENDED)
