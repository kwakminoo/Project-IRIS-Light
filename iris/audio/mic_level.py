"""마이크 RMS ↔ UI 표시 레벨 변환 (continuous_listen·설정 게이지 공통)."""

from __future__ import annotations

from iris.audio.pcm_convert import rms_to_dbfs

# 구 설정값 호환: 슬라이더 0..1 ↔ speech_rms
MIC_LEVEL_SCALE = 12.0
_DBFS_FLOOR = -56.0
_DBFS_CEIL = -6.0


def rms_to_display_level(rms: float) -> float:
    """canonical RMS를 로그(dBFS) 게이지 0..1로 변환한다."""
    dbfs = rms_to_dbfs(max(0.0, float(rms)))
    span = _DBFS_CEIL - _DBFS_FLOOR
    return min(1.0, max(0.0, (dbfs - _DBFS_FLOOR) / span))


def display_level_to_speech_rms(level: float) -> float:
    """게이지 감도 막대 위치(0~1)를 음성 인식 임계 RMS로 변환한다."""
    clamped = min(1.0, max(0.0, level))
    return clamped / MIC_LEVEL_SCALE


def speech_rms_to_display_level(speech_rms: float) -> float:
    """저장된 ALWAYS_LISTEN_SPEECH_RMS를 게이지 막대 위치로 변환한다."""
    return min(1.0, max(0.0, float(speech_rms) * MIC_LEVEL_SCALE))
