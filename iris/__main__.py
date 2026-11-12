"""python -m iris 진입점 — UI 셸."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication


def _boot_trace(msg: str) -> None:
    """pid/ppid breadcrumb for dual-GUI hunts (pythonw has no console)."""
    try:
        path = Path.home() / ".iris-light" / "logs" / "boot_trace.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"pid={os.getpid()} ppid={os.getppid()} {msg}\n")
    except Exception:
        pass


def _maybe_elevate_on_startup() -> bool:
    """관리자 재실행이 필요하면 UAC 후 True(현재 프로세스 종료).

    - 제한 없음 권한
    - 실행 프로토콜(첫 설치·Core 미완료) — winget/Hermes 등이 관리자에서만 정상
    elevate 는 singleton 보다 먼저: 부모가 mutex 를 쥔 채 자식만 죽이면 GUI 가 0이 된다.
    성공 시 부모는 반드시 exit — Local\\ mutex 는 integrity 가 다르면 자식을 막지 못한다.
    """
    if sys.platform != "win32":
        return False
    try:
        from iris.learning.elevation import (
            is_elevated,
            needs_admin_for_setup,
            relaunch_as_admin,
        )

        if is_elevated():
            return False
        # Spawned by relaunch_as_admin — never ShellExecute again from this process.
        if os.environ.get("IRIS_ELEVATED_CHILD", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }:
            return False
        from iris.storage.database import Database
        from iris.storage.learning_prefs import load_learning_preferences

        prefs = load_learning_preferences(Database())
        if prefs.permission_level == "unrestricted" or needs_admin_for_setup():
            return bool(relaunch_as_admin())
    except Exception:
        return False
    return False


def _setup_file_logging() -> None:
    """iris.* 로그를 ~/.iris-light/logs/iris.log 에 남긴다.

    설정이 없으면 log.info 는 어디에도 안 남고 warning 도 숨긴 콘솔로만 가서,
    핀 감시처럼 백그라운드에서 도는 기능이 왜 멈췄는지 알 길이 없었다."""
    import logging
    from logging.handlers import RotatingFileHandler

    try:
        log_dir = Path.home() / ".iris-light" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_dir / "iris.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
    except Exception:
        return
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%m-%d %H:%M:%S")
    )
    logger = logging.getLogger("iris")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)


def main() -> None:
    # Qt aborts on an unhandled Python slot exception. Persist the traceback
    # even under pythonw, whose stderr is normally None.
    def report_exception(exc_type, value, tb):
        from IRIS_launcher import _log_path

        try:
            with _log_path().open("a", encoding="utf-8") as log:
                traceback.print_exception(exc_type, value, tb, file=log)
        finally:
            sys.__excepthook__(exc_type, value, tb)
            app = QApplication.instance()
            if app is not None:
                app.exit(1)

    sys.excepthook = report_exception
    _boot_trace("main enter")

    # pythonw 부모 + 콘솔 자식 = Cascadia/터미널 깜빡임. 무거운 import 전에 막는다.
    try:
        from iris.system.win_subprocess import (
            install_no_console_subprocess_patch,
            suppress_platform_ver_console,
        )

        suppress_platform_ver_console()
        install_no_console_subprocess_patch()
    except Exception:
        pass

    # Elevate before singleton: parent must not hold the GUI mutex across UAC relaunch.
    if _maybe_elevate_on_startup():
        _boot_trace("elevate relaunch; parent exit")
        sys.exit(0)

    _setup_file_logging()

    try:
        from iris.system.gui_singleton import acquire_gui_singleton

        ok_single, single_msg = acquire_gui_singleton()
        _boot_trace(f"singleton ok={ok_single}")
        if not ok_single:
            try:
                import ctypes

                ctypes.windll.user32.MessageBoxW(0, single_msg, "IRIS", 0x40)
            except Exception:
                print(single_msg, file=sys.stderr)
            sys.exit(0)
    except ImportError:
        _boot_trace("singleton ImportError")
    except Exception:
        import logging

        logging.getLogger("iris").exception("gui singleton acquire failed")
        _boot_trace("singleton exception exit")
        sys.exit(1)

    _boot_trace("gui continue")

    try:
        from iris.learning.elevation import hide_console_window

        hide_console_window()
    except Exception:
        pass

    if sys.platform == "win32":
        from iris.assets.windows_taskbar import ensure_windows_taskbar_branding

        ensure_windows_taskbar_branding()

    from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

    ensure_qt_webengine_ready()

    from iris.assets.branding import APP_DISPLAY_NAME, load_app_icon
    from iris.ui.window.main_window import MainWindow

    app = QApplication(sys.argv)
    # ponytail: 설정/위저드 등 top-level 다이얼로그만 닫혀도 프로세스 종료 금지 —
    # 종료는 MainWindow.closeEvent accept 뒤 QApplication.quit()만.
    app.setQuitOnLastWindowClosed(False)
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
