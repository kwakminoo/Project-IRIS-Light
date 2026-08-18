"""PCM 스트리밍 프레이밍 + Speakers를 열기 전 지터 버퍼."""

from __future__ import annotations

import json
from typing import Any

SAMPLE_WIDTH = 2
DEFAULT_SAMPLE_RATE = 24000
# Qwen 12Hz 패킷이 320ms. 이만큼은 모아 두고 Speakers를 연다.
START_MS = 320


def start_bytes(sample_rate: int, start_ms: int = START_MS) -> int:
    rate = max(1, int(sample_rate or DEFAULT_SAMPLE_RATE))
    return max(SAMPLE_WIDTH, int(rate * SAMPLE_WIDTH * (max(0, int(start_ms)) / 1000.0)))


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
