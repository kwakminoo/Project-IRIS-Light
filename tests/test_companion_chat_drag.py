"""Continuous IDE chat expansion, stable orb and the main chat fade contract."""
import sys
import unittest

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.monitor.live_activity_panel import LiveActivityPanel
from iris.ui.widgets.visualizer import Visualizer
from iris.ui.workspaces.ide_companion_page import IdeCompanionPage

APP = QApplication.instance() or QApplication(sys.argv)


class CompanionChatDragTests(unittest.TestCase):
    def setUp(self):
        self.window = QWidget()
        self.window.resize(360, 820)
        self.page = IdeCompanionPage()
        QVBoxLayout(self.window).addWidget(self.page)
        self.orb = QWidget()
        self.live = LiveActivityPanel()
        self.chat = ChatPanel()
        self.viz = Visualizer()
        self.window._viz = self.viz
        self.page.mount(orb_spacer=self.orb, live_activity=self.live,
                        chat=self.chat, orb_height=260, activity_height=90)
        self.page.embed_orb(self.viz)
        self.viz.set_layout_orb_mode(True)
        self.viz.set_companion_orb_placement(True)
        self.window.show()
        APP.processEvents()
        self.top = self.chat.y()
        self.center = self.viz.particle_core().effective_center()
        self.chat._height_handle.drag_started.emit(700)

    def tearDown(self):
        self.chat.reset_height_expansion()
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()

    def drag(self, extra):
        self.chat._height_handle.dragged.emit(700 - extra)
        APP.processEvents()

    def test_every_pixel_moves_continuously_in_both_directions(self):
        for extra in [*range(351), *range(350, -1, -1)]:
            self.drag(extra)
            self.assertEqual(self.chat.y(), self.top - extra, extra)
            self.assertEqual(self.orb.height(), max(0, 260 - extra))
            self.assertEqual(self.live.height(), 90 - max(0, extra - 260))
            self.assertEqual(self.viz.particle_core().effective_center(), self.center)
            if extra:
                edge = self.viz.mapFromGlobal(self.chat.mapToGlobal(QPoint(0, 0))).y()
                self.assertEqual(self.viz.particle_core()._chat_fade_y, edge)
            else:
                self.assertIsNone(self.viz.particle_core()._chat_fade_y)

    def test_fade_uses_fixed_orb_coordinates_and_clears_on_restore(self):
        self.assertTrue(self.page._orb_host.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        image = QImage(20, 260, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor("white"))
        alpha = []
        for extra in (100, 180, 260, 340):
            self.drag(extra)
            faded = self.viz.particle_core()._fade_orb_image(image, 0)
            alpha.append(faded.pixelColor(10, 125).alpha())
        self.assertEqual(alpha, sorted(alpha, reverse=True))
        self.assertGreater(alpha[0], alpha[-1])
        self.assertEqual(alpha[-1], 0)
        self.chat.reset_height_expansion()
        APP.processEvents()
        self.assertEqual(self.chat.y(), self.top)
        self.assertEqual((self.orb.height(), self.live.height()), (260, 90))
        self.assertIsNone(self.viz.particle_core()._chat_fade_y)
        self.assertEqual(self.chat._above_snap, [])

    def test_mount_and_transfer_discard_previous_layout_snapshot(self):
        self.drag(180)
        target = QWidget()
        target.resize(360, 820)
        layout = QVBoxLayout(target)
        self.page.transfer_to(layout, (0, 0, 1))
        target.show()
        APP.processEvents()
        self.assertEqual(self.chat._extra_h, 0)
        self.assertEqual(self.chat._above_snap, [])
        self.page.mount(orb_spacer=self.orb, live_activity=self.live,
                        chat=self.chat, orb_height=260, activity_height=90)
        APP.processEvents()
        self.chat._height_handle.drag_started.emit(700)
        top = self.chat.y()
        self.drag(25)
        self.assertEqual(self.chat.y(), top - 25)
        target.close()
