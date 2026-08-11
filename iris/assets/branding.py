"""앱 아이콘·표시 이름 — 창/작업표시줄용."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtGui import QIcon

APP_DISPLAY_NAME = "IRIS"
_ASSETS = Path(__file__).resolve().parent


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
