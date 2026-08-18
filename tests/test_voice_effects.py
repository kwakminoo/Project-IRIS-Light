from __future__ import annotations

from array import array
from unittest import TestCase

from iris.audio.voice_effects import VoiceAssistantEffect


def _pcm(samples: list[int]) -> bytes:
    return array("h", samples).tobytes()


def _samples(pcm: bytes) -> list[int]:
    values = array("h")
    values.frombytes(pcm)
    return list(values)


class VoiceAssistantEffectTests(TestCase):
    def test_disabled_is_byte_identical(self) -> None:
        raw = _pcm([0, 1234, -2345, 32767, -32768])
        effect = VoiceAssistantEffect(24000)
        self.assertEqual(effect.process(raw), raw)

    def test_enabled_is_stream_safe_and_bounded(self) -> None:
        raw = _pcm(([28000, -28000, 12000, -12000] * 700))
        effect = VoiceAssistantEffect(24000)
        effect.configure(enabled=True, intensity=0.55)
        output = effect.process(raw)

        self.assertEqual(len(output), len(raw))
        self.assertNotEqual(output, raw)
        self.assertTrue(all(-32768 <= sample <= 32767 for sample in _samples(output)))

    def test_split_stream_matches_one_shot_and_reset_drops_old_echo(self) -> None:
        raw = _pcm(([0, 9000, -4000, 2000] * 800))
        whole = VoiceAssistantEffect(24000)
        whole.configure(enabled=True, intensity=0.35)
        expected = whole.process(raw)

        split = VoiceAssistantEffect(24000)
        split.configure(enabled=True, intensity=0.35)
        cut = 1024
        actual = split.process(raw[:cut]) + split.process(raw[cut:])
        self.assertEqual(actual, expected)

        split.reset()
        self.assertEqual(split.process(raw), expected)
