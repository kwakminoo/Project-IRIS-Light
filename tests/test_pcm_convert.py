"""48k stereo float → 16k mono int16."""

from __future__ import annotations

import math
from unittest import TestCase

import numpy as np

from iris.audio.pcm_convert import CANONICAL_RATE, rms_int16, to_canonical_pcm


class PcmConvertTests(TestCase):
    def test_48k_stereo_float_to_16k_mono_int16(self) -> None:
        seconds = 0.2
        src_rate = 48000
        n = int(src_rate * seconds)
        t = np.arange(n, dtype=np.float32) / src_rate
        left = 0.4 * np.sin(2 * math.pi * 440 * t)
        right = 0.1 * np.sin(2 * math.pi * 440 * t)
        stereo = np.empty(n * 2, dtype=np.float32)
        stereo[0::2] = left
        stereo[1::2] = right
        pcm = to_canonical_pcm(
            stereo.tobytes(),
            sample_rate=src_rate,
            channels=2,
            sample_format="float32",
        )
        samples = np.frombuffer(pcm, dtype=np.int16)
        expected = int(round(n * CANONICAL_RATE / src_rate))
        self.assertAlmostEqual(samples.size, expected, delta=2)
        rms = rms_int16(pcm)
        self.assertGreater(rms, 0.05)
        self.assertLess(rms, 0.4)
