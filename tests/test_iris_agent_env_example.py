"""The distributed environment template matches Iris Agent settings."""

import unittest
from pathlib import Path


class IrisAgentEnvExampleTests(unittest.TestCase):
    def test_template_uses_agent_names_and_home(self):
        text = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
        self.assertNotIn("Hermes", text)
        self.assertNotIn("IRIS_HERMES_", text)
        for key in (
            "IRIS_AGENT_ENABLED",
            "IRIS_AGENT_BASE_URL",
            "IRIS_AGENT_COMMAND",
            "IRIS_AGENT_API_KEY",
        ):
            self.assertIn(f"{key}=", text)
        self.assertIn(".iris-light/agent/.env", text)
        self.assertNotIn("apply_env_to_hermes.ps1", text)


if __name__ == "__main__":
    unittest.main()
