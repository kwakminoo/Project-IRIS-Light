"""ActionSpec names must stay derived from command_specs()."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from iris.browser.registry import command_specs, control_action_names


class BrowserRegistrySyncTests(unittest.TestCase):
    def test_control_names_unique(self) -> None:
        names = control_action_names()
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), len(command_specs()))
        self.assertIn("browser.mini_player", names)

    def test_browser_py_has_no_playwright(self) -> None:
        path = Path("iris/ui/control_actions/browser.py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn("playwright", alias.name.lower())
            if isinstance(node, ast.ImportFrom) and node.module:
                self.assertNotIn("playwright", node.module.lower())

    def test_parse_mini_player(self) -> None:
        from iris.browser.registry import parse_command
        from iris.browser.types import MiniPlayer

        cmd = parse_command({"command": "mini_player", "on": True})
        self.assertIsInstance(cmd, MiniPlayer)
        assert isinstance(cmd, MiniPlayer)
        self.assertTrue(cmd.on)


if __name__ == "__main__":
    unittest.main()
