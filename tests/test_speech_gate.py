"""SpeechGate 최소 검증."""

from __future__ import annotations

from unittest import TestCase

from iris.audio.speech_gate import SpeechGate


class SpeechGateTests(TestCase):
    def test_start_and_end(self) -> None:
        gate = SpeechGate(speech_rms=0.02, start_frames=2, end_frames=2)
        self.assertEqual(gate.feed(0.001), "")
        self.assertEqual(gate.feed(0.05), "")
        self.assertEqual(gate.feed(0.05), "start")
        self.assertTrue(gate.speaking)
        self.assertEqual(gate.feed(0.05), "")
        self.assertEqual(gate.feed(0.001), "")
        self.assertEqual(gate.feed(0.001), "end")
        self.assertFalse(gate.speaking)

    def test_below_threshold_stays_idle(self) -> None:
        gate = SpeechGate(speech_rms=0.05, start_frames=2, end_frames=2)
        self.assertEqual(gate.feed(0.01), "")
        self.assertEqual(gate.feed(0.01), "")
        self.assertFalse(gate.speaking)

    def test_small_noise_is_not_speech(self) -> None:
        gate = SpeechGate(speech_rms=0.02, start_frames=3, end_frames=2, min_speech_frames=4)
        for _ in range(12):
            self.assertEqual(gate.feed(0.004), "")
        self.assertFalse(gate.speaking)

    def test_short_click_is_dropped(self) -> None:
        gate = SpeechGate(speech_rms=0.02, start_frames=2, end_frames=2, min_speech_frames=4)
        self.assertEqual(gate.feed(0.08), "")
        self.assertEqual(gate.feed(0.08), "start")
        self.assertEqual(gate.feed(0.001), "")
        self.assertEqual(gate.feed(0.001), "drop")
        self.assertFalse(gate.speaking)

    def test_silero_rejects_high_rms_nonspeech(self) -> None:
        gate = SpeechGate(speech_rms=0.02, start_frames=2, end_frames=2)
        self.assertEqual(gate.feed(0.2, vad_prob=0.05), "")
        self.assertEqual(gate.feed(0.2, vad_prob=0.05), "")
        self.assertFalse(gate.speaking)

    def test_silero_accepts_speech(self) -> None:
        gate = SpeechGate(speech_rms=0.02, start_frames=2, end_frames=2, min_speech_frames=2)
        self.assertEqual(gate.feed(0.05, vad_prob=0.9), "")
        self.assertEqual(gate.feed(0.05, vad_prob=0.9), "start")
        self.assertTrue(gate.speaking)
