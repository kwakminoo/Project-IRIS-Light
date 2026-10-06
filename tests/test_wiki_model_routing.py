"""Keep wiki's Hermes route usable when a cloud model needs login."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from iris.ui.window.main_window import MainWindow


class WikiModelRoutingTests(TestCase):
    def window(self, local="local:tools"):
        return SimpleNamespace(
            _remember_blocked_cloud_model=Mock(),
            _first_local_picker_model=Mock(return_value=local),
            _live_activity=Mock(),
            _chat=Mock(),
            _db=None,
        )

    @patch("iris.infrastructure.hermes_errors.cloud_model_blocked_without_login", return_value=True)
    def test_blocked_cloud_uses_available_local_model(self, blocked):
        window = self.window()
        window._chat.select_model_silent.return_value = True
        chosen = MainWindow._guard_cloud_model_selection(window, "remote:cloud")
        self.assertEqual(chosen, "local:tools")
        window._remember_blocked_cloud_model.assert_called_once_with("remote:cloud")
        window._chat.select_model_silent.assert_called_once_with("local:tools")

    @patch("iris.infrastructure.hermes_errors.cloud_model_blocked_without_login", return_value=True)
    def test_no_local_model_keeps_login_prompt(self, blocked):
        window = self.window(local="")
        self.assertEqual(
            MainWindow._guard_cloud_model_selection(window, "remote:cloud"), "remote:cloud"
        )
        window._chat.append_ollama_cloud_login_prompt.assert_called_once()
        window._chat.select_model_silent.assert_not_called()

    @patch("iris.infrastructure.hermes_errors.cloud_model_blocked_without_login", return_value=False)
    def test_authenticated_model_is_preserved(self, blocked):
        window = self.window()
        self.assertEqual(
            MainWindow._guard_cloud_model_selection(window, "remote:cloud"), "remote:cloud"
        )
        window._first_local_picker_model.assert_not_called()
