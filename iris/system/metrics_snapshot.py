"""시스템 메트릭 스냅샷."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricsSnapshot:
    """CPU·GPU·메모리 사용률 스냅샷."""

    cpu_percent: float
    memory_percent: float
    gpu_percent: float | None  # None이면 N/A
    gpu_label: str  # "GPU" 또는 "N/A"
