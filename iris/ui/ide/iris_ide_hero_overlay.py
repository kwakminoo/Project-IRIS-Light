"""IRIS IDE 히어로 — 랜딩 사이트 첫 화면과 동일 톤(타이틀·코너·상태·폴더 CTA)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QPointF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from iris.storage.ide_recent_folders import (
    list_recent_folders,
    next_iris_project_dir,
    record_opened_folder,
    truncate_path_middle,
)
from iris.ui.shared.theme_tokens import TOKENS

_CORNER = 22
_TITLE_PX = 72


class _RecentChip(QPushButton):
    path_chosen = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path = ""
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self.setStyleSheet(
            "QPushButton {"
            f" color: {TOKENS.text_secondary};"
            " background: transparent;"
            " border: none;"
            " font-size: 12px;"
            " text-align: left;"
            " padding: 2px 0;"
            "}"
            f"QPushButton:hover {{ color: {TOKENS.neon_cyan}; }}"
        )
        self.clicked.connect(self._emit)

    def set_entry(self, name: str, path: str) -> None:
        self._path = path
        tip = truncate_path_middle(path, 48) if path else ""
        self.setText(f"{name}  ·  {tip}" if path else "")
        self.setVisible(bool(path))

    def _emit(self) -> None:
        if self._path:
            self.path_chosen.emit(self._path)


class IrisIdeHeroOverlay(QWidget):
    """단일 창 히어로 — 구체는 MainWindow ParticleVisualizer, 여기는 크롬·CTA만."""

    folder_opened = pyqtSignal(str)
    folder_created = pyqtSignal(str)
    dismiss_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("IrisIdeHeroOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAcceptDrops(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(48, 40, 48, 28)
        root.setSpacing(0)
        root.addStretch(3)

        self._boot = QLabel("SYS.BOOT — IRIS IDE · LOCAL AGENT", self)
        self._boot.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._boot.setStyleSheet(
            f"color: {TOKENS.neon_cyan};"
            " font-size: 11px;"
            " letter-spacing: 4px;"
            " background: transparent;"
            f" font-family: {TOKENS.font_mono};"
        )
        root.addWidget(self._boot)
        root.addSpacing(10)

        self._title = QLabel("IRIS IDE", self)
        self._title.setObjectName("IrisIdeHeroTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._title.setStyleSheet(
            "color: #eef5ff;"
            f" font-size: {_TITLE_PX}px;"
            " font-weight: 400;"
            " letter-spacing: 12px;"
            " padding-left: 12px;"
            " background: transparent;"
            " text-shadow:"
            "  -1px 0 rgba(255,45,111,0.42),"
            "   1px 0 rgba(34,211,238,0.55),"
            "   0 0 18px rgba(34,211,238,0.38),"
            "   0 0 48px rgba(96,165,250,0.22);"
        )
        root.addWidget(self._title)
        root.addSpacing(18)

        st = QHBoxLayout()
        st.setSpacing(22)
        st.addStretch(1)
        for label, value, on in (
            ("OLLAMA", ":11434", True),
            ("HERMES", ":8642", True),
            ("STATE", "IDLE", False),
        ):
            st.addWidget(self._status_pill(label, value, on))
        st.addStretch(1)
        root.addLayout(st)
        root.addSpacing(28)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch(1)
        self.btn_open = self._cta("Open folder")
        self.btn_create = self._cta("Create folder")
        self.btn_open.clicked.connect(self._pick_open)
        self.btn_create.clicked.connect(self._pick_create)
        btn_row.addWidget(self.btn_open)
        btn_row.addWidget(self.btn_create)
        btn_row.addStretch(1)
        root.addLayout(btn_row)
        root.addSpacing(16)

        self._recent_hdr = QLabel("Recent", self)
        self._recent_hdr.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._recent_hdr.setStyleSheet(
            f"color: {TOKENS.text_muted}; font-size: 11px; background: transparent;"
            " letter-spacing: 2px;"
        )
        self._recent_hdr.hide()
        self._recent_box = QVBoxLayout()
        self._recent_box.setSpacing(2)
        self._recent_box.addWidget(self._recent_hdr)
        self._recent_chips: list[_RecentChip] = []
        for _ in range(4):
            chip = _RecentChip(self)
            chip.path_chosen.connect(self._emit_folder)
            chip.hide()
            self._recent_box.addWidget(chip, 0, Qt.AlignmentFlag.AlignHCenter)
            self._recent_chips.append(chip)
        root.addLayout(self._recent_box)
        root.addStretch(4)

        meta = QHBoxLayout()
        left = QLabel("IRIS IDE · Companion ready", self)
        right = QLabel("v0.1.0-light · Open Source", self)
        for m in (left, right):
            m.setStyleSheet(
                f"color: {TOKENS.text_muted};"
                " font-size: 10px;"
                " letter-spacing: 2px;"
                " background: transparent;"
                f" font-family: {TOKENS.font_mono};"
            )
        meta.addWidget(left)
        meta.addStretch(1)
        meta.addWidget(right)
        root.addLayout(meta)

        self._phase = 0.0
        self._tick = QTimer(self)
        self._tick.setInterval(50)
        self._tick.timeout.connect(self._on_tick)
        self.refresh_recent()

    def _status_pill(self, label: str, value: str, on: bool) -> QWidget:
        w = QWidget(self)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        dot = QLabel("●", w)
        color = TOKENS.success if on else TOKENS.text_muted
        dot.setStyleSheet(
            f"color: {color}; font-size: 9px; background: transparent;"
        )
        text = QLabel(f"{label}  {value}", w)
        text.setStyleSheet(
            f"color: {TOKENS.text_secondary};"
            " font-size: 10px;"
            " letter-spacing: 2px;"
            " background: transparent;"
            f" font-family: {TOKENS.font_mono};"
        )
        lay.addWidget(dot)
        lay.addWidget(text)
        return w

    def _cta(self, label: str) -> QPushButton:
        btn = QPushButton(label, self)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumSize(148, 40)
        btn.setStyleSheet(
            "QPushButton {"
            f" color: {TOKENS.text_primary};"
            " background: rgba(5, 12, 26, 0.35);"
            f" border: 1px solid {TOKENS.border_subtle};"
            " border-radius: 6px;"
            " font-size: 13px;"
            " letter-spacing: 1px;"
            " padding: 8px 18px;"
            "}"
            f"QPushButton:hover {{"
            f" border-color: {TOKENS.neon_cyan};"
            f" background: {TOKENS.panel_hover};"
            "}}"
        )
        return btn

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._tick.isActive():
            self._tick.start()
        self.refresh_recent()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self._tick.stop()

    def _on_tick(self) -> None:
        self._phase += 0.04
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()

        # vignette — 사이트 .fx-vig
        vig = QRadialGradient(w * 0.5, h * 0.5, max(w, h) * 0.72)
        vig.setColorAt(0.0, QColor(34, 211, 238, 12))
        vig.setColorAt(0.45, QColor(0, 0, 0, 0))
        vig.setColorAt(1.0, QColor(2, 4, 8, 210))
        p.fillRect(0, 0, w, h, vig)

        # orbit rings (사이트 orbit 톤)
        cx, cy = w * 0.5, h * 0.42
        base = min(w, h) * 0.38
        pen = QPen(QColor(96, 165, 250, 55))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i, ratio in enumerate((0.72, 0.92, 1.12)):
            r = base * ratio
            if i == 1:
                dash = QPen(QColor(96, 165, 250, 40))
                dash.setWidthF(1.0)
                dash.setDashPattern([2, 7])
                p.setPen(dash)
            else:
                p.setPen(pen)
            p.drawEllipse(QPointF(cx, cy), r, r)

        # corner brackets
        m = 28
        top = 52
        bot = h - 28
        c = QColor(34, 211, 238, 90)
        pen = QPen(c)
        pen.setWidthF(1.2)
        p.setPen(pen)
        for x, y, dx, dy in (
            (m, top, 1, 1),
            (w - m, top, -1, 1),
            (m, bot, 1, -1),
            (w - m, bot, -1, -1),
        ):
            p.drawLine(int(x), int(y), int(x + dx * _CORNER), int(y))
            p.drawLine(int(x), int(y), int(x), int(y + dy * _CORNER))
        p.end()

    def refresh_recent(self) -> None:
        recent = list_recent_folders(4)
        self._recent_hdr.setVisible(bool(recent))
        for i, chip in enumerate(self._recent_chips):
            if i < len(recent):
                name, path = recent[i]
                chip.set_entry(name, path)
            else:
                chip.set_entry("", "")

    def _emit_folder(self, path: str) -> None:
        record_opened_folder(Path(path))
        self.refresh_recent()
        self.folder_opened.emit(path)

    def _pick_open(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open folder")
        if path:
            self._emit_folder(path)

    def _pick_create(self) -> None:
        parent = QFileDialog.getExistingDirectory(self, "Create folder — 상위 디렉터리 선택")
        if not parent:
            return
        new_dir = next_iris_project_dir(Path(parent))
        new_dir.mkdir(parents=True, exist_ok=False)
        resolved = str(new_dir.resolve())
        record_opened_folder(new_dir)
        self.refresh_recent()
        self.folder_created.emit(resolved)
        self.folder_opened.emit(resolved)
