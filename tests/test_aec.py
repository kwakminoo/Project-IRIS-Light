"""NLMS AEC + playback tap."""

from __future__ import annotations

from unittest import TestCase

import numpy as np

from iris.audio.aec import NlmsAec, PlaybackTap
from iris.audio.pcm_convert import CANONICAL_RATE, rms_int16


def _sine(n: int, hz: float, amp: float = 0.4, sr: int = CANONICAL_RATE) -> np.ndarray:
    t = np.arange(n, dtype=np.float32) / float(sr)
    return (amp * np.sin(2.0 * np.pi * hz * t)).astype(np.float32)


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x))))


class NlmsAecTests(TestCase):
    def test_cancels_linear_echo(self) -> None:
        n = 6000
        ref = _sine(n, 440.0, 0.5)
        delay = 48
        mic = np.zeros(n, dtype=np.float32)
        mic[delay:] = 0.65 * ref[:-delay]
        aec = NlmsAec(taps=256, mu=0.55)
        residual = aec.process(mic, ref)
        self.assertLess(_rms(residual[-1500:]), _rms(mic[-1500:]) * 0.35)

    def test_keeps_near_end_during_double_talk(self) -> None:
        n = 6000
        ref = _sine(n, 440.0, 0.45)
        speech = _sine(n, 880.0, 0.5)
        delay = 32
        echo = np.zeros(n, dtype=np.float32)
        echo[delay:] = 0.6 * ref[:-delay]
        mic = echo + speech
        aec = NlmsAec(taps=256, mu=0.5)
        residual = aec.process(mic, ref)
        self.assertGreater(_rms(residual[-1500:]), _rms(speech[-1500:]) * 0.25)

    def test_process_int16_roundtrip_length(self) -> None:
        mic = (np.clip(_sine(800, 300.0), -1, 1) * 32767).astype(np.int16).tobytes()
        ref = (np.clip(_sine(800, 300.0, 0.2), -1, 1) * 32767).astype(np.int16).tobytes()
        out = NlmsAec(taps=64).process_int16(mic, ref)
        self.assertEqual(len(out), len(mic))


class PlaybackTapTests(TestCase):
    def test_farend_matches_pushed_pcm(self) -> None:
        tap = PlaybackTap(CANONICAL_RATE)
        pcm = (np.clip(_sine(1600, 200.0), -1, 1) * 32767).astype(np.int16).tobytes()
        tap.push(pcm)
        far = tap.farend_canonical(len(pcm), delay_ms=0)
        self.assertEqual(len(far), len(pcm))
        self.assertGreater(rms_int16(far), 0.05)

    def test_delay_shifts_window_toward_silence_at_start(self) -> None:
        tap = PlaybackTap(CANONICAL_RATE)
        pcm = (np.clip(_sine(1600, 200.0), -1, 1) * 32767).astype(np.int16).tobytes()
        tap.push(pcm)
        delayed = tap.farend_canonical(3200, delay_ms=80)
        self.assertEqual(len(delayed), 3200)
        head = rms_int16(delayed[:800])
        tail = rms_int16(delayed[-800:])
        self.assertLess(head, tail)
