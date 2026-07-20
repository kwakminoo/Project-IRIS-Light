"""마이크 RMS ↔ UI 표시 레벨 변환 (continuous_listen·설정 게이지 공통)."""

from __future__ import annotations

# RMS를 0~1 게이지로 매핑할 때 사용하는 배율 (continuous_listen과 동일)
MIC_LEVEL_SCALE = 12.0


def rms_to_display_level(rms: float) -> float:
    """원시 RMS를 0~1 표시 레벨로 변환한다."""
    return min(1.0, max(0.0, rms * MIC_LEVEL_SCALE))


def display_level_to_speech_rms(level: float) -> float:
    """게이지 감도 막대 위치(0~1)를 음성 인식 임계 RMS로 변환한다."""
    clamped = min(1.0, max(0.0, level))
    return clamped / MIC_LEVEL_SCALE


def speech_rms_to_display_level(speech_rms: float) -> float:
    """저장된 ALWAYS_LISTEN_SPEECH_RMS를 게이지 막대 위치로 변환한다."""
    return rms_to_display_level(speech_rms)
