"""Windows IDE hooks must import and preserve pointer-sized API values."""
import ctypes
import sys
import unittest
from unittest.mock import patch


@unittest.skipUnless(sys.platform == "win32", "Windows hooks")
class Win32IdeHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication

        # Keep Qt alive across tests: app-owned shared managers must not outlive
        # an application recreated by the next test.
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_pointer_sized_callback_and_handle(self):
        from iris.learning.win32_hooks import LRESULT, LowLevelProc

        self.assertEqual(ctypes.sizeof(LRESULT), ctypes.sizeof(ctypes.c_void_p))
        result = (1 << 40) + 123 if ctypes.sizeof(LRESULT) == 8 else 123
        callback = LowLevelProc(lambda code, wp, lp: result)
        self.assertEqual(callback(0, 0, 0), result)
        api = ctypes.windll.user32
        self.assertEqual(ctypes.sizeof(api.SetWindowsHookExW.restype), ctypes.sizeof(ctypes.c_void_p))
        self.assertIs(api.CallNextHookEx.restype, LRESULT)

    def test_real_install_uninstall_and_reinstall(self):
        from PyQt6.QtWidgets import QApplication, QWidget
        from iris.ui.window.ide_snap_redirect import IdeSnapRedirect

        app = QApplication.instance() or QApplication([])
        owner = QWidget()
        redirect = IdeSnapRedirect(owner, ide_hwnd=lambda: 0)
        try:
            for _ in range(2):
                self.assertTrue(redirect.install())
                self.assertTrue(redirect._hook)
                app.processEvents()
                redirect.uninstall()
                self.assertIsNone(redirect._hook)
        finally:
            redirect.uninstall()
            owner.close()

    def test_missing_optional_hook_does_not_raise(self):
        from PyQt6.QtWidgets import QApplication, QWidget
        from iris.ui.window.ide_snap_redirect import IdeSnapRedirect

        app = QApplication.instance() or QApplication([])
        owner = QWidget()
        redirect = IdeSnapRedirect(owner, ide_hwnd=lambda: 0)
        with patch.dict(sys.modules, {"iris.learning.win32_hooks": None}):
            with self.assertLogs("iris.ui.ide_snap_redirect", level="ERROR"):
                self.assertFalse(redirect.install())
        owner.close()
