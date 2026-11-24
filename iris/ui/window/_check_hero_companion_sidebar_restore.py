"""Hero→companion exit must restore left_sidebar visibility.

Regression: from_hero open-folder called left.hide(); companion deactivate
restored right via _restore_assistant_sizes but never left.show(), so home
lost the chat-history sidebar after leaving IDE companion.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    from iris.ui.window.main_window import MainWindow

    win = MainWindow(test_mode=True)
    win.show()
    for _ in range(5):
        app.processEvents()

    # Same hide pair as _apply_iris_ide_hero_layout / from_hero open-folder.
    win._left_sidebar.hide()
    win._assistant_page.right_column.hide()
    assert not win._left_sidebar.isVisible()
    assert not win._assistant_page.right_column.isVisible()

    win._home_assistant_sizes = win._snapshot_assistant_sizes()
    win._restore_assistant_sizes(win._home_assistant_sizes)
    for _ in range(5):
        app.processEvents()

    assert win._left_sidebar.isVisible(), "left_sidebar must show after restore"
    assert win._assistant_page.right_column.isVisible(), (
        "right_column must show after restore"
    )
    win.close()
    app.processEvents()
    print("hero companion sidebar restore OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
