"""앱 아이콘·표시 이름 — 창/작업표시줄용."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QIcon

APP_DISPLAY_NAME = "IRIS"
# Windows 작업표시줄 그룹핑 — python.exe와 분리
APP_USER_MODEL_ID = "kwakminoo.IRIS.Light"
_ASSETS = Path(__file__).resolve().parent


def apply_windows_app_id() -> None:
    """QApplication 생성 전에 호출 — 작업표시줄 아이콘/이름을 IRIS로."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def app_icon_path() -> Path:
    """우선 .ico, 없으면 png."""
    ico = _ASSETS / "iris_icon.ico"
    if ico.is_file():
        return ico
    return _ASSETS / "iris_icon.png"


def load_app_icon() -> QIcon:
    path = app_icon_path()
    if not path.is_file():
        return QIcon()
    return QIcon(str(path))


if __name__ == "__main__":
    p = app_icon_path()
    assert p.name.startswith("iris_icon"), p
    print("branding ok", p, "exists", p.is_file())
