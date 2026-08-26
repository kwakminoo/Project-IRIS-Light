"""재생 단계 피치 시프트 — 길이는 유지하고 음높이만 올린다."""

from __future__ import annotations

import time
from unittest import TestCase

import numpy as np

from iris.audio.pitch_shift import MAX_SEMITONES, PitchShifter, semitones_to_ratio
from iris.audio.voice_effects import VoiceAssistantEffect

SR = 24000


def _tone(freq: float, seconds: float = 2.0, amp: float = 0.35) -> bytes:
    t = np.arange(int(SR * seconds)) / SR
    wave = np.sin(2 * np.pi * freq * t) + 0.4 * np.sin(4 * np.pi * freq * t)
    wave = wave / np.max(np.abs(wave)) * amp
    return (wave * 32767).astype("<i2").tobytes()


def _dominant_hz(pcm: bytes, skip_sec: float = 0.4) -> float:
    """기본주파수. 링버퍼가 차기 전 구간은 빼고 정상 상태만 본다."""
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float64)
    skip = int(SR * skip_sec)
    if len(samples) > skip * 2:
        samples = samples[skip:]
    spectrum = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
    freqs = np.fft.rfftfreq(len(samples), 1 / SR)
    audible = freqs > 50
    return float(freqs[audible][np.argmax(spectrum[audible])])


def _stream(shifter: PitchShifter, pcm: bytes, chunk: int = 960) -> bytes:
    return b"".join(shifter.process(pcm[i : i + chunk]) for i in range(0, len(pcm), chunk))


class SemitoneMathTests(TestCase):
    def test_octave_is_double(self) -> None:
        self.assertAlmostEqual(semitones_to_ratio(6.0), 2.0 ** 0.5, places=6)
        self.assertAlmostEqual(semitones_to_ratio(0.0), 1.0, places=9)

    def test_range_is_clamped(self) -> None:
        self.assertEqual(semitones_to_ratio(99.0), semitones_to_ratio(MAX_SEMITONES))
        self.assertEqual(semitones_to_ratio(-99.0), semitones_to_ratio(-MAX_SEMITONES))


class PitchShiftTests(TestCase):
    def test_raises_fundamental_frequency(self) -> None:
        for semitones in (2.0, 3.5, 5.0):
            with self.subTest(semitones=semitones):
                out = _stream(PitchShifter(SR, semitones), _tone(200.0))
                expected = 200.0 * semitones_to_ratio(semitones)
                self.assertLess(abs(_dominant_hz(out) - expected) / expected, 0.06)

    def test_lowers_when_negative(self) -> None:
        out = _stream(PitchShifter(SR, -2.0), _tone(200.0))
        self.assertLess(_dominant_hz(out), 195.0)

    def test_length_is_preserved(self) -> None:
        """길이가 바뀌면 스트리밍 재생에서 말이 빨라지거나 끊긴다."""
        src = _tone(200.0, 1.0)
        for chunk in (256, 960, 4096):
            with self.subTest(chunk=chunk):
                self.assertEqual(len(_stream(PitchShifter(SR, 3.0), src, chunk)), len(src))

    def test_chunk_size_does_not_change_result(self) -> None:
        """청크 크기는 호출 측 사정이다. 결과가 달라지면 안 된다."""
        src = _tone(180.0)
        results = [_dominant_hz(_stream(PitchShifter(SR, 3.0), src, c)) for c in (256, 960, 4096)]
        self.assertLess(max(results) - min(results), 6.0)

    def test_chunk_larger_than_ring_buffer(self) -> None:
        """청크가 링버퍼보다 크면 아직 읽어야 할 과거가 덮어써진다 — 내부에서 쪼갠다."""
        src = _tone(180.0)
        whole = _dominant_hz(PitchShifter(SR, 3.0).process(src))
        piecemeal = _dominant_hz(_stream(PitchShifter(SR, 3.0), src, 960))
        self.assertLess(abs(whole - piecemeal), 6.0)

    def test_zero_semitones_passes_through_untouched(self) -> None:
        src = _tone(200.0, 0.2)
        self.assertEqual(PitchShifter(SR, 0.0).process(src), src)

    def test_no_clipping_on_full_scale_input(self) -> None:
        loud = (np.ones(SR // 2) * 32767).astype("<i2").tobytes()
        out = PitchShifter(SR, 4.0).process(loud)
        peak = int(np.max(np.abs(np.frombuffer(out, dtype="<i2").astype(np.int32))))
        self.assertLessEqual(peak, 32767)

    def test_silence_stays_silent(self) -> None:
        out = PitchShifter(SR, 4.0).process(bytes(SR))
        self.assertEqual(int(np.max(np.abs(np.frombuffer(out, dtype="<i2").astype(np.int32)))), 0)

    def test_odd_trailing_byte_is_preserved(self) -> None:
        src = _tone(200.0, 0.1) + b"\x01"
        self.assertEqual(len(PitchShifter(SR, 3.0).process(src)), len(src))

    def test_empty_input(self) -> None:
        self.assertEqual(PitchShifter(SR, 3.0).process(b""), b"")

    def test_reset_clears_tail(self) -> None:
        shifter = PitchShifter(SR, 4.0)
        shifter.process(_tone(200.0, 0.3))
        shifter.reset()
        out = shifter.process(bytes(SR // 4))
        self.assertEqual(int(np.max(np.abs(np.frombuffer(out, dtype="<i2").astype(np.int32)))), 0)

    def test_fast_enough_for_realtime(self) -> None:
        """속도가 최우선인 기능이다. 20ms 청크 처리가 20ms를 넘으면 못 쓴다."""
        audio = _tone(200.0, 5.0)
        shifter = PitchShifter(SR, 3.0)
        started = time.perf_counter()
        _stream(shifter, audio, 960)
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 5.0 / 10)  # 최소 10배 실시간


class VoiceEffectPitchTests(TestCase):
    def test_pitch_applies_even_when_fx_disabled(self) -> None:
        """AI 음향 효과와 톤은 별개 설정이다."""
        effect = VoiceAssistantEffect(SR)
        effect.configure(enabled=False, intensity=0.0)
        effect.set_pitch(4.0)
        src = _tone(200.0)
        out = b"".join(effect.process(src[i : i + 960]) for i in range(0, len(src), 960))
        self.assertGreater(_dominant_hz(out), 235.0)

    def test_pitch_zero_with_fx_off_is_passthrough(self) -> None:
        effect = VoiceAssistantEffect(SR)
        effect.configure(enabled=False, intensity=0.0)
        src = _tone(200.0, 0.2)
        self.assertEqual(effect.process(src), src)

    def test_length_preserved_with_fx_and_pitch(self) -> None:
        effect = VoiceAssistantEffect(SR)
        effect.configure(enabled=True, intensity=0.75)
        effect.set_pitch(3.0)
        src = _tone(200.0, 0.5)
        out = b"".join(effect.process(src[i : i + 960]) for i in range(0, len(src), 960))
        self.assertEqual(len(out), len(src))

    def test_sample_rate_change_keeps_pitch(self) -> None:
        effect = VoiceAssistantEffect(SR)
        effect.set_pitch(3.0)
        effect.set_sample_rate(16000)
        self.assertAlmostEqual(effect.pitch_semitones, 3.0, places=6)
