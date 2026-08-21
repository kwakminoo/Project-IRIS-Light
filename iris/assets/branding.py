"""앱 아이콘·표시 이름 — 창/작업표시줄용."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QFontDatabase, QIcon

APP_DISPLAY_NAME = "IRIS"
# Windows 작업표시줄 그룹핑 — python.exe와 분리
APP_USER_MODEL_ID = "kwakminoo.IRIS.Light"
_ASSETS = Path(__file__).resolve().parent
_FONT_DIR = _ASSETS / "fonts"
_BUNDLED_FONT_FILES = ("Pretendard-Regular.otf", "Pretendard-Bold.otf")

# PC마다 시스템 폰트 설치 여부가 달라 UI가 다르게 보이는 문제를 막기 위해
# 폰트를 앱에 번들 — 등록 성공 시 이 family명이 항상 쓰인다.
BUNDLED_FONT_FAMILY = "Pretendard"


def load_bundled_fonts() -> str:
    """QApplication 생성 후, 위젯 생성 전에 호출. 등록된 family명을 반환.

    등록 실패(파일 손상 등) 시 시스템 폰트로 폴백하도록 기존 폴백 체인 이름을 반환.
    """
    ok = False
    for name in _BUNDLED_FONT_FILES:
        path = _FONT_DIR / name
        if not path.is_file():
            continue
        if QFontDatabase.addApplicationFont(str(path)) != -1:
            ok = True
    return BUNDLED_FONT_FAMILY if ok else "Segoe UI"


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
