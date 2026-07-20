"""HUD 퀵런치 아이콘 — QPainter로 브랜드 실루엣 렌더."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap

from iris.ui.theme_tokens import TOKENS

HUD_ICON_PX = 22
HUD_ICON_BTN_PX = 40


def _stroke(active: bool) -> QPen:
    color = QColor(TOKENS.neon_cyan if active else TOKENS.text_accent)
    pen = QPen(color)
    pen.setWidthF(1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _fill(active: bool) -> QBrush:
    return QBrush(QColor(TOKENS.neon_cyan if active else TOKENS.text_accent))


def _paint_ide(p: QPainter, active: bool) -> None:
    pen = _stroke(active)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(7, 8, 4, 11)
    p.drawLine(4, 11, 7, 14)
    p.drawLine(15, 8, 18, 11)
    p.drawLine(18, 11, 15, 14)
    p.setFont(QFont(TOKENS.font_mono.split(",")[0].strip('"'), 9, QFont.Weight.Bold))
    p.drawText(6, 17, ";")


def _paint_email(p: QPainter, active: bool) -> None:
    pen = _stroke(active)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(4, 7, 14, 10, 2, 2)
    path = QPainterPath()
    path.moveTo(4, 8)
    path.lineTo(11, 13)
    path.lineTo(18, 8)
    p.drawPath(path)


def _paint_instagram(p: QPainter, active: bool) -> None:
    pen = _stroke(active)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(4, 4, 14, 14, 4, 4)
    p.drawEllipse(8, 8, 6, 6)
    p.drawPoint(15, 7)


def _paint_discord(p: QPainter, active: bool) -> None:
    pen = _stroke(active)
    p.setPen(pen)
    p.setBrush(_fill(active))
    path = QPainterPath()
    path.moveTo(5, 9)
    path.cubicTo(5, 6, 8, 5, 11, 5)
    path.cubicTo(14, 5, 17, 6, 17, 9)
    path.cubicTo(17, 12, 15, 15, 11, 16)
    path.cubicTo(7, 15, 5, 12, 5, 9)
    p.drawPath(path)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(8, 10, 2, 2)
    p.drawEllipse(12, 10, 2, 2)


def _paint_kakao(p: QPainter, active: bool) -> None:
    pen = _stroke(active)
    p.setPen(pen)
    p.setBrush(_fill(active))
    p.drawRoundedRect(4, 5, 14, 11, 5, 5)
    tail = QPainterPath()
    tail.moveTo(8, 16)
    tail.lineTo(6, 19)
    tail.lineTo(11, 16)
    p.drawPath(tail)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(TOKENS.void_black))
    p.drawEllipse(8, 9, 2, 2)
    p.drawEllipse(12, 9, 2, 2)


def _paint_telegram(p: QPainter, active: bool) -> None:
    pen = _stroke(active)
    p.setPen(pen)
    p.setBrush(_fill(active))
    path = QPainterPath()
    path.moveTo(5, 11)
    path.lineTo(17, 6)
    path.lineTo(13, 17)
    path.lineTo(10, 13)
    path.lineTo(6, 14)
    path.closeSubpath()
    p.drawPath(path)


def _paint_mobile(p: QPainter, active: bool) -> None:
    pen = _stroke(active)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(7, 3, 8, 16, 2, 2)
    p.drawLine(9, 6, 13, 6)
    p.drawPoint(11, 17)


def _paint_obsidian(p: QPainter, active: bool) -> None:
    """Obsidian 보석 실루엣."""
    pen = _stroke(active)
    p.setPen(pen)
    p.setBrush(_fill(active))
    gem = QPainterPath()
    gem.moveTo(11, 4)
    gem.lineTo(16, 9)
    gem.lineTo(13, 18)
    gem.lineTo(6, 18)
    gem.lineTo(3, 9)
    gem.closeSubpath()
    p.drawPath(gem)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(11, 4, 11, 18)
    p.drawLine(3, 9, 16, 9)


_PAINTERS = {
    "ide": _paint_ide,
    "email": _paint_email,
    "instagram": _paint_instagram,
    "discord": _paint_discord,
    "kakao": _paint_kakao,
    "telegram": _paint_telegram,
    "mobile": _paint_mobile,
    "obsidian": _paint_obsidian,
}


def render_hud_icon_pixmap(kind: str, *, active: bool = False, size: int = HUD_ICON_PX) -> QPixmap:
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    scale = size / HUD_ICON_PX
    if scale != 1.0:
        painter.scale(scale, scale)
    painter_fn = _PAINTERS.get(kind)
    if painter_fn is not None:
        painter_fn(painter, active)
    painter.end()
    return px


def hud_quick_launch_icon(kind: str, *, active: bool = False) -> QIcon:
    return QIcon(render_hud_icon_pixmap(kind, active=active))


def hud_icon_size() -> QSize:
    return QSize(HUD_ICON_PX, HUD_ICON_PX)


if __name__ == "__main__":
    for kind in _PAINTERS:
        assert not render_hud_icon_pixmap(kind).isNull(), kind
    print("hud_quick_launch_icons ok")
