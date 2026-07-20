"""GPU 사용률 수집 — nvidia-smi → Windows PDH → N/A."""

from __future__ import annotations

import re
import subprocess
from typing import Optional

_GPU_PDH_AVAILABLE: bool | None = None


def read_gpu_utilization() -> tuple[Optional[float], str]:
    """
    GPU 사용률(%)과 라벨 반환.
    측정 불가 시 (None, "N/A").
  """
    nvidia = _read_nvidia_smi()
    if nvidia is not None:
        return nvidia, "GPU"
    pdh = _read_windows_pdh_gpu()
    if pdh is not None:
        return pdh, "GPU"
    return None, "N/A"


def _read_nvidia_smi() -> Optional[float]:
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            shell=False,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    first = proc.stdout.strip().splitlines()[0].strip()
    match = re.search(r"(\d+(?:\.\d+)?)", first)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    return max(0.0, min(100.0, value))


def _read_windows_pdh_gpu() -> Optional[float]:
    global _GPU_PDH_AVAILABLE
    if _GPU_PDH_AVAILABLE is False:
        return None
    try:
        import win32pdh  # type: ignore[import-untyped]
    except ImportError:
        _GPU_PDH_AVAILABLE = False
        return None

    query_paths = (
        r"\GPU Engine(*)\Utilization Percentage",
        r"\GPU Adapter Memory(*)\Dedicated Usage",
    )
    for path in query_paths:
        value = _pdh_query_avg(path, win32pdh)
        if value is not None:
            _GPU_PDH_AVAILABLE = True
            return value
    _GPU_PDH_AVAILABLE = False
    return None


def _pdh_query_avg(path: str, win32pdh: object) -> Optional[float]:
    try:
        query = win32pdh.OpenQuery()  # type: ignore[attr-defined]
        counter = win32pdh.AddCounter(query, path, None)  # type: ignore[attr-defined]
        win32pdh.CollectQueryData(query)  # type: ignore[attr-defined]
        import time

        time.sleep(0.15)
        win32pdh.CollectQueryData(query)  # type: ignore[attr-defined]
        _, values = win32pdh.GetFormattedCounterArray(  # type: ignore[attr-defined]
            counter, win32pdh.PDH_FMT_DOUBLE  # type: ignore[attr-defined]
        )
        win32pdh.CloseQuery(query)  # type: ignore[attr-defined]
        nums = [float(v) for v in values if isinstance(v, (int, float))]
        if not nums:
            return None
        return max(0.0, min(100.0, sum(nums) / len(nums)))
    except Exception:
        return None
