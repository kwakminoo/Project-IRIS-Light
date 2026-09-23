"""설치 프로토콜 단계별 브랜드 로고 (Ollama / Hermes / IRIS)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPixmap

_ASSETS = Path(__file__).resolve().parent
_IRIS_PNG = _ASSETS / "iris_icon.png"

# step_id → brand key
STEP_BRAND: dict[str, str] = {
    "mcp_venv": "iris",
    "ollama_install": "ollama",
    "ollama_model": "ollama",
    "ollama_cloud": "ollama",
    "hermes_install": "hermes",
    "hermes_env": "hermes",
    "hermes_provider": "hermes",
    "iris_control_sync": "hermes",
    "hermes_gateway": "hermes",
    "core_smoke": "iris",
    "emulator": "iris",
    "voice": "iris",
    "voice_full": "iris",
    "learning": "iris",
    "mobile_mcp": "iris",
    "iris_ide": "iris",
}

_BRAND_LABEL = {
    "ollama": "Ollama",
    "hermes": "Hermes",
    "iris": "IRIS",
}

_BRAND_COLOR = {
    "ollama": "#1a1a1a",
    "hermes": "#5b4dff",
    "iris": "#00e5ff",
}


def brand_for_step(step_id: str) -> str:
    return STEP_BRAND.get((step_id or "").strip(), "iris")


def brand_label(brand: str) -> str:
    return _BRAND_LABEL.get(brand, "IRIS")


def setup_brand_pixmap(brand: str, *, size: int = 36) -> QPixmap:
    """단계 카드용 로고. IRIS는 앱 아이콘, 나머지는 모노그램 배지."""
    key = (brand or "iris").strip().lower() or "iris"
    if key == "iris" and _IRIS_PNG.is_file():
        src = QPixmap(str(_IRIS_PNG))
        if not src.isNull():
            return src.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
    return _monogram_pixmap(key, size)


def _monogram_pixmap(brand: str, size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    fill = QColor(_BRAND_COLOR.get(brand, "#00e5ff"))
    if brand == "ollama":
        # Ollama 느낌의 밝은 원 + 검정 O
        p.setBrush(QColor("#ffffff"))
        p.setPen(QPen(QColor("#222222"), max(1.0, size * 0.06)))
        m = max(1, size // 12)
        p.drawEllipse(m, m, size - 2 * m, size - 2 * m)
        p.setPen(QColor("#111111"))
    else:
        p.setBrush(fill)
        p.setPen(Qt.PenStyle.NoPen)
        rad = max(4, size // 5)
        p.drawRoundedRect(0, 0, size, size, rad, rad)
        p.setPen(QColor("#ffffff"))
    letter = {"ollama": "O", "hermes": "H", "iris": "I"}.get(brand, "?")
    font = QFont("Segoe UI", max(8, int(size * 0.42)))
    font.setBold(True)
    p.setFont(font)
    p.drawText(pm.rect(), int(Qt.AlignmentFlag.AlignCenter), letter)
    p.end()
    return pm


if __name__ == "__main__":
    assert brand_for_step("hermes_gateway") == "hermes"
    assert brand_for_step("core_smoke") == "iris"
    assert brand_for_step("ollama_install") == "ollama"
    pm = setup_brand_pixmap("hermes", size=32)
    assert not pm.isNull() and pm.width() == 32
    print("setup_logos ok", brand_label("hermes"), pm.width())
