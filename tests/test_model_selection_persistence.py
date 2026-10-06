"""Regression checks for explicit model choice across refresh and process restart."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
import unittest
from PyQt6.QtWidgets import QApplication
from iris.infrastructure.ollama_client import OllamaModelInfo
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.model_picker_menu import split_picker_groups
from iris.storage.database import Database
from iris.storage.model_prefs import load_selected_model, save_selected_model
from tempfile import TemporaryDirectory
from pathlib import Path

APP = QApplication.instance() or QApplication(sys.argv)

class ModelSelectionTests(unittest.TestCase):
    def test_refresh_preserves_choice_without_user_signal(self):
        panel = ChatPanel()
        signals = []
        panel.model_changed.connect(signals.append)
        panel.set_models(["claude", "gpt"], selected="claude")
        panel.set_models(["gpt"], selected="claude")
        self.assertEqual(panel.current_model(), "claude")
        panel.set_models([])
        self.assertEqual(panel.current_model(), "claude")
        self.assertEqual(signals, [])
        panel.set_models(["claude", "gpt"])
        panel._select_model_runtime("gpt")
        self.assertEqual(signals, ["gpt"])
        panel.set_models(["claude", "gpt"])
        self.assertEqual(panel.current_model(), "gpt")
        panel.deleteLater()

    def test_local_section_selects_runtime(self):
        panel = ChatPanel()
        signals = []
        panel.model_changed.connect(signals.append)
        panel.set_models(
            [
                OllamaModelInfo(name="llama3.2:latest"),
                OllamaModelInfo(name="gemma4:31b-cloud", catalog_name="gemma4 cloud"),
                OllamaModelInfo(
                    name="api:lm:foo",
                    catalog_name="LM Studio · foo",
                    endpoint="http://127.0.0.1:1234/v1",
                ),
                OllamaModelInfo(
                    name="api:nv:meta/llama",
                    catalog_name="NVIDIA · llama",
                    endpoint="https://integrate.api.nvidia.com/v1",
                ),
            ],
            selected="gemma4:31b-cloud",
        )
        local, ollama, _brands, singles = split_picker_groups(panel._picker_models)
        self.assertEqual([m.runtime for m in local], ["api:lm:foo", "llama3.2:latest"])
        self.assertEqual([m.runtime for m in ollama], ["gemma4:31b-cloud"])
        self.assertEqual([m.runtime for m in singles], ["api:nv:meta/llama"])
        panel._select_model_runtime("llama3.2:latest")
        self.assertEqual(panel.current_model(), "llama3.2:latest")
        self.assertEqual(signals, ["llama3.2:latest"])
        panel._select_model_runtime("api:lm:foo")
        self.assertEqual(panel.current_model(), "api:lm:foo")
        self.assertEqual(signals, ["llama3.2:latest", "api:lm:foo"])
        panel.deleteLater()

    def test_database_reopen(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "prefs.db"
            for model in ("claude", "gpt"):
                db = Database(path)
                save_selected_model(db, model)
                db.close()
                db = Database(path)
                self.assertEqual(load_selected_model(db), model)
                db.close()
