"""IRIS IDE companion 80:20 — A구조(슬롯 자식 orb) + 타일 계약."""

from __future__ import annotations

import inspect
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from iris.system.ide_tiler import (
    compute_tile_rects,
    read_qt_window_rect,
    tiles_are_flush,
    tiles_have_overlap,
    tile_iris_ide_and_iris,
    work_area_for,
)
from iris.ui.widgets.visualizer import Visualizer
from iris.ui.window.cyberspace_background import CyberspaceBackground
from iris.ui.window.frameless_chrome import FramelessShell
from iris.ui.workspaces.ide_companion_page import IdeCompanionPage, IdeUnifiedShell
from iris.ui.workspaces.iris_ide_window import IrisIdeWindow


def _assert_no_orb_above_in_unified_source() -> None:
    from iris.ui.window import main_window as mw

    for name in (
        "_apply_iris_ide_unified_layout",
        "_activate_iris_ide_companion_tile",
        "_embed_viz_in_companion_slot",
    ):
        src = inspect.getsource(getattr(mw.MainWindow, name))
        assert "set_orb_above_ui(True)" not in src, name
    embed = inspect.getsource(mw.MainWindow._embed_viz_in_companion_slot)
    assert "embed_orb" in embed
    assert "set_layout_orb_mode(True)" in embed
    assert "release_orb_layer" in embed
    act = inspect.getsource(mw.MainWindow._activate_iris_ide_companion_tile)
    assert "set_embedded(True" in act
    assert "_sync_docked_iris_ide_geometry" in act
    assert "Qt.WindowType.Widget" not in inspect.getsource(
        __import__("iris.ui.workspaces.iris_ide_window", fromlist=["IrisIdeWindow"]).IrisIdeWindow.set_embedded
    )
    sync = inspect.getsource(mw.MainWindow._sync_docked_iris_ide_geometry)
    assert "iris_left" in sync or "iris.mapToGlobal" in sync
    assert "_normalize_assistant_sizes" in inspect.getsource(mw.MainWindow)
    assert "_home_assistant_sizes" in inspect.getsource(mw.MainWindow._apply_iris_ide_hero_layout)


def _assert_layout_orb_a_structure(app: QApplication) -> None:
    """Visualizer가 orb_spacer 자식이고 cyberspace orb_layer가 비어 있음."""
    root = CyberspaceBackground()
    root.resize(1000, 600)
    root.show()

    viz = Visualizer()
    ui = QWidget()
    ui.setObjectName("UiOverlay")
    root.set_orb_layer(viz)
    root.set_ui_overlay(ui)
    app.processEvents()

    shell = IdeUnifiedShell(ui)
    companion = IdeCompanionPage()
    ide = IrisIdeWindow()
    ide.set_embedded(True, host=shell)
    shell.setGeometry(0, 40, 1000, 560)
    shell.show()

    spacer = QWidget()
    spacer.setMinimumHeight(260)
    spacer.setMaximumHeight(260)
    live = QWidget()
    live.setMinimumHeight(80)
    live.setMaximumHeight(80)
    chat = QWidget()
    companion.mount(
        orb_spacer=spacer,
        live_activity=live,
        chat=chat,
        orb_height=260,
        activity_height=80,
    )
    shell.mount(None, companion, total_w=1000)
    app.processEvents()

    # 세로 드래그 스플리터 없음 — 고정 슬롯 + stretch
    assert not hasattr(companion, "_v_split")
    assert live.parent() is companion
    assert chat.parent() is companion
    assert shell._split.handleWidth() == 0

    # A: release + embed into spacer
    root.set_orb_above_ui(False)
    root.release_orb_layer()
    companion.embed_orb(viz, spacer)
    viz.set_layout_orb_mode(True)
    viz.set_companion_orb_placement(True)
    app.processEvents()

    assert root._orb_layer is None
    assert viz.parent() is spacer, viz.parent()
    assert companion.embedded_orb() is viz
    assert viz.is_layout_orb_mode()
    # 슬롯 중심 (창 중앙 아님)
    viz.resize(200, 260)
    app.processEvents()
    cx, cy = viz._window_content_center_local()
    assert abs(cx - 100) < 5, (cx, cy)
    assert 0 < cy < 260, (cx, cy)

    # IDE host opaque, iris transparent
    assert shell.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert shell.iris_host().testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    # restore path
    companion.release_embedded_orb()
    viz.set_layout_orb_mode(False)
    root.set_orb_layer(viz)
    app.processEvents()
    assert viz.parent() is root
    assert not viz.is_layout_orb_mode()

    root.close()
    app.processEvents()


def _assert_companion_grips() -> None:
    host = QMainWindow()
    host.resize(800, 600)
    shell = FramelessShell(host)
    content = QWidget()
    shell.set_center_widget(content)
    host.setCentralWidget(shell)
    host.show()
    shell.set_companion_grip_mode(True)
    # TL L BL B hidden
    assert not shell._grips[0].isVisible()
    assert not shell._grips[3].isVisible()
    assert not shell._grips[5].isVisible()
    assert not shell._grips[6].isVisible()
    assert shell._grips[4].isVisible()  # right
    shell.set_companion_grip_mode(False)
    assert shell._grips[6].isVisible()
    host.close()


def main() -> int:
    from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)
    iris = QMainWindow()
    iris.setWindowTitle("Iris Light")
    iris.resize(900, 700)
    iris.show()
    ide = IrisIdeWindow()
    ide.show()
    app.processEvents()

    area = work_area_for(iris)
    tiles = compute_tile_rects(area, ide_ratio=0.8)
    assert tiles_are_flush(tiles.ide, tiles.iris)
    assert tiles.ide.width() + tiles.iris.width() == area.width()

    ok, err = tile_iris_ide_and_iris(ide, iris, ide_ratio=0.8)
    assert ok, err
    app.processEvents()

    ide_geo = read_qt_window_rect(ide) or ide.geometry()
    iris_geo = read_qt_window_rect(iris) or iris.geometry()
    total = area.width()
    expected_ide = int(total * 0.8)
    assert ide_geo.width() == expected_ide, (ide_geo.width(), expected_ide)
    assert iris_geo.width() == total - expected_ide, (iris_geo.width(), total - expected_ide)
    assert tiles_are_flush(ide_geo, iris_geo), (ide_geo, iris_geo)
    assert not tiles_have_overlap(ide_geo, iris_geo), (ide_geo, iris_geo)
    assert ide_geo.width() + iris_geo.width() == total

    shell = IdeUnifiedShell()
    companion = IdeCompanionPage()
    ide2 = IrisIdeWindow()
    # HWND 도킹 — Qt 레이아웃에 IDE를 넣지 않음
    shell.resize(1000, 600)
    shell.show()
    shell.mount(None, companion, total_w=1000)
    app.processEvents()
    sizes = shell._split.sizes()
    assert sizes[0] == 800 and sizes[1] == 200, sizes
    ide2.set_embedded(True, host=shell)
    assert ide2.is_embedded()
    assert ide2.isWindow()
    assert bool(ide2.windowFlags() & Qt.WindowType.Window)
    assert hasattr(ide2, "focus_theia_view")
    assert hasattr(shell, "set_ide_insets")
    ide2.set_embedded(False)

    _assert_no_orb_above_in_unified_source()
    _assert_layout_orb_a_structure(app)
    _assert_companion_grips()

    # 히어로 geometry는 overlay 전체
    from iris.ui.window import main_window as mw

    sync_src = inspect.getsource(mw.MainWindow._sync_ide_hero_geometry)
    assert "overlay.rect()" in sync_src
    assert "body.mapTo" not in sync_src

    assert companion.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert shell.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    iris.close()
    app.processEvents()
    print("iris_ide_companion_tile check ok", tiles.ide, tiles.iris, "unified", sizes, "A-layout-orb")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
