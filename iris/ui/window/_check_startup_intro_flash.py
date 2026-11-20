"""Prove startup flash is gone: first show paints chrome already at opacity 0.

Contract: after MainWindow._arm_boot_intro() then show()+processEvents(),
chat/live/left/right/chrome opacity effects are already 0 (before any later
prepare_hidden re-arm from _begin_boot_sequence).

Product path: _start_runtime_boot → _arm_boot_intro (bind + prepare_hidden)
then later _begin_boot_sequence re-arms + start(). This check calls the same
_arm_boot_intro so product and synthesis share one source of truth.

Does not change intro product path or iris_agent_workers.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QGraphicsOpacityEffect, QWidget


def _opacity_of(widget: QWidget) -> float:
    effect = widget.graphicsEffect()
    if effect is None:
        # No effect → Qt paints the widget fully opaque.
        return 1.0
    if isinstance(effect, QGraphicsOpacityEffect):
        return float(effect.opacity())
    return 1.0


def _sample(win) -> dict[str, float]:
    return {
        "chat": _opacity_of(win._chat),
        "live": _opacity_of(win._live_activity),
        "left": _opacity_of(win._left_sidebar),
        "right": _opacity_of(win._assistant_page.right_column),
        "chrome": _opacity_of(win._drag),
    }


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    from iris.ui.window.main_window import MainWindow

    win = MainWindow(test_mode=True)
    assert win._ui_mode == "normal", win._ui_mode
    # Same arm path production uses in _start_runtime_boot (no 40ms timer).
    win._arm_boot_intro()
    assert win._intro is not None

    win.show()
    for _ in range(3):
        app.processEvents()

    before = _sample(win)
    print("opacity after show+processEvents (before prepare_hidden):", before)

    win._intro.prepare_hidden()
    app.processEvents()
    after = _sample(win)
    print("opacity after prepare_hidden:", after)

    # Anti-flash: already hidden on first paint (armed by _arm_boot_intro).
    bad = {name: val for name, val in before.items() if val > 0.01}
    assert not bad, (
        "startup flash: widgets still opaque after first show()+processEvents() "
        f"before prepare_hidden; measured before={before} after={after}"
    )

    win.close()
    app.processEvents()
    print("startup intro flash check OK")


if __name__ == "__main__":
    main()
