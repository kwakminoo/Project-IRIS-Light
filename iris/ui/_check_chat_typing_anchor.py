"""Shared main/IDE scrolling regression check (wheel, drag, typing and streaming)."""
from __future__ import annotations

import unittest

from tests.test_chat_scroll import ChatScrollTests


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ChatScrollTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
