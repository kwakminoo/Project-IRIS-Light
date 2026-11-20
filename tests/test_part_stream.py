"""PartStreamBuffer: str chunks → open/delta/close; incomplete fence → code."""

from __future__ import annotations

import unittest

from iris.core.message_parts import CodePart, TextPart
from iris.core.part_stream import PartClose, PartDelta, PartOpen, PartStreamBuffer


def _types(events):
    out = []
    for ev in events:
        if isinstance(ev, PartOpen):
            out.append(("open", ev.type, ev.part_id))
        elif isinstance(ev, PartDelta):
            out.append(("delta", ev.part_id, ev.text))
        elif isinstance(ev, PartClose):
            out.append(("close", ev.part_id))
        else:
            out.append(("?", ev))
    return out


class PartStreamSequenceTests(unittest.TestCase):
    def test_prose_fence_prose_event_sequence(self) -> None:
        buf = PartStreamBuffer()
        e1 = buf.push("Hello ")
        self.assertTrue(any(isinstance(x, PartOpen) and x.type == "text" for x in e1))
        self.assertTrue(any(isinstance(x, PartDelta) and x.text == "Hello " for x in e1))
        self.assertFalse(any(isinstance(x, PartClose) for x in e1))

        e2 = buf.push("```python\nprint(1)\n")
        # Prose closes; code opens with source delta; code stays open.
        self.assertTrue(any(isinstance(x, PartClose) for x in e2))
        self.assertTrue(any(isinstance(x, PartOpen) and x.type == "code" for x in e2))
        self.assertTrue(
            any(isinstance(x, PartDelta) and "print(1)" in x.text for x in e2)
        )
        self.assertFalse(
            any(
                isinstance(x, PartClose) and x.part_id.startswith("code")
                for x in e2
            )
        )

        e3 = buf.push("```\nMore prose")
        self.assertTrue(
            any(
                isinstance(x, PartClose) and x.part_id.startswith("code")
                for x in e3
            )
        )
        self.assertTrue(any(isinstance(x, PartOpen) and x.type == "text" for x in e3))
        self.assertTrue(
            any(isinstance(x, PartDelta) and "More prose" in x.text for x in e3)
        )

        e4 = buf.finish()
        self.assertTrue(any(isinstance(x, PartClose) for x in e4))

        parts = buf.parts()
        self.assertEqual(len(parts), 3)
        self.assertIsInstance(parts[0], TextPart)
        assert isinstance(parts[0], TextPart)
        self.assertEqual(parts[0].markdown, "Hello ")
        self.assertIsInstance(parts[1], CodePart)
        assert isinstance(parts[1], CodePart)
        self.assertEqual(parts[1].language, "python")
        self.assertEqual(parts[1].source, "print(1)")
        self.assertIsInstance(parts[2], TextPart)
        assert isinstance(parts[2], TextPart)
        self.assertEqual(parts[2].markdown.lstrip("\n"), "More prose")

    def test_incomplete_fence_finish_closes_as_code(self) -> None:
        buf = PartStreamBuffer()
        buf.push("Intro\n")
        buf.push("```js\nconst x = 1;\n")
        # No closing fence.
        events = buf.finish()
        self.assertTrue(
            any(
                isinstance(x, PartClose) and x.part_id.startswith("code")
                for x in events
            ),
            msg=_types(events),
        )
        parts = buf.parts()
        self.assertEqual(len(parts), 2)
        self.assertIsInstance(parts[0], TextPart)
        self.assertIsInstance(parts[1], CodePart)
        assert isinstance(parts[1], CodePart)
        self.assertEqual(parts[1].language, "js")
        self.assertIn("const x = 1;", parts[1].source)
        # Snapshot matches closed parts (no dangling open).
        self.assertIsNone(buf._open)

    def test_parts_snapshot_matches_during_open_code(self) -> None:
        buf = PartStreamBuffer()
        buf.push("```py\na=1\n")
        snap = buf.parts()
        self.assertEqual(len(snap), 1)
        self.assertIsInstance(snap[0], CodePart)
        assert isinstance(snap[0], CodePart)
        self.assertEqual(snap[0].language, "py")
        self.assertIn("a=1", snap[0].source)
        buf.finish()
        final = buf.parts()
        self.assertEqual(len(final), 1)
        self.assertIsInstance(final[0], CodePart)
        assert isinstance(final[0], CodePart)
        self.assertIn("a=1", final[0].source)


if __name__ == "__main__":
    unittest.main()
