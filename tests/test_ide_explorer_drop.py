"""IDE native file drops survive repeated WebEngine target refreshes."""
import sys
import unittest
from unittest.mock import patch


@unittest.skipUnless(sys.platform == "win32", "Windows OLE targets")
class IdeExplorerDropTests(unittest.TestCase):
    def test_real_native_child_registration_survives_refresh(self):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication, QWidget
        from iris.ui.window import win_ole_drop as dnd

        app = QApplication.instance() or QApplication([])
        host = QWidget()
        child = QWidget(host)
        child.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        child.setAcceptDrops(True)
        host.show()
        app.processEvents()
        try:
            root_hwnd, child_hwnd = int(host.winId()), int(child.winId())
            # Simulate a child surface registering its own OLE target, as
            # Chromium can do when it creates a native drop surface.
            foreign = dnd._ExplorerDropTarget(host, target_name="webengine")
            self.assertTrue(dnd._register_hwnd(child_hwnd, foreign, label="webengine"))
            self.assertTrue(dnd._ole_prop(child_hwnd))
            for _ in range(3):
                self.assertTrue(dnd.ensure_explorer_drop_targets(root_hwnd, host, target="ide"))
                self.assertIn(child_hwnd, host._explorer_ole_hwnds)
                self.assertEqual(dnd._ole_prop(child_hwnd), host._explorer_ole_target.addr)
        finally:
            dnd._revoke_hwnds(getattr(host, "_explorer_ole_hwnds", ()))
            host.close()
            host.deleteLater()
            app.processEvents()

    def test_refresh_keeps_owned_children_and_removes_detached_children(self):
        from iris.ui.window import win_ole_drop as dnd

        class Host:
            pass

        host = Host()
        props = {10: 0, 11: 42, 12: 42}
        drop = type("Target", (), {"addr": 42})()

        def register(hwnd, target, **kwargs):
            props[hwnd] = target.addr
            return True

        def revoke(hwnds):
            for hwnd in hwnds:
                props[hwnd] = 0

        with patch.object(dnd, "_owned_target", return_value=drop), \
             patch.object(dnd, "_ole_prop", side_effect=lambda hwnd: props[hwnd]), \
             patch.object(dnd, "_register_hwnd", side_effect=register), \
             patch.object(dnd, "_revoke_hwnds", side_effect=revoke), \
             patch.object(dnd, "_child_hwnds_with_drop", return_value=[11, 12]):
            for _ in range(3):
                self.assertTrue(dnd.ensure_explorer_drop_targets(10, host, target="ide"))
                self.assertEqual(host._explorer_ole_hwnds, {10, 11, 12})
                self.assertEqual(props, {10: 42, 11: 42, 12: 42})
            with patch.object(dnd, "_child_hwnds_with_drop", return_value=[11]):
                self.assertTrue(dnd.ensure_explorer_drop_targets(10, host, target="ide"))
                self.assertEqual(props[11], 42)
                self.assertEqual(props[12], 0)

    def test_enumeration_includes_our_targets_but_not_unregistered_children(self):
        import ctypes
        from iris.ui.window import win_ole_drop as dnd

        def enumerate_children(root, callback, data):
            for hwnd in (11, 12, 13):
                callback(hwnd, data)
            return 1

        with patch.object(ctypes.windll.user32, "EnumChildWindows", side_effect=enumerate_children), \
             patch.object(dnd, "_ole_prop", side_effect=lambda hwnd: {11: 42, 12: 99, 13: 0}[hwnd]):
            self.assertEqual(dnd._child_hwnds_with_drop(10), [11, 12])


if __name__ == "__main__":
    unittest.main()
