"""python -m iris 진입점 — UI 셸."""

from __future__ import annotations

import sys

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication


def _maybe_elevate_for_unrestricted() -> bool:
    """제한 없음 저장 상태인데 비관리자면 UAC 재실행. True면 현재 프로세스 종료."""
    if sys.platform != "win32":
        return False
    try:
        from iris.learning.elevation import is_elevated, relaunch_as_admin
        from iris.storage.database import Database
        from iris.storage.learning_prefs import load_learning_preferences

        if is_elevated():
            return False
        prefs = load_learning_preferences(Database())
        if prefs.permission_level != "unrestricted":
            return False
        if relaunch_as_admin():
            return True
    except Exception:
        return False
    return False


def main() -> None:
    if _maybe_elevate_for_unrestricted():
        sys.exit(0)

    # GUI 전용 — 단독 콘솔이면 숨기고, 백그라운드 자식도 창 없이
    try:
        from iris.learning.elevation import hide_console_window

        hide_console_window()
    except Exception:
        pass

    # Windows 작업표시줄 아이콘 — Qt/QApplication import 전에 AppID 등록
    if sys.platform == "win32":
        from iris.assets.windows_taskbar import ensure_windows_taskbar_branding

        ensure_windows_taskbar_branding()

    from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

    ensure_qt_webengine_ready()

    from iris.assets.branding import APP_DISPLAY_NAME, load_app_icon
    from iris.ui.window.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setOrganizationName(APP_DISPLAY_NAME)
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    icon = load_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    app.setFont(QFont("Noto Sans KR", 10))
    win = MainWindow()
    win.show()
    for _ in range(3):
        app.processEvents()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
