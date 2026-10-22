"""Browser workspace split self-check (calendar-style + companion stay)."""

from __future__ import annotations

import sys


def main() -> int:
    import os
    import tempfile
    from pathlib import Path

    os.environ.setdefault("IRIS_BROWSER_PROFILE_NAME", f"iris-browser-ws-{os.getpid()}")
    os.environ.setdefault(
        "IRIS_BROWSER_PROFILE",
        str(Path(tempfile.gettempdir()) / f"iris-browser-ws-{os.getpid()}"),
    )
    from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

    ensure_qt_webengine_ready()
    from PyQt6.QtWidgets import QApplication

    from iris.ui.window.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    w = MainWindow(test_mode=True)
    w.resize(1280, 800)
    w.show()
    app.processEvents()
    panel = w.show_browser_workspace()
    app.processEvents()
    assert w._workspace_mode == "browser"
    assert w._workspace_stack.currentWidget() is w._browser_page
    assert w._browser_page.browser_panel() is panel
    assert w._workspace_chat.is_mounted()
    assert w._iris_ide_window is None or not w._iris_ide_window.isVisible()
    sizes = w._browser_page._splitter.sizes()
    assert sizes[0] >= 400 and sizes[1] >= 300, sizes
    w._browser_page._splitter.setSizes([sizes[0] - 80, sizes[1] + 80])
    app.processEvents()
    resized = w._browser_page._splitter.sizes()
    assert resized[0] > 0 and resized[1] > 0, resized
    assert resized != sizes, (sizes, resized)
    panel.ensure_view()
    assert panel.tab_count() >= 1
    adopted = panel._adopt_popup()
    assert adopted is not None
    assert panel.tab_count() == 2
    assert panel.current_tab_index() == 0
    panel._on_new_tab()
    app.processEvents()
    assert panel.tab_count() == 3, panel.tab_count()

    w._ui_mode = "ide_companion"
    ide_panel = w.show_browser_workspace()
    app.processEvents()
    assert w._ui_mode == "ide_companion", "browser must not exit companion"
    ide = w._iris_ide_window
    assert ide is not None
    assert ide_panel is panel
    assert ide.is_browser_visible() or ide._stack.currentWidget() is panel
    ide.return_from_browser()
    app.processEvents()
    assert not ide.is_browser_visible()
    w.show_browser_workspace()
    app.processEvents()
    assert ide.is_browser_visible() or ide._stack.currentWidget() is panel
    w.close()
    print("browser workspace ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
