from __future__ import annotations

from unittest import TestCase

from iris.audio.text_normalizer import (
    DEFAULT_PRONUNCIATIONS,
    load_pronunciation_map,
    normalize_tts_text,
    split_tts_sentences,
)


class TextNormalizerTests(TestCase):
    def test_pronunciation_override(self) -> None:
        mapping = load_pronunciation_map('{"API":"에이피아이 변경"}')
        self.assertEqual(mapping["API"], "에이피아이 변경")
        self.assertEqual(mapping["GPU"], DEFAULT_PRONUNCIATIONS["GPU"])

    def test_markdown_and_path_cleanup(self) -> None:
        text = """
        # 제목
        **API** 문서 경로는 C:\\temp\\file.txt 입니다.
        ```python
        print("x")
        ```
        https://example.com
        """
        out = normalize_tts_text(text)
        self.assertIn("에이피아이", out)
        self.assertNotIn("https://", out)
        self.assertNotIn("C:\\", out)
        self.assertNotIn("print", out)

    def test_sentence_split(self) -> None:
        text = "첫 번째 문장입니다. 두 번째 문장은 조금 더 깁니다, 그래서 쉼표 기준으로도 나뉠 수 있습니다! 짧다."
        parts = split_tts_sentences(text, max_chars=35, min_chars=8)
        self.assertGreaterEqual(len(parts), 2)
        self.assertTrue(all(part.strip() for part in parts))

