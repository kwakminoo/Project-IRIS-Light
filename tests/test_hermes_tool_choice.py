from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import yaml

from iris.system.iris_agent_tool_choice import (
    load_hermes_tool_choice,
    set_hermes_tool_choice,
)


class HermesToolChoiceTests(TestCase):
    def test_default_is_auto_and_choices_round_trip(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch(
                "iris.infrastructure.iris_agent_credentials.hermes_home",
                return_value=home,
            ):
                self.assertEqual(load_hermes_tool_choice(), "auto")
                changed, _ = set_hermes_tool_choice("required")
                self.assertTrue(changed)
                self.assertEqual(load_hermes_tool_choice(), "required")
                changed, _ = set_hermes_tool_choice("auto")
                self.assertTrue(changed)
                self.assertEqual(load_hermes_tool_choice(), "auto")
                data = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
                self.assertEqual(data["agent"]["tool_choice"], "auto")

    def test_invalid_choice_is_rejected_without_writing(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch(
                "iris.infrastructure.iris_agent_credentials.hermes_home",
                return_value=home,
            ):
                changed, status = set_hermes_tool_choice("always")
                self.assertFalse(changed)
                self.assertIn("invalid", status)
                self.assertFalse((home / "config.yaml").exists())
