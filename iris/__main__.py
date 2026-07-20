"""python -m iris 진입점 — UI 셸."""

from __future__ import annotations

import sys

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication


def main() -> None:
    from iris.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Iris Light")
    app.setFont(QFont("Noto Sans KR", 10))
    win = MainWindow()
    win.show()
    app.processEvents()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
