"""소스 우선 런처 — frozen → .venv hop 로직 자검."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iris.system import source_launch as sl


class SourceLaunchTests(unittest.TestCase):
    def test_looks_like_repo(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.assertTrue(sl.looks_like_repo(root))
        self.assertFalse(sl.looks_like_repo(root / "dist"))

    def test_resolve_venv_python_prefers_pythonw(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / ".venv" / "Scripts"
            scripts.mkdir(parents=True)
            (scripts / "python.exe").write_text("", encoding="utf-8")
            (scripts / "pythonw.exe").write_text("", encoding="utf-8")
            found = sl.resolve_venv_python(root)
            self.assertIsNotNone(found)
            assert found is not None
            self.assertEqual(found.name.lower(), "pythonw.exe")

    def test_should_prefer_source_respects_force_frozen(self) -> None:
        with patch.object(sys, "frozen", True, create=True):
            with patch.dict("os.environ", {}, clear=False):
                # ensure flag off
                import os

                os.environ.pop("IRIS_FORCE_FROZEN", None)
                self.assertTrue(sl.should_prefer_source())
            with patch.dict("os.environ", {"IRIS_FORCE_FROZEN": "1"}):
                self.assertFalse(sl.should_prefer_source())

    def test_reexec_returns_false_when_not_frozen(self) -> None:
        with patch.object(sys, "frozen", False, create=True):
            self.assertFalse(sl.reexec_to_source_if_available())


if __name__ == "__main__":
    unittest.main()
