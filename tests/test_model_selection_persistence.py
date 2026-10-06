"""Regression checks for explicit model choice across refresh and process restart."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
import unittest
from PyQt6.QtWidgets import QApplication
from iris.ui.chat.chat_panel import ChatPanel
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
