from __future__ import annotations

from unittest import TestCase

from iris.audio.tts_pipeline import TtsSentencePump, should_start_tts_synth


class TtsPrefetchDecisionTests(TestCase):
    def test_starts_first_chunk(self) -> None:
        self.assertTrue(
            should_start_tts_synth(
                synthesizing=False, pending_count=3, ready_count=0
            )
        )

    def test_keeps_gpu_busy_when_ready_already_queued(self) -> None:
        self.assertTrue(
            should_start_tts_synth(
                synthesizing=False, pending_count=2, ready_count=3
            )
        )

    def test_waits_when_already_synthesizing(self) -> None:
        self.assertFalse(
            should_start_tts_synth(
                synthesizing=True, pending_count=2, ready_count=0
            )
        )


class TtsSentencePumpTests(TestCase):
    def test_waits_for_sentence_end(self) -> None:
        pump = TtsSentencePump()
        self.assertEqual(pump.feed("안녕하세요"), [])
        self.assertEqual(pump.feed(" 반갑습니다."), ["안녕하세요 반갑습니다."])

    def test_first_sentence_emits_immediately(self) -> None:
        pump = TtsSentencePump()
        self.assertEqual(pump.feed("첫 문장입니다. "), ["첫 문장입니다."])
        self.assertEqual(pump.feed("둘째입니다. 셋째입니다. "), [])
        flushed = pump.flush()
        self.assertEqual(len(flushed), 1)
        self.assertIn("둘째입니다.", flushed[0])
        self.assertIn("셋째입니다.", flushed[0])

    def test_later_chunks_pack_until_flush(self) -> None:
        pump = TtsSentencePump(later_max_chars=30)
        self.assertEqual(pump.feed("하나. "), ["하나."])
        self.assertEqual(pump.feed("두 번째 문장입니다. "), [])
        self.assertEqual(pump.flush(), ["두 번째 문장입니다."])
