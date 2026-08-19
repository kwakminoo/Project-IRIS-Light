"""PCM 스트리밍 프레이밍 + Speakers를 열기 전 지터 버퍼."""

from __future__ import annotations

import json
import os
from typing import Any

SAMPLE_WIDTH = 2
DEFAULT_SAMPLE_RATE = 24000
DEFAULT_START_MS = 100
MIN_START_MS = 60
MAX_START_MS = 1000


def clamp_start_ms(value: int | str | None) -> int:
    """너무 작은 지터 버퍼/비정상 환경값으로 인한 underrun을 막는다."""
    try:
        ms = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        ms = DEFAULT_START_MS
    return max(MIN_START_MS, min(MAX_START_MS, ms))


# 실시간 PCM은 첫 소리가 먼저 중요하다. 필요하면 환경변수로 장치별 튜닝한다.
START_MS = clamp_start_ms(os.getenv("IRIS_TTS_PCM_START_MS", str(DEFAULT_START_MS)))


def start_bytes(sample_rate: int, start_ms: int = START_MS) -> int:
    rate = max(1, int(sample_rate or DEFAULT_SAMPLE_RATE))
    return max(SAMPLE_WIDTH, int(rate * SAMPLE_WIDTH * (clamp_start_ms(start_ms) / 1000.0)))


def should_open_speakers(
    buffered: int,
    sample_rate: int,
    *,
    stream_ended: bool,
    start_ms: int = START_MS,
) -> bool:
    """첫 패킷이 짧아도 스트림이 끝나면 바로 연다. 아니면 START_MS를 채운다."""
    if buffered <= 0:
        return False
    if stream_ended:
        return True
    return buffered >= start_bytes(sample_rate, start_ms)


def encode_event(event: dict[str, Any]) -> bytes:
    return (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")


def parse_event_line(line: str) -> dict[str, Any]:
    raw = (line or "").strip()
    if not raw:
        return {}
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}
