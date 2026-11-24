"""Boot intro must not leave left/right sidebars at maxWidth=0.

Regression: _arm_boot_intro() ran twice. First prepare_hidden collapsed
panels to maxWidth=0; second bind captured min/max=0 as restore targets;
finish() then restored 0/0 so left/right never reappeared.
"""

from __future__ import annotations

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    from iris.ui.window.main_window import MainWindow

    win = MainWindow(test_mode=True)
    left0 = (win._left_sidebar.minimumWidth(), win._left_sidebar.maximumWidth())
    right0 = (
        win._assistant_page.right_column.minimumWidth(),
        win._assistant_page.right_column.maximumWidth(),
    )
    assert left0[0] > 0 and left0[1] >= left0[0], left0
    assert right0[0] > 0 and right0[1] >= right0[0], right0

    # Product path: __init__ arms, then _start_runtime_boot arms again.
    win._arm_boot_intro()
    win.show()
    for _ in range(5):
        app.processEvents()
    win._runtime_boot_started = False
    win._start_runtime_boot()
    for _ in range(40):
        app.processEvents()
        time.sleep(0.02)

    # Wait for intro motion + models cap.
    deadline = time.monotonic() + 25.0
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.05)
        intro = win._intro
        if intro is not None and getattr(intro, "_completed", False):
            break

    left = (win._left_sidebar.minimumWidth(), win._left_sidebar.maximumWidth())
    right = (
        win._assistant_page.right_column.minimumWidth(),
        win._assistant_page.right_column.maximumWidth(),
    )
    print("design left/right", left0, right0)
    print("after intro left/right", left, right)
    assert left[0] >= left0[0] and left[1] >= left0[1], (
        f"left sidebar collapsed after intro: {left} (design {left0})"
    )
    assert right[0] >= right0[0] and right[1] >= right0[1], (
        f"right column collapsed after intro: {right} (design {right0})"
    )
    assert win._left_sidebar.width() >= left0[0], win._left_sidebar.width()
    assert win._assistant_page.right_column.width() >= right0[0], (
        win._assistant_page.right_column.width()
    )

    win.close()
    app.processEvents()
    print("boot sidebar sizes OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
