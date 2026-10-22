from __future__ import annotations

import unittest

from iris.browser.intent import format_browser_reply, match_browser_intent
from iris.browser.registry import parse_command
from iris.browser.types import Media
from iris.browser.youtube import page_block_reason


class BrowserIntentTests(unittest.TestCase):
    def test_youtube_any_song(self) -> None:
        intent = match_browser_intent("유튜브에서 노래 하나 아무거나 틀어줘")
        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertEqual(intent.kind, "play")
        self.assertEqual(intent.control, "browser.search")
        self.assertEqual(intent.args["engine"], "youtube")
        self.assertTrue(intent.args["play"])
        self.assertEqual(intent.args["query"], "음악")

    def test_named_track(self) -> None:
        intent = match_browser_intent("아이유 밤편지 틀어줘")
        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertEqual(intent.args["query"], "아이유 밤편지")

    def test_chat_does_not_drive_browser(self) -> None:
        for text in ("유튜브가 뭐야", "음악을 좋아해", "오늘 날씨 어때", "코드 리뷰해줘"):
            self.assertIsNone(match_browser_intent(text), text)

    def test_pause_resume(self) -> None:
        self.assertEqual(match_browser_intent("영상 일시정지 해줘").kind, "pause")
        self.assertEqual(match_browser_intent("다시 재생해줘").kind, "resume")

    def test_reply_does_not_claim_speakers(self) -> None:
        intent = match_browser_intent("유튜브에서 음악 틀어줘")
        assert intent is not None
        text = format_browser_reply(
            intent,
            {"ok": True, "result": {"browser_playing": True, "title": "x", "media": {"playing": True}}},
        )
        self.assertIn("재생을 시작", text)
        self.assertIn("스피커", text)

    def test_parse_media(self) -> None:
        cmd = parse_command({"action": "browser.media", "media": "pause"})
        self.assertIsInstance(cmd, Media)
        assert isinstance(cmd, Media)
        self.assertEqual(cmd.action, "pause")

    def test_page_block_reason(self) -> None:
        self.assertEqual(page_block_reason("https://consent.youtube.com/ml"), "consent")
        self.assertEqual(page_block_reason("https://www.google.com/sorry/index"), "captcha")
        self.assertEqual(page_block_reason("https://www.youtube.com/watch?v=x"), "")

    def test_intent_module_does_not_import_tts(self) -> None:
        import iris.browser.intent as mod

        self.assertNotIn("iris.audio", getattr(mod, "__dict__", {}))
        from pathlib import Path

        src = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("tts", src.lower())
        self.assertNotIn("sovits", src.lower())


if __name__ == "__main__":
    unittest.main()
