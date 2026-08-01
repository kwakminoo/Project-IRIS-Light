"""Cursor 스타일 Composer + 메뉴 — 첨부·Skill·MCP."""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QPoint, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def _hermes_root() -> Path:
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        p = Path(local) / "hermes"
        if p.is_dir():
            return p
    return Path.home() / ".hermes"


def list_hermes_skill_names(*, limit: int = 80) -> list[str]:
    root = _hermes_root() / "skills"
    if not root.is_dir():
        return []
    names: list[str] = []
    for path in sorted(root.rglob("SKILL.md")):
        name = path.parent.name.strip()
        if name and name not in names:
            names.append(name)
        if len(names) >= limit:
            break
    return names


def list_custom_skill_names(*, limit: int = 40) -> list[str]:
    """하위 호환 — custom 폴더만."""
    root = _hermes_root() / "skills" / "custom"
    if not root.is_dir():
        return []
    names: list[str] = []
    for path in sorted(root.rglob("SKILL.md")):
        name = path.parent.name.strip()
        if name and name not in names:
            names.append(name)
        if len(names) >= limit:
            break
    return names


def list_hermes_mcp_names(*, limit: int = 24) -> list[str]:
    """config.yaml 의 mcp_servers 키만 가볍게 파싱 (의존성 없이)."""
    cfg = _hermes_root() / "config.yaml"
    if not cfg.is_file():
        return []
    try:
        text = cfg.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    names: list[str] = []
    in_block = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if not in_block:
            if line.strip().startswith("mcp_servers:"):
                in_block = True
            continue
        if line and not line.startswith((" ", "\t")) and not line.strip().startswith("#"):
            break
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith(":") and not stripped.startswith("-"):
            key = stripped[:-1].strip().strip("\"'")
            if key and key not in names:
                names.append(key)
            if len(names) >= limit:
                break
    return names


class _MenuRow(QPushButton):
    def __init__(
        self,
        icon_text: str,
        title: str,
        subtitle: str = "",
        *,
        show_arrow: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ComposerPlusMenuRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(32 if subtitle else 28)
        self.setMaximumHeight(36 if subtitle else 30)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 3, 8, 3)
        lay.setSpacing(8)

        icon = QLabel(icon_text)
        icon.setObjectName("ComposerPlusMenuIcon")
        icon.setFixedWidth(28)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont("Segoe UI", 8)
        font.setWeight(QFont.Weight.DemiBold)
        icon.setFont(font)
        lay.addWidget(icon, 0)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("ComposerPlusMenuTitle")
        text_col.addWidget(title_lbl)
        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setObjectName("ComposerPlusMenuSub")
            text_col.addWidget(sub_lbl)
        lay.addLayout(text_col, 1)

        if show_arrow:
            arrow = QLabel("›")
            arrow.setObjectName("ComposerPlusMenuArrow")
            arrow.setFixedWidth(18)
            arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(arrow, 0)

        self.setStyleSheet(
            """
            QPushButton#ComposerPlusMenuRow {
                background: transparent;
                border: none;
                border-radius: 6px;
                text-align: left;
            }
            QPushButton#ComposerPlusMenuRow:hover {
                background: rgba(56, 189, 248, 0.10);
            }
            QPushButton#ComposerPlusMenuRow:pressed {
                background: rgba(56, 189, 248, 0.16);
            }
            QLabel#ComposerPlusMenuIcon {
                color: #7dd3fc;
                background: rgba(34, 211, 238, 0.08);
                border-radius: 4px;
                padding: 2px 1px;
                font-size: 8px;
            }
            QLabel#ComposerPlusMenuTitle {
                color: #e2e8f0;
                font-size: 12px;
                background: transparent;
            }
            QLabel#ComposerPlusMenuSub {
                color: #64748b;
                font-size: 10px;
                background: transparent;
            }
            QLabel#ComposerPlusMenuArrow {
                color: #7dd3fc;
                font-size: 16px;
                font-weight: 600;
                background: transparent;
            }
            """
        )


class ComposerPlusMenu(QFrame):
    """입력창 + 버튼용 팝업 — Skills/MCP는 관리 창으로."""

    add_photos = pyqtSignal()
    add_files = pyqtSignal()
    skill_chosen = pyqtSignal(str)
    mcp_chosen = pyqtSignal(str)
    open_skills_panel = pyqtSignal()
    open_mcp_panel = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        self.setObjectName("ComposerPlusMenu")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(
            """
            QFrame#ComposerPlusMenu {
                background-color: #111827;
                border: 1px solid rgba(56, 189, 248, 0.22);
                border-radius: 10px;
            }
            QLabel#ComposerPlusSection {
                color: #64748b;
                font-size: 9px;
                font-weight: 600;
                letter-spacing: 0.6px;
                padding: 6px 10px 1px 10px;
                background: transparent;
            }
            QFrame#ComposerPlusSep {
                background: rgba(148, 163, 184, 0.14);
                border: none;
                max-height: 1px;
                margin: 3px 8px;
            }
            """
        )

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        main = QWidget()
        main.setFixedWidth(220)
        root = QVBoxLayout(main)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(1)

        photos = _MenuRow("IMG", "Add Photos & Videos", "이미지·동영상")
        photos.clicked.connect(self._on_photos)
        root.addWidget(photos)

        files = _MenuRow("FILE", "Add Files", "파일 첨부")
        files.clicked.connect(self._on_files)
        root.addWidget(files)

        sep1 = QFrame()
        sep1.setObjectName("ComposerPlusSep")
        sep1.setFixedHeight(1)
        root.addWidget(sep1)

        n_skills = len(list_hermes_skill_names())
        skills_row = _MenuRow(
            "SK",
            "Skills",
            f"{n_skills} linked" if n_skills else "manage ›",
            show_arrow=True,
        )
        skills_row.clicked.connect(self._on_open_skills)
        root.addWidget(skills_row)

        sep2 = QFrame()
        sep2.setObjectName("ComposerPlusSep")
        sep2.setFixedHeight(1)
        root.addWidget(sep2)

        n_mcp = len(list_hermes_mcp_names())
        mcp_row = _MenuRow(
            "MCP",
            "MCP",
            f"{n_mcp} servers" if n_mcp else "manage ›",
            show_arrow=True,
        )
        mcp_row.clicked.connect(self._on_open_mcp)
        root.addWidget(mcp_row)

        outer.addWidget(main, 0)

    def _on_photos(self) -> None:
        self.add_photos.emit()
        self.hide()

    def _on_files(self) -> None:
        self.add_files.emit()
        self.hide()

    def _on_open_skills(self) -> None:
        self.hide()
        self.open_skills_panel.emit()

    def _on_open_mcp(self) -> None:
        self.hide()
        self.open_mcp_panel.emit()

    def popup_above(self, anchor: QWidget) -> None:
        self.adjustSize()
        pos = anchor.mapToGlobal(QPoint(0, 0))
        x = pos.x()
        y = pos.y() - self.sizeHint().height() - 6
        self.move(x, max(8, y))
        self.show()
        self.raise_()
        self.activateWindow()


class ComposerPlusButton(QPushButton):
    """입력창 + 원형 버튼 — ChatModelShell과 동일 슬레이트 톤."""

    _BTN = 28
    _ARM = 5.5
    _THICK = 1.35
    # ChatModelShell / 드롭다운 배경 (#0f172a)
    _SHELL_RGB = (15, 23, 42)
    _PLUS_RGB = (226, 232, 240)  # model combo 텍스트 #e2e8f0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ComposerPlusButton")
        self.setText("")
        self.setToolTip("Add photos, files, skills, MCP")
        self.setFixedSize(self._BTN, self._BTN)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        r, g, b = self._SHELL_RGB
        self.setStyleSheet(
            f"""
            QPushButton#ComposerPlusButton {{
                background-color: rgba({r}, {g}, {b}, 0.85);
                border: 1px solid rgba(56, 189, 248, 0.28);
                border-radius: 14px;
                padding: 0;
            }}
            QPushButton#ComposerPlusButton:hover {{
                background-color: rgba({r}, {g}, {b}, 1.0);
                border-color: rgba(56, 189, 248, 0.45);
            }}
            QPushButton#ComposerPlusButton:pressed {{
                background-color: rgba({r}, {g}, {b}, 1.0);
                border-color: rgba(56, 189, 248, 0.6);
            }}
            """
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        arm = float(self._ARM)
        pr, pg, pb = self._PLUS_RGB

        for width, alpha in ((2.4, 70), (self._THICK, 230)):
            pen = QPen(QColor(pr, pg, pb, alpha))
            pen.setWidthF(width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(cx - arm, cy), QPointF(cx + arm, cy))
            painter.drawLine(QPointF(cx, cy - arm), QPointF(cx, cy + arm))
        painter.end()


class ComposerSendButton(QPushButton):
    """전송 ↑ — 원형 배경은 고정, 활성 시 화살표만 +와 동일 색·크기."""

    _BTN = ComposerPlusButton._BTN
    _ARM = ComposerPlusButton._ARM
    _THICK = ComposerPlusButton._THICK
    _ARROW_RGB = ComposerPlusButton._PLUS_RGB  # #e2e8f0
    _ARROW_MUTED_RGB = (71, 85, 105)  # 기존 disabled 화살표 #475569

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ChatSendButton")
        self.setText("")
        self.setToolTip("전송")
        self.setFixedSize(self._BTN, self._BTN)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setEnabled(False)
        # 원형 배경: 활성/비활성 모두 기존 disabled 톤 유지 (인디고 전환 없음)
        self.setStyleSheet(
            """
            QPushButton#ChatSendButton {
                background-color: #1e293b;
                border: none;
                border-radius: 14px;
                padding: 0;
            }
            QPushButton#ChatSendButton:hover:enabled {
                background-color: #1e293b;
            }
            QPushButton#ChatSendButton:pressed:enabled {
                background-color: #1e293b;
            }
            QPushButton#ChatSendButton:disabled {
                background-color: #1e293b;
            }
            """
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        arm = float(self._ARM)
        if self.isEnabled():
            r, g, b = self._ARROW_RGB
            alphas = (70, 230)
        else:
            r, g, b = self._ARROW_MUTED_RGB
            alphas = (50, 180)

        # +와 동일 arm/stroke — 위로 향하는 화살표
        tip_y = cy - arm
        base_y = cy + arm
        head_y = cy - arm * 0.15
        for width, alpha in ((2.4, alphas[0]), (self._THICK, alphas[1])):
            pen = QPen(QColor(r, g, b, alpha))
            pen.setWidthF(width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(QPointF(cx, base_y), QPointF(cx, tip_y))
            painter.drawLine(QPointF(cx, tip_y), QPointF(cx - arm * 0.72, head_y))
            painter.drawLine(QPointF(cx, tip_y), QPointF(cx + arm * 0.72, head_y))
        painter.end()


if __name__ == "__main__":
    assert isinstance(list_hermes_skill_names(), list)
    assert isinstance(list_hermes_mcp_names(), list)
    assert ComposerSendButton._BTN == ComposerPlusButton._BTN
    assert ComposerSendButton._ARM == ComposerPlusButton._ARM
    assert ComposerSendButton._ARROW_RGB == ComposerPlusButton._PLUS_RGB
    print(
        "composer_plus_menu ok",
        "skills",
        len(list_hermes_skill_names()),
        "mcp",
        len(list_hermes_mcp_names()),
    )
