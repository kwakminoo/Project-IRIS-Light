"""Browser workspace self-check: dedicated shell occupant + companion stay."""

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
    assert w._ui_mode == "dedicated_browser"
    assert w._body_stack.currentWidget() is w._unified_shell
    assert w._unified_shell.left_browser() is panel
    assert panel.isVisible()
    assert w._companion_page.is_mounted()
    mounted = getattr(w._companion_page, "_mounted", None) or []
    assert w._chat in mounted, "dedicated browser must remount the same ChatPanel"
    assert hasattr(w._chat, "set_presenting")
    assert hasattr(w._drag, "set_tts_enabled")
    assert w._iris_ide_window is None or not w._iris_ide_window.isVisible()
    assert not getattr(w, "_iris_ide_unified", False)
    sizes = w._unified_shell._split.sizes()
    total = sum(sizes)
    assert sizes[0] == int(total * 0.8) or abs(sizes[0] / total - 0.8) < 0.05, sizes
    w._unified_shell._split.setSizes([sizes[0] - 80, sizes[1] + 80])
    app.processEvents()
    assert w._unified_shell._split.sizes() != sizes
    assert panel.view() is not None
    assert w._unified_shell.left_browser() is panel
    w._exit_dedicated_browser()
    app.processEvents()
    assert w._ui_mode == "normal"
    panel = w.show_browser_workspace()
    app.processEvents()
    assert w._ui_mode == "dedicated_browser"
    assert w._body_stack.currentWidget() is w._unified_shell
    assert panel.view() is not None
    panel.ensure_view()
    assert panel.tab_count() >= 1
    adopted = panel._adopt_popup()
    assert adopted is not None and panel.tab_count() == 2
    panel._on_new_tab()
    app.processEvents()
    assert panel.tab_count() == 3, panel.tab_count()

    from iris.browser.session import get_browser_session
    from iris.browser.types import PanelHost, docked_site

    get_browser_session().note_view_host(PanelHost(site="dedicated"))
    w._ui_mode = "ide_companion"
    w._clear_leftover_dedicated_host()
    assert docked_site(get_browser_session().view_host()) == "ide_internal", "leftover dedicated must be cleared"
    ide_panel = w.show_browser_workspace()
    app.processEvents()
    assert w._ui_mode == "ide_companion", "browser must not exit companion"
    ide = w._iris_ide_window
    assert ide is w._iris_ide_window and ide is not None
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
