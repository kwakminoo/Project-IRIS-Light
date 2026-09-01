"""IRIS IDE settings UI checks."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from iris.system.ide_launcher import get_ide_spec, is_ide_installed
from iris.ui.widgets.ide_icons import ide_icon_for


def main() -> None:
    app = QApplication(sys.argv)
    spec = get_ide_spec("iris_ide")
    assert spec is not None
    assert spec.name == "IRIS IDE"
    icon = ide_icon_for("iris_ide", size=40)
    assert not icon.isNull()
    _ = is_ide_installed("iris_ide")
    app.quit()
    print("iris_ide_settings check ok")


if __name__ == "__main__":
    main()
