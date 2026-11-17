"""MessagePart domain: parse/serialize round-trip and display MD summary."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from iris.core.message_parts import (
    AppPart,
    CitationPart,
    CodePart,
    DiagramPart,
    ExecutionPart,
    ImagePart,
    TextPart,
    ToolPart,
    WritingPart,
    parse_part,
    parse_parts,
    part_to_dict,
    parts_display_md,
    parts_for_model,
    parts_to_jsonable,
    writing_context_snippets,
)

_SAMPLE_TURN = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "code-review"
    / "scratch-b0-gpt-transcript"
    / "shared"
    / "sample_turn.json"
)


class ParsePartTests(unittest.TestCase):
    def test_unknown_type_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_part({"type": "unknown", "x": 1})

    def test_missing_type_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_part({"markdown": "hi"})

    def test_parse_parts_none_and_empty(self) -> None:
        self.assertEqual(parse_parts(None), [])
        self.assertEqual(parse_parts([]), [])


class RoundTripTests(unittest.TestCase):
    def test_each_variant_round_trips(self) -> None:
        cases = [
            TextPart(markdown="hello **md**"),
            WritingPart(title="draft", body="# body"),
            CodePart(language="python", source="print(1)", filename="a.py"),
            CodePart(language="js", source="1"),
            ToolPart(name="wiki.search", detail="q=iris"),
            ToolPart(name="noop"),
            ImagePart(alt="plot", path="/tmp/x.png"),
            ImagePart(),
            ExecutionPart(stdout="1\n", stderr="", ok=True, language="python"),
            ExecutionPart(stdout="", stderr="boom", ok=False),
            AppPart(title="calc", html="<html></html>", display_mode="pip"),
            AppPart(title="plain", html="<p/>"),
            CitationPart(label="src", url="https://example.com"),
            CitationPart(label="note"),
            DiagramPart(path="/tmp/d.html", kind="workflow", title="Flow"),
            DiagramPart(path="/tmp/x.html"),
        ]
        for part in cases:
            with self.subTest(type=part.type):
                data = part_to_dict(part)
                again = parse_part(data)
                self.assertEqual(again, part)

    def test_app_accepts_displayMode_and_display_mode(self) -> None:
        camel = parse_part(
            {
                "type": "app",
                "title": "t",
                "html": "<p/>",
                "displayMode": "fullscreen",
            }
        )
        snake = parse_part(
            {
                "type": "app",
                "title": "t",
                "html": "<p/>",
                "display_mode": "fullscreen",
            }
        )
        self.assertEqual(camel, AppPart(title="t", html="<p/>", display_mode="fullscreen"))
        self.assertEqual(snake, camel)

    def test_app_serialize_uses_displayMode(self) -> None:
        data = part_to_dict(AppPart(title="t", html="<p/>", display_mode="inline"))
        self.assertEqual(data["displayMode"], "inline")
        self.assertNotIn("display_mode", data)

    def test_sample_turn_parts_round_trip(self) -> None:
        payload = json.loads(_SAMPLE_TURN.read_text(encoding="utf-8"))
        parts = parse_parts(payload["parts"])
        self.assertEqual(len(parts), 4)
        self.assertIsInstance(parts[0], TextPart)
        self.assertIsInstance(parts[1], WritingPart)
        self.assertIsInstance(parts[2], CodePart)
        self.assertIsInstance(parts[3], AppPart)
        assert isinstance(parts[3], AppPart)
        self.assertEqual(parts[3].display_mode, "inline")
        self.assertEqual(parts[3].title, "인라인 계산기")

        jsonable = parts_to_jsonable(parts)
        again = parse_parts(jsonable)
        self.assertEqual(again, parts)


class DisplayMdTests(unittest.TestCase):
    def test_display_md_joins_variants(self) -> None:
        md = parts_display_md(
            [
                TextPart(markdown="Hello"),
                WritingPart(title="Memo", body="line1\nline2"),
                CodePart(language="py", source="x=1", filename="x.py"),
                AppPart(title="Calc", html="<html/>"),
                ToolPart(name="search", detail="q=a"),
                ImagePart(alt="chart", path="c.png"),
                ExecutionPart(stdout="hi", stderr="", ok=True),
                CitationPart(label="doc", url="https://ex"),
                DiagramPart(path="d.html", kind="sequence", title="Seq"),
            ]
        )
        self.assertEqual(
            md,
            "\n\n".join(
                [
                    "Hello",
                    "Memo\n\nline1\nline2",
                    "```py\nx=1\n```",
                    "[app: Calc]",
                    "[tool: search] q=a",
                    "[image: chart] c.png",
                    "[execution: ok]\nhi",
                    "[citation: doc] https://ex",
                    "[diagram: Seq] d.html",
                ]
            ),
        )

    def test_display_md_empty(self) -> None:
        self.assertEqual(parts_display_md([]), "")

    def test_display_md_tool_image_citation_without_extras(self) -> None:
        md = parts_display_md(
            [
                ToolPart(name="noop"),
                ImagePart(),
                CitationPart(label="ref"),
            ]
        )
        self.assertEqual(md, "[tool: noop]\n\n[image]\n\n[citation: ref]")

    def test_writing_context_and_parts_for_model(self) -> None:
        parts = [
            TextPart(markdown="Hello"),
            WritingPart(title="Memo", body="edited draft"),
        ]
        self.assertEqual(writing_context_snippets(parts), "### Memo\nedited draft")
        self.assertIn("edited draft", parts_for_model(parts))
        self.assertEqual(writing_context_snippets([TextPart(markdown="x")]), "")


if __name__ == "__main__":
    unittest.main()
