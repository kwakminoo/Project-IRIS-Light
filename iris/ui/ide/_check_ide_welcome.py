"""IDE welcome layer self-check."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from iris.storage.ide_recent_folders import truncate_path_middle
from iris.ui.ide.iris_ide_welcome_layer import IrisIdeWelcomeLayer
from iris.ui.workspaces.iris_ide_window import IrisIdeWindow


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert "..." in truncate_path_middle("C:/very/long/path/" + ("x" * 80), 40)
    layer = IrisIdeWelcomeLayer()
    assert layer.btn_open_folder is not None
    assert layer._title.text() == "IRIS IDE"
    w = IrisIdeWindow()
    w.show_welcome()
    assert w.is_welcome_visible()
    print("ide_welcome ok")
    app.quit()


if __name__ == "__main__":
    main()
