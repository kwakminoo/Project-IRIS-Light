"""T8: model / SpeakTools part contract — templates gated; free HTML is text."""

from __future__ import annotations

import json
import unittest

from iris.core.message_parts import AppPart, CodePart, TextPart, WritingPart
from iris.core.part_contract import (
    IncompleteAppHtmlError,
    gated_app_part,
    parts_from_assistant_payload,
    require_complete_app_html,
    try_parse_part_template,
)


_COMPLETE_HTML = "<!DOCTYPE html><html><body><button>1</button></body></html>"


class FreeProseTests(unittest.TestCase):
    def test_raw_html_in_text_stays_text_part(self) -> None:
        flood = (
            "Here is a calculator:\n"
            f"{_COMPLETE_HTML}\n"
            "Enjoy."
        )
        parts = parts_from_assistant_payload(text=flood)
        self.assertEqual(len(parts), 1)
        self.assertIsInstance(parts[0], TextPart)
        assert isinstance(parts[0], TextPart)
        self.assertIn("<html>", parts[0].markdown)
        self.assertFalse(any(isinstance(p, AppPart) for p in parts))
        self.assertFalse(any(isinstance(p, WritingPart) for p in parts))

    def test_try_parse_free_html_returns_none(self) -> None:
        self.assertIsNone(try_parse_part_template(_COMPLETE_HTML))
        self.assertIsNone(try_parse_part_template("## Draft\n\nHello"))


class WritingTemplateTests(unittest.TestCase):
    def test_iris_writing_json_fence(self) -> None:
        fence = '```iris-writing\n{"title": "Memo", "body": "# Hello"}\n```'
        part = try_parse_part_template(fence)
        self.assertIsInstance(part, WritingPart)
        assert isinstance(part, WritingPart)
        self.assertEqual(part.title, "Memo")
        self.assertEqual(part.body, "# Hello")

    def test_iris_writing_titled_body_in_payload(self) -> None:
        md = "Intro\n\n```iris-writing\nDraft Title\n\nline one\nline two\n```\n"
        parts = parts_from_assistant_payload(text=md)
        writings = [p for p in parts if isinstance(p, WritingPart)]
        self.assertEqual(len(writings), 1)
        self.assertEqual(writings[0].title, "Draft Title")
        self.assertEqual(writings[0].body, "line one\nline two")
        self.assertTrue(any(isinstance(p, TextPart) for p in parts))


class AppTemplateTests(unittest.TestCase):
    def test_iris_app_json_fence(self) -> None:
        payload = json.dumps(
            {"title": "Calc", "html": _COMPLETE_HTML, "display_mode": "pip"}
        )
        fence = f"```iris-app\n{payload}\n```"
        part = try_parse_part_template(fence)
        self.assertIsInstance(part, AppPart)
        assert isinstance(part, AppPart)
        self.assertEqual(part.title, "Calc")
        self.assertEqual(part.display_mode, "pip")
        self.assertIn("<html>", part.html)

    def test_incomplete_iris_app_rejected(self) -> None:
        fence = "```iris-app\nCalc\n\n<div>fragment</div>\n```"
        with self.assertRaises(IncompleteAppHtmlError):
            try_parse_part_template(fence)
        with self.assertRaises(IncompleteAppHtmlError):
            parts_from_assistant_payload(text=fence)

    def test_gated_app_part_rejects_fragment(self) -> None:
        with self.assertRaises(IncompleteAppHtmlError):
            gated_app_part("x", "<div>no root</div>")
        with self.assertRaises(IncompleteAppHtmlError):
            require_complete_app_html("")


class CodeTemplateTests(unittest.TestCase):
    def test_iris_code_json_fence(self) -> None:
        fence = (
            '```iris-code\n'
            '{"language": "python", "source": "print(1)", "filename": "a.py"}\n'
            "```"
        )
        part = try_parse_part_template(fence)
        self.assertIsInstance(part, CodePart)
        assert isinstance(part, CodePart)
        self.assertEqual(part.language, "python")
        self.assertEqual(part.source, "print(1)")
        self.assertEqual(part.filename, "a.py")


class ExplicitPartsTests(unittest.TestCase):
    def test_explicit_parts_list_wins_and_regates_app(self) -> None:
        parts = parts_from_assistant_payload(
            text="ignored html <html></html>",
            parts=[
                {"type": "text", "markdown": "hi"},
                {
                    "type": "app",
                    "title": "Calc",
                    "html": _COMPLETE_HTML,
                    "displayMode": "inline",
                },
            ],
        )
        self.assertEqual(len(parts), 2)
        self.assertIsInstance(parts[0], TextPart)
        self.assertIsInstance(parts[1], AppPart)

    def test_explicit_incomplete_app_raises(self) -> None:
        with self.assertRaises(IncompleteAppHtmlError):
            parts_from_assistant_payload(
                parts=[{"type": "app", "title": "x", "html": "<span/>"}]
            )


if __name__ == "__main__":
    unittest.main()
