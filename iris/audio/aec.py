"""NLMS acoustic echo canceller + far-end playback tap.

ponytail: 1024-tap NLMS, no delay estimator. 잔향이 긴 방은 WebRTC APM으로 교체.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

from iris.audio.pcm_convert import CANONICAL_RATE, to_canonical_pcm


class EchoSource(Protocol):
    def farend_canonical(self, n_bytes: int, delay_ms: int = 180) -> bytes: ...


class NlmsAec:
    """16 kHz float 블록을 받아 near-end residual을 반환."""

    def __init__(self, *, taps: int = 1024, mu: float = 0.45) -> None:
        self._taps = max(32, int(taps))
        self._mu = float(mu)
        self._w = np.zeros(self._taps, dtype=np.float32)
        self._x = np.zeros(self._taps, dtype=np.float32)

    def reset(self) -> None:
        self._w.fill(0.0)
        self._x.fill(0.0)

    def process(self, mic: np.ndarray, ref: np.ndarray) -> np.ndarray:
        n = int(mic.size)
        if n <= 0:
            return mic.astype(np.float32, copy=False)
        if ref.size != n:
            padded = np.zeros(n, dtype=np.float32)
            take = min(n, int(ref.size))
            if take:
                padded[:take] = ref[:take]
            ref = padded
        residual = np.empty(n, dtype=np.float32)
        x = self._x
        w = self._w
        mu = self._mu
        taps = self._taps
        for i in range(n):
            x[1:] = x[:-1]
            x[0] = float(ref[i])
            y = float(np.dot(w, x))
            e = float(mic[i]) - y
            residual[i] = e
            denom = float(np.dot(x, x)) + 1e-6
            w += (mu * e / denom) * x
        self._x = x
        self._w = w
        return residual

    def process_int16(self, mic_pcm: bytes, ref_pcm: bytes) -> bytes:
        mic = _int16_to_float(mic_pcm)
        if mic.size == 0:
            return b""
        ref = _int16_to_float(ref_pcm)
        residual = self.process(mic, ref)
        return _float_to_int16(residual)


class PlaybackTap:
    """스피커에 쓴 PCM을 보관하고, 재생 위치 기준으로 16 kHz far-end를 잘라 준다."""

    def __init__(self, sample_rate: int, *, max_sec: float = 4.0) -> None:
        self._sr = max(1, int(sample_rate))
        self._max_sec = max(1.0, float(max_sec))
        self._pcm = bytearray()
        self._written = 0

    def set_sample_rate(self, sample_rate: int) -> None:
        sr = max(1, int(sample_rate))
        if sr == self._sr:
            return
        self._sr = sr
        self.clear()

    def clear(self) -> None:
        self._pcm.clear()
        self._written = 0

    def push(self, pcm: bytes) -> None:
        if not pcm:
            return
        usable = len(pcm) - (len(pcm) % 2)
        if usable <= 0:
            return
        self._pcm.extend(pcm[:usable])
        self._written += usable // 2
        max_bytes = int(self._sr * 2 * self._max_sec)
        extra = len(self._pcm) - max_bytes
        if extra > 0:
            del self._pcm[: extra - (extra % 2)]

    def farend_canonical(
        self,
        n_bytes: int,
        delay_ms: int = 180,
        *,
        processed_samples: int | None = None,
    ) -> bytes:
        n_out = max(0, int(n_bytes) // 2)
        if n_out <= 0:
            return b""
        n_src = max(1, int(round(n_out * self._sr / CANONICAL_RATE)))
        delay = int(self._sr * max(0, int(delay_ms)) / 1000.0)
        end = int(self._written if processed_samples is None else processed_samples) - delay
        raw = self._slice_samples(end, n_src)
        converted = to_canonical_pcm(raw, sample_rate=self._sr, channels=1, sample_format="int16")
        if len(converted) < n_out * 2:
            converted += b"\x00" * (n_out * 2 - len(converted))
        return converted[: n_out * 2]

    def _slice_samples(self, end_sample: int, n_samples: int) -> bytes:
        n_samples = max(0, int(n_samples))
        out = bytearray(n_samples * 2)
        if n_samples <= 0:
            return bytes(out)
        start = int(end_sample) - n_samples
        ring_n = len(self._pcm) // 2
        ring_end = self._written
        ring_start = ring_end - ring_n
        src_start = max(start, ring_start)
        src_end = min(int(end_sample), ring_end)
        if src_start >= src_end:
            return bytes(out)
        dst_off = (src_start - start) * 2
        src_off = (src_start - ring_start) * 2
        n = (src_end - src_start) * 2
        out[dst_off : dst_off + n] = self._pcm[src_off : src_off + n]
        return bytes(out)


def _int16_to_float(pcm: bytes) -> np.ndarray:
    if not pcm:
        return np.zeros(0, dtype=np.float32)
    usable = len(pcm) - (len(pcm) % 2)
    if usable <= 0:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(pcm[:usable], dtype=np.int16).astype(np.float32) / 32768.0


def _float_to_int16(samples: np.ndarray) -> bytes:
    clipped = np.clip(samples, -1.0, 1.0)
    return np.round(clipped * 32767.0).astype(np.int16).tobytes()
