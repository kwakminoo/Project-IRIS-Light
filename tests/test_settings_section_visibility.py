"""Settings sections must never be shown as temporary top-level windows."""

from unittest import TestCase

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QApplication, QGroupBox, QToolButton

from iris.ui.settings.hud_dialog import make_collapsible


class _ShowObserver(QObject):
    def __init__(self):
        super().__init__()
        self.top_level_shows = 0

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Show and watched.isWindow():
            self.top_level_shows += 1
        return False


class SettingsSectionVisibilityTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_sections_are_parented_before_becoming_visible(self):
        for expanded in (True, False):
            with self.subTest(expanded=expanded):
                box = QGroupBox("Settings section")
                observer = _ShowObserver()
                box.installEventFilter(observer)
                wrap = make_collapsible(box, expanded=expanded)
                try:
                    self.assertEqual(observer.top_level_shows, 0)
                    self.assertIs(box.parentWidget(), wrap)
                    self.assertFalse(box.isWindow())
                    self.assertFalse(wrap.isVisible())
                    wrap.show()
                    self.assertEqual(box.isVisible(), expanded)
                    toggle = wrap.findChild(QToolButton, "HudSectionToggle")
                    toggle.setChecked(not expanded)
                    self.assertEqual(box.isVisible(), not expanded)
                    self.assertEqual(observer.top_level_shows, 0)
                finally:
                    wrap.close()
                    wrap.deleteLater()
        self.app.processEvents()
