"""IRIS IDE window smoke check."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QRect

from iris.system.ide_tiler import compute_tile_rects, tiles_are_flush
from iris.ui.window.frameless_chrome import FramelessShell
from iris.ui.workspaces.iris_ide_window import IRIS_IDE_TITLE, IrisIdeWindow


def _check_folder_open_avoids_frameless_modal() -> None:
    """폴더 대화상자는 parent=None. 슬롯은 set_embedded 전에 HWND를 만들지 않는다."""
    root = Path(__file__).resolve().parents[2]
    hero = (root / "iris/ui/ide/iris_ide_hero_overlay.py").read_text(encoding="utf-8")
    welcome = (root / "iris/ui/ide/iris_ide_welcome_layer.py").read_text(encoding="utf-8")
    ide = (root / "iris/ui/control_actions/ide.py").read_text(encoding="utf-8")
    main_src = (root / "iris/ui/window/main_window.py").read_text(encoding="utf-8")
    chat = (root / "iris/ui/chat/chat_panel.py").read_text(encoding="utf-8")
    for label, src in (("hero", hero), ("welcome", welcome)):
        assert "getExistingDirectory(self" not in src, label
        assert "getExistingDirectory(None" in src, label
    assert "getExistingDirectory(window" not in ide
    assert "getOpenFileNames(window" not in ide
    assert "getExistingDirectory(None" in ide
    photos = chat[chat.index("def _pick_photos") : chat.index("def _pick_files")]
    files = chat[chat.index("def _pick_files") : chat.index("def _on_paths_attached")]
    folder = chat[chat.index("def _pick_folder") : chat.index("def _on_skill")]
    for label, body in (("photos", photos), ("files", files)):
        assert "getOpenFileNames(" in body, label
        assert "None," in body.split("getOpenFileNames(", 1)[1], label
        assert "getOpenFileNames(self" not in body, label
        assert "\n            self," not in body.split("getOpenFileNames(", 1)[1].split(")", 1)[0], label
    assert "getExistingDirectory(None" in folder
    assert "getExistingDirectory(self" not in folder
    start = main_src.index("def _open_iris_ide_folder")
    body = main_src[start : main_src.index("\n    def _activate_companion_tile")]
    assert "apply_frameless_chrome()" not in body
    assert "show_window=False" in body
    assert "show_ide_not_installed_dialog(None" in body
    hide_at = body.index("win.hide()")
    assert body.index("show_window=False") > hide_at
    assert body.index("IDE already launching") < hide_at


def main() -> None:
    _check_folder_open_avoids_frameless_modal()
    from PyQt6.QtWidgets import QApplication
    import sys

    from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)
    work = QRect(0, 0, 1000, 800)
    tiles = compute_tile_rects(work, ide_ratio=0.8)
    assert tiles.ide.width() == 800
    assert tiles.iris.width() == 200
    assert tiles_are_flush(tiles.ide, tiles.iris)
    w = IrisIdeWindow()
    assert w.windowFlags() & Qt.WindowType.FramelessWindowHint
    shell = w.centralWidget()
    assert isinstance(shell, FramelessShell)
    assert len(shell._grips) == 8
    w.resize(800, 600)
    w.show()
    app.processEvents()
    body = shell._content
    assert body is not None
    assert body.geometry().x() == shell._margin and body.geometry().y() == shell._margin
    assert not body.geometry().intersects(shell._grips[4].geometry())
    assert not hasattr(w, "_caption")
    assert w.maximize_button_global_rect().isNull()
    w.show_loading()
    assert w.is_opening()
    assert not w.is_theia_loaded()
    assert w.windowTitle() == IRIS_IDE_TITLE
    app.quit()
    print("iris_ide_window check ok")


if __name__ == "__main__":
    main()
