"""IDE 공식 로고 아이콘 — 설치 여부와 무관하게 assets/ide_logos 사용."""

from __future__ import annotations

import webbrowser
from pathlib import Path

from PyQt6.QtCore import QByteArray, Qt, QRectF, QSize
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QMessageBox, QWidget

from iris.system.ide_launcher import get_ide_spec

_IRIS_ICON_DIR = Path(__file__).resolve().parents[2] / "assets"
_LOGO_DIR = _IRIS_ICON_DIR / "ide_logos"

# 다크 UI용 — 검정 실루엣 / fill 없는 SVG에 브랜드 색 주입
_BRAND_FILL: dict[str, str] = {
    "cursor": "#E8ECFF",
    "vscode": "#007ACC",
    "vs": "#5C2D91",
    "pycharm": "#21D789",
    "intellij": "#FE315D",
    "webstorm": "#00CDD7",
    "android_studio": "#3DDC84",
    "sublime": "#FF9800",
    "notepadpp": "#90E59A",
    "windsurf": "#00A67E",
    "trae": "#6C8CFF",
    "zed": "#0847F7",
    "rider": "#DD3A9B",
    "neovim": "#57A143",
}


def _logo_path(ide_id: str) -> Path | None:
    for ext in (".svg", ".png", ".jpg", ".jpeg", ".ico", ".webp"):
        p = _LOGO_DIR / f"{ide_id}{ext}"
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def _fallback_ide_icon(name: str, size: int = 40) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(QColor("#1a1c24"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#2a2d3a"))
    p.setPen(QColor("#5a8fff"))
    p.drawRoundedRect(1, 1, size - 2, size - 2, 6, 6)
    letter = (name.strip()[:1] or "?").upper()
    p.setPen(QColor("#e8ecff"))
    p.setFont(QFont("Segoe UI", max(10, size // 3), QFont.Weight.Bold))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, letter)
    p.end()
    return QIcon(pm)


def _prepare_svg(raw: str, ide_id: str) -> str:
    fill = _BRAND_FILL.get(ide_id, "#E8ECFF")
    text = raw
    for old in ('fill="#000000"', 'fill="#000"', 'fill="black"', "fill='#000000'", "fill='black'"):
        text = text.replace(old, f'fill="{fill}"')
    # fill 없는 SVG(루트)면 브랜드 색 주입
    if 'fill="' not in text[:160] and "fill='" not in text[:160]:
        text = text.replace("<svg ", f'<svg fill="{fill}" ', 1)
    return text


def _render_logo(path: Path, ide_id: str, size: int) -> QPixmap | None:
    try:
        if path.suffix.lower() == ".svg":
            raw = path.read_text(encoding="utf-8")
            prepared = _prepare_svg(raw, ide_id)
            renderer = QSvgRenderer(QByteArray(prepared.encode("utf-8")))
            if not renderer.isValid():
                return None
            pm = QPixmap(size, size)
            pm.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pm)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pad = max(2, size // 10)
            renderer.render(painter, QRectF(pad, pad, size - 2 * pad, size - 2 * pad))
            painter.end()
            return pm
        src = QPixmap(str(path))
        if src.isNull():
            return None
        return src.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    except OSError:
        return None


def _iris_official_icon(size: int = 40) -> QIcon | None:
    for name in ("iris_icon.png", "iris_icon.ico"):
        p = _IRIS_ICON_DIR / name
        if p.is_file() and p.stat().st_size > 0:
            pm = _render_logo(p, "iris_ide", size)
            if pm is not None and not pm.isNull():
                return QIcon(pm)
    return None


def ide_icon_for(ide_id: str, exe_path: str = "", *, size: int = 40) -> QIcon:
    """공식 로고 우선. exe_path는 호환용으로 무시(설치 여부와 무관)."""
    _ = exe_path
    key = (ide_id or "").strip().lower()
    if key == "iris_ide":
        iris = _iris_official_icon(size=size)
        if iris is not None:
            return iris
    path = _logo_path(key)
    if path is not None:
        pm = _render_logo(path, key, size)
        if pm is not None and not pm.isNull():
            # PNG가 작을 수 있어 캔버스 중앙 배치
            if pm.width() != size or pm.height() != size:
                canvas = QPixmap(size, size)
                canvas.fill(Qt.GlobalColor.transparent)
                painter = QPainter(canvas)
                x = (size - pm.width()) // 2
                y = (size - pm.height()) // 2
                painter.drawPixmap(x, y, pm)
                painter.end()
                pm = canvas
            return QIcon(pm)
    spec = get_ide_spec(key)
    return _fallback_ide_icon(spec.name if spec else key or "?", size=size)


def show_ide_not_installed_dialog(parent: QWidget | None, ide_id: str) -> None:
    """미설치 IDE — 닫기 / 설치하기."""
    if (ide_id or "").strip().lower() == "iris_ide":
        from iris.ui.settings.iris_ide_settings import prompt_iris_ide_install

        prompt_iris_ide_install(parent)
        return
    spec = get_ide_spec(ide_id)
    name = spec.name if spec else ide_id
    url = (spec.install_url if spec else "") or ""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle("IDE 미설치")
    box.setText(f"{name}이(가) 이 PC에 설치되어 있지 않습니다.")
    box.setInformativeText("설치하기를 누르면 다운로드 페이지를 엽니다.")
    close_btn = box.addButton("닫기", QMessageBox.ButtonRole.RejectRole)
    install_btn = box.addButton("설치하기", QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(close_btn)
    box.exec()
    if box.clickedButton() is install_btn and url:
        webbrowser.open(url)


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    for ide in ("cursor", "vscode", "pycharm", "trae", "missing"):
        icon = ide_icon_for(ide, size=40)
        assert not icon.isNull(), ide
    print("ide_icons ok")
