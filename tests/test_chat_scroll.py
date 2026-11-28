"""Exercise the visible H1 transcript in main and IDE companion layouts."""

import sys
import unittest

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()

from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.ui.chat._check_h1_wheel_hit import _check_host_wheel_moves_scroll
from iris.ui.chat._check_transcript_scroll import (
    _check_dom_patch_preserves_hold,
    _check_scroll_hold_follow,
)
from iris.ui.workspaces.workspace_iris_chat import WorkspaceIrisPanel


class ChatScrollTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _APP

    def test_main_and_companion(self):
        _check_scroll_hold_follow(self.app)
        _check_dom_patch_preserves_hold(self.app)
        _check_host_wheel_moves_scroll(self.app)
        for mode in ("Email", "Calendar"):
            with self.subTest(mode=mode):
                window = QWidget()
                window.resize(480, 720)
                workspace = WorkspaceIrisPanel(
                    name_prefix=mode, placeholder="test", parent=window
                )
                QVBoxLayout(window).addWidget(workspace)
                window.show()
                try:
                    _check_scroll_hold_follow(self.app, workspace.chat)
                finally:
                    window.close()
                    window.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
