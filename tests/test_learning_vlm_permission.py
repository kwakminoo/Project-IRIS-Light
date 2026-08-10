"""VLM policy / permission / privacy / runtime 단위 테스트."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from iris.learning.permission import policy_for
from iris.learning.privacy import is_password_control_os, redact_key_if_needed
from iris.learning.vlm_policy import is_learning_capable_vision, model_name_suggests_vision
from iris.storage.database import Database
from iris.storage.learning_prefs import LearningPreferences, load_learning_preferences, save_learning_preferences


class TestVlmPolicy(unittest.TestCase):
    def test_vision_name(self) -> None:
        self.assertTrue(model_name_suggests_vision("llava:13b"))
        self.assertTrue(model_name_suggests_vision("qwen2.5-vl:7b"))
        self.assertFalse(model_name_suggests_vision("llama3.2:3b"))

    def test_learning_capable(self) -> None:
        ok, _ = is_learning_capable_vision(name="llava:13b", size=8e9, supports_vision=True)
        self.assertTrue(ok)
        ok, reason = is_learning_capable_vision(
            name="llama3.2:3b", size=2e9, supports_vision=False
        )
        self.assertFalse(ok)
        self.assertIn("비전", reason)


class TestPermission(unittest.TestCase):
    def test_levels(self) -> None:
        low = policy_for("low")
        self.assertFalse(low.record_keyboard)
        unr = policy_for("unrestricted")
        self.assertTrue(unr.allow_unrestricted_os_control)
        self.assertFalse(unr.executor_confirm_required)


class TestLearningPrefs(unittest.TestCase):
    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "p.db")
            prefs = LearningPreferences(permission_level="high", vlm_model="llava:7b")
            save_learning_preferences(db, prefs)
            loaded = load_learning_preferences(db)
            self.assertEqual(loaded.permission_level, "high")
            self.assertEqual(loaded.vlm_model, "llava:7b")
            db._conn.close()


class TestPrivacy(unittest.TestCase):
    def test_redact(self) -> None:
        self.assertEqual(
            redact_key_if_needed("a", window_title="Login", is_password_control=False),
            "[REDACTED]",
        )
        # OS call should not crash
        _ = is_password_control_os()


if __name__ == "__main__":
    unittest.main()
