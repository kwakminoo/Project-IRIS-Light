"""Startup model discovery must preserve selection and never raise in a Qt slot."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from PyQt6.QtWidgets import QApplication
from iris.ui.chat.chat_panel import ChatPanel

class StartupModelStatusTests(unittest.TestCase):
    def test_status_during_discovery_preserves_model_and_unblocks_signals(self):
        app = QApplication.instance() or QApplication([])
        panel = ChatPanel()
        panel.set_models(['claude'], selected='claude')
        signals = []
        panel.model_changed.connect(signals.append)
        for status in ('Loading cloud models', 'No connection'):
            panel.set_model_status(status)
            self.assertEqual(panel.current_model(), 'claude')
            self.assertFalse(panel._model_combo.signalsBlocked())
        self.assertEqual(signals, [])
        panel.close()
