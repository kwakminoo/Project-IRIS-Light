"""IDE hero overlay + welcome + intro self-check."""

from __future__ import annotations

import inspect
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from iris.ui.ide.iris_ide_hero_overlay import IrisIdeHeroOverlay
from iris.ui.ide.iris_ide_welcome_layer import IrisIdeWelcomeLayer
from iris.ui.shared.theme_tokens import TOKENS
from iris.ui.sidebar.workspace_action_panel import WorkspaceActionPanel
from iris.ui.widgets.particle_visualizer import ParticleVisualizer
from iris.ui.widgets.visualizer import Visualizer
from iris.ui.window.startup_intro import StartupIntroAnimator
from iris.ui.workspaces.ide_companion_page import IdeUnifiedShell
from iris.ui.workspaces.iris_ide_window import IrisIdeWindow

def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    hero = IrisIdeHeroOverlay()
    assert hero._title.text() == "IRIS IDE"
    assert hero.btn_open is not None

    layer = IrisIdeWelcomeLayer()
    assert layer._title.text() == "IRIS IDE"

    orb = ParticleVisualizer()
    orb.set_hero_mode(True)
    assert orb._hero_mode is True

    viz = Visualizer()
    viz.set_hero_orb_placement(True)
    assert viz._center_y_ratio > 0.36

    intro = StartupIntroAnimator()
    assert hasattr(intro, "start_panels_reveal")
    assert hasattr(intro, "start_exit_to_void")
    assert hasattr(intro, "start_hero_reveal")
    assert hasattr(intro, "start_hero_conceal")
    assert hasattr(intro, "start_enter_from_void")
    assert hasattr(intro, "restore_proxies")

    hits: list[str] = []
    panel = WorkspaceActionPanel()
    panel.set_default_callback(lambda: hits.append("default"))
    panel.add_icon_action(
        action_id="ide",
        icon_kind="ide",
        tooltip="IDE",
        callback=lambda: hits.append("ide"),
        reclick_returns=False,
    )
    panel.set_action_active("ide", True)
    panel._invoke_icon_action("ide", lambda: hits.append("ide"))
    assert hits == ["ide"], hits

    shell = IdeUnifiedShell()
    shell.resize(1000, 600)
    shell.show()
    app.processEvents()
    shell.apply_ratio(1000)
    app.processEvents()
    sizes = shell._split.sizes()
    assert sum(sizes) == 1000, sizes
    assert sizes[0] == 800, sizes
    assert sizes[1] == 200, sizes
    # IDE host insets — left/bottom grips must not cover Theia chrome
    assert shell._ide_lay.contentsMargins().left() >= 8
    assert shell._ide_lay.contentsMargins().bottom() >= 8
    # 우측 Companion — 셸/아이리스 호스트 투명 (구체·사이버 배경 비침)
    assert shell.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert shell.iris_host().testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert TOKENS.void_black in shell.ide_host().styleSheet()

    # Create folder: no QInputDialog name prompt
    import inspect

    from iris.ui.ide import iris_ide_hero_overlay as hero_mod
    from iris.ui.ide import iris_ide_welcome_layer as welcome_mod

    assert "QInputDialog" not in inspect.getsource(hero_mod.IrisIdeHeroOverlay._pick_create)
    assert "QInputDialog" not in inspect.getsource(welcome_mod.IrisIdeWelcomeLayer._pick_create_folder)
    assert "next_iris_project_dir" in inspect.getsource(hero_mod.IrisIdeHeroOverlay._pick_create)

    # Companion orb X follows anchor, not window center
    from PyQt6.QtWidgets import QWidget
    from iris.ui.workspaces.ide_companion_page import IdeCompanionPage
    from iris.ui.window.cyberspace_background import CyberspaceBackground

    host = QWidget()
    host.resize(1000, 600)
    host.show()
    companion = IdeCompanionPage(host)
    companion.setGeometry(800, 0, 200, 600)
    companion.show()
    spacer = QWidget(companion)
    spacer.setGeometry(0, 0, 200, 260)
    spacer.show()
    viz = Visualizer(host)
    viz.setGeometry(0, 0, 1000, 600)
    viz.show()
    viz.set_orb_anchor(spacer)
    viz.set_companion_orb_placement(True)
    app.processEvents()
    cx, cy = viz._window_content_center_local()
    assert cx > 700, (cx, cy)  # right 20% column, not window center 500
    assert abs(cx - 900) < 80, (cx, cy)

    # cyberspace: companion A — layout orb in spacer (not full-window overlay)
    bg = CyberspaceBackground()
    bg.resize(1000, 600)
    bg.show()
    viz2 = Visualizer()
    overlay = QWidget()
    overlay.setObjectName("UiOverlay")
    bg.set_orb_layer(viz2)
    bg.set_ui_overlay(overlay)
    spacer2 = QWidget(overlay)
    spacer2.setGeometry(800, 0, 200, 260)
    spacer2.show()
    bg.release_orb_layer()
    lay = __import__("PyQt6.QtWidgets", fromlist=["QVBoxLayout"]).QVBoxLayout(spacer2)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(viz2)
    viz2.set_layout_orb_mode(True)
    viz2.set_companion_orb_placement(True)
    app.processEvents()
    assert bg._orb_layer is None
    assert viz2.parent() is spacer2
    assert viz2.is_layout_orb_mode()
    cx2, _ = viz2._window_content_center_local()
    assert abs(cx2 - viz2.width() * 0.5) < 5, cx2

    # layout_orb + anchor None 동기화 — 구체 중심이 슬롯 안에 유지
    viz2.set_orb_anchor(None)
    viz2.request_sync_orb_anchor("test")
    app.processEvents()
    assert viz2._last_center is not None
    assert 0 < viz2._last_center[0] < viz2.width()
    assert 0 < viz2._last_center[1] < viz2.height()

    # Transparent companion page (cyberspace shows through)
    assert companion.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    # HWND dock: set_embedded keeps Window, never Qt.Widget embed
    from PyQt6.QtWidgets import QWidget as _QW

    ide = IrisIdeWindow()
    host = _QW()
    ide.set_embedded(True, host=host)
    assert ide.isWindow()
    assert "Qt.WindowType.Widget" not in inspect.getsource(IrisIdeWindow.set_embedded)
    ide.set_embedded(False)

    print("ide_hero ok")
    app.quit()


if __name__ == "__main__":
    main()
