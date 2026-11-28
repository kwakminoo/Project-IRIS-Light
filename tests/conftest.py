"""Qt test-session bootstrap; must run before any test creates QApplication."""

import sys

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready


ensure_qt_webengine_ready()

from PyQt6.QtWidgets import QApplication


_APP = QApplication.instance() or QApplication(sys.argv)
