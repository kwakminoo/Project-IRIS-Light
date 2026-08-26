"""장치 native PCM → 16 kHz mono signed int16."""

from __future__ import annotations

import math
import struct

import numpy as np

CANONICAL_RATE = 16000
CANONICAL_CHANNELS = 1
CANONICAL_SAMPLE_WIDTH = 2


def _as_float_mono(
    data: bytes,
    *,
    channels: int,
    sample_format: str,
) -> np.ndarray:
    fmt = (sample_format or "int16").lower()
    if not data:
        return np.zeros(0, dtype=np.float32)
    ch = max(1, int(channels or 1))
    if fmt in ("float32", "float"):
        arr = np.frombuffer(data, dtype=np.float32)
    elif fmt in ("int32",):
        arr = np.frombuffer(data, dtype=np.int32).astype(np.float32) / 2147483648.0
    elif fmt in ("uint8",):
        arr = (np.frombuffer(data, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        usable = len(data) - (len(data) % 2)
        arr = np.frombuffer(data[:usable], dtype=np.int16).astype(np.float32) / 32768.0
    if arr.size == 0:
        return arr.astype(np.float32, copy=False)
    if ch > 1:
        n = (arr.size // ch) * ch
        arr = arr[:n].reshape(-1, ch).mean(axis=1)
    return np.asarray(arr, dtype=np.float32)


def _resample(mono: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    src = max(1, int(src_rate or dst_rate))
    dst = max(1, int(dst_rate))
    if src == dst or mono.size == 0:
        return mono
    n_out = max(1, int(round(mono.size * dst / src)))
    x_old = np.linspace(0.0, 1.0, num=mono.size, endpoint=False, dtype=np.float64)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False, dtype=np.float64)
    return np.interp(x_new, x_old, mono.astype(np.float64)).astype(np.float32)


def to_canonical_pcm(
    data: bytes,
    *,
    sample_rate: int,
    channels: int,
    sample_format: str = "int16",
) -> bytes:
    """어떤 장치 포맷이든 16k mono int16 PCM으로 맞춘다."""
    mono = _as_float_mono(data, channels=channels, sample_format=sample_format)
    resampled = _resample(mono, sample_rate, CANONICAL_RATE)
    clipped = np.clip(resampled, -1.0, 1.0)
    pcm = np.round(clipped * 32767.0).astype(np.int16)
    return pcm.tobytes()


def rms_int16(pcm: bytes) -> float:
    if not pcm:
        return 0.0
    usable = len(pcm) - (len(pcm) % 2)
    if usable <= 0:
        return 0.0
    arr = np.frombuffer(pcm[:usable], dtype=np.int16)
    if arr.size == 0:
        return 0.0
    return float(np.sqrt(np.mean((arr.astype(np.float32) / 32768.0) ** 2)))


def rms_to_dbfs(rms: float) -> float:
    if rms <= 1e-9:
        return -96.0
    return float(20.0 * math.log10(max(rms, 1e-9)))


def wav_header(pcm_bytes: bytes, *, sample_rate: int = CANONICAL_RATE, channels: int = 1) -> bytes:
    """pcm int16 + RIFF header."""
    nchannels = max(1, int(channels))
    rate = max(1, int(sample_rate))
    data_size = len(pcm_bytes)
    byte_rate = rate * nchannels * CANONICAL_SAMPLE_WIDTH
    block_align = nchannels * CANONICAL_SAMPLE_WIDTH
    return b"".join(
        (
            b"RIFF",
            struct.pack("<I", 36 + data_size),
            b"WAVE",
            b"fmt ",
            struct.pack("<IHHIIHH", 16, 1, nchannels, rate, byte_rate, block_align, 16),
            b"data",
            struct.pack("<I", data_size),
            pcm_bytes,
        )
    )
