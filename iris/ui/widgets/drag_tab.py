"""Draggable top chrome with stable window controls."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from iris.learning.models import LearningState
from iris.ui.window.top_status_header import STATUS_BLOCK_HEIGHT

_MIC_BTN_W = 36
_MIC_BTN_H = 26
_LEARN_BTN_W = 36
_LEARN_BTN_H = 26


def _win_ctrl_button(text: str, tooltip: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("WinCtrl")
    btn.setToolTip(tooltip)
    btn.setFixedSize(30, 26)
    btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return btn


def _heartbeat_path(w: float, h: float) -> QPainterPath:
    """양끝 직선 + 가운데 심박 스파이크 네온 라인 경로."""
    mid_y = h * 0.52
    # x 비율: 좌측 직선 → 심박 → 우측 직선
    pts = (
        (0.06, mid_y),
        (0.30, mid_y),
        (0.36, mid_y - h * 0.08),   # 작은 상승
        (0.40, mid_y + h * 0.06),   # 살짝 하강
        (0.46, mid_y - h * 0.38),   # 큰 스파이크 꼭대기
        (0.52, mid_y + h * 0.34),   # 깊은 하강
        (0.58, mid_y - h * 0.10),   # 회복 상승
        (0.64, mid_y),              # 베이스라인 복귀
        (0.94, mid_y),
    )
    path = QPainterPath()
    path.moveTo(QPointF(pts[0][0] * w, pts[0][1]))
    for x_ratio, y in pts[1:]:
        path.lineTo(QPointF(x_ratio * w, y))
    return path


def _waveform_mic_icon(*, active: bool, size: QSize | None = None) -> QIcon:
    """얇은 네온 심박 라인 아이콘 (양끝 직선, 가운데 파형)."""
    sz = size or QSize(_MIC_BTN_W, _MIC_BTN_H)
    pm = QPixmap(sz)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    base = QColor(248, 113, 113) if active else QColor(34, 211, 238)
    path = _heartbeat_path(float(sz.width()), float(sz.height()))

    # 얇은 네온사인: 바깥 글로우 → 코어 하이라이트
    for width, alpha in ((3.6, 28), (2.0, 70), (0.95, 230), (0.45, 255)):
        color = QColor(base)
        color.setAlpha(alpha)
        # 가장 안쪽은 거의 흰색 하이라이트
        if width < 0.6:
            color = QColor(255, 255, 255, alpha)
        pen = QPen(color)
        pen.setWidthF(width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    painter.end()
    return QIcon(pm)


def _learning_icon(state: LearningState, *, size: QSize | None = None, pulse: float = 1.0) -> QIcon:
    """미니멀 모니터 선형 아이콘 — 화면 베젤 + 스탠드 (26–30px에서도 식별)."""
    sz = size or QSize(_LEARN_BTN_W, _LEARN_BTN_H)
    pm = QPixmap(sz)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    if state == LearningState.IDLE:
        base = QColor(100, 116, 139)  # slate
        glow = False
    elif state == LearningState.ERROR:
        base = QColor(248, 113, 113)
        glow = True
    else:
        # RECORDING / PROCESSING — neon cyan
        base = QColor(34, 211, 238)
        glow = True

    w, h = float(sz.width()), float(sz.height())
    alpha_scale = max(0.35, min(1.0, pulse))

    # 비율: 얇은 모니터 — 화면 영역 + 목 + 받침대
    screen = (
        0.14 * w,
        0.12 * h,
        0.72 * w,
        0.52 * h,
    )  # x, y, ww, hh
    neck_top = screen[1] + screen[3]
    neck_x = 0.46 * w
    neck_w = 0.08 * w
    neck_h = 0.14 * h
    base_y = neck_top + neck_h
    base_x = 0.28 * w
    base_w = 0.44 * w
    base_h = 0.08 * h

    def _stroke(width: float, alpha: int) -> None:
        color = QColor(base)
        color.setAlpha(int(alpha * alpha_scale))
        pen = QPen(color)
        pen.setWidthF(width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    layers = ((2.8, 24), (1.5, 70), (0.95, 220)) if glow else ((1.15, 175),)
    screen_rect = QRectF(screen[0], screen[1], screen[2], screen[3])
    for width, alpha in layers:
        _stroke(width, alpha)
        painter.drawRoundedRect(screen_rect, 1.6, 1.6)
        painter.drawLine(
            QPointF(neck_x + neck_w * 0.5, neck_top),
            QPointF(neck_x + neck_w * 0.5, base_y),
        )
        painter.drawLine(
            QPointF(base_x, base_y + base_h * 0.5),
            QPointF(base_x + base_w, base_y + base_h * 0.5),
        )

    inset = 2.2
    inner = screen_rect.adjusted(inset, inset, -inset, -inset)
    if inner.width() > 2 and inner.height() > 2:
        if glow:
            fill = QColor(base)
            fill.setAlpha(int(36 * alpha_scale))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(inner, 1.0, 1.0)
            dot = QColor(255, 255, 255, int(210 * alpha_scale))
            painter.setBrush(dot)
            painter.drawEllipse(
                QPointF(inner.right() - 2.2, inner.bottom() - 2.0),
                1.1,
                1.1,
            )
        else:
            _stroke(0.7, 120)
            painter.drawRoundedRect(inner, 1.0, 1.0)

    painter.end()
    return QIcon(pm)


class DragTab(QWidget):
    """Frameless title bar with drag handling and window controls."""

    profile_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    minimize_clicked = pyqtSignal()
    maximize_clicked = pyqtSignal()
    ide_toggle_clicked = pyqtSignal()
    learning_clicked = pyqtSignal()
    mic_clicked = pyqtSignal()

    def __init__(self, parent_window: QWidget) -> None:
        super().__init__()
        self.setObjectName("DragTab")
        self._win = parent_window
        # 상태 2행 + 상하 패딩에 맞춘 고정 높이
        chrome_h = STATUS_BLOCK_HEIGHT + 12
        self.setFixedHeight(chrome_h)
        self.setMinimumHeight(chrome_h)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(10)

        self._title = QLabel("IRIS")
        self._title.setObjectName("DragTitle")
        self._title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._title.setFixedHeight(STATUS_BLOCK_HEIGHT)
        self._title.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        lay.addWidget(self._title, 0, Qt.AlignmentFlag.AlignVCenter)

        self._status_column = QWidget()
        self._status_column.setObjectName("DragTabStatusColumn")
        self._status_column.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._status_column.setFixedHeight(STATUS_BLOCK_HEIGHT)
        self._status_column_lay = QVBoxLayout(self._status_column)
        self._status_column_lay.setContentsMargins(0, 0, 0, 0)
        self._status_column_lay.setSpacing(0)
        self._status_column.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        lay.addWidget(self._status_column, 0, Qt.AlignmentFlag.AlignVCenter)

        lay.addStretch(1)

        ctrl_row = QHBoxLayout()
        ctrl_row.setContentsMargins(0, 0, 0, 0)
        ctrl_row.setSpacing(4)
        ctrl_row.setSizeConstraint(QHBoxLayout.SizeConstraint.SetFixedSize)

        # companion(Iris≈20%)에서만 표시 — 일반 모드는 좌측 하단 IDE로 진입
        self._btn_ide = _win_ctrl_button("</>", "일반 레이아웃으로 복귀")
        self._btn_ide.hide()
        self._btn_learning = QPushButton()
        self._btn_learning.setObjectName("WinCtrlLearning")
        self._btn_learning.setToolTip("업무 학습 시작")
        self._btn_learning.setFixedSize(_LEARN_BTN_W, _LEARN_BTN_H)
        self._btn_learning.setIconSize(QSize(_LEARN_BTN_W - 8, _LEARN_BTN_H - 6))
        self._btn_learning.setIcon(_learning_icon(LearningState.IDLE))
        self._btn_learning.setText("")
        self._btn_learning.setCheckable(True)
        self._btn_learning.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._btn_learning.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_mic = QPushButton()
        self._btn_mic.setObjectName("WinCtrlMic")
        self._btn_mic.setToolTip("음성 인식 켜기")
        self._btn_mic.setFixedSize(_MIC_BTN_W, _MIC_BTN_H)
        self._btn_mic.setIconSize(QSize(_MIC_BTN_W - 8, _MIC_BTN_H - 6))
        self._btn_mic.setIcon(_waveform_mic_icon(active=False))
        self._btn_mic.setText("")
        self._btn_mic.setCheckable(True)
        self._btn_mic.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._btn_mic.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_profile = _win_ctrl_button("👤", "사용자 프로필")
        self._btn_settings = _win_ctrl_button("⚙", "설정")
        self._btn_min = _win_ctrl_button("−", "창 내리기")
        self._btn_max = _win_ctrl_button("□", "전체 화면")
        self._btn_close = _win_ctrl_button("×", "닫기")

        for btn in (
            self._btn_ide,
            self._btn_learning,
            self._btn_mic,
            self._btn_profile,
            self._btn_settings,
            self._btn_min,
            self._btn_max,
            self._btn_close,
        ):
            ctrl_row.addWidget(btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        lay.addLayout(ctrl_row)

        self._learning_state = LearningState.IDLE
        self._learning_pulse = 1.0
        self._learning_pulse_dir = -1
        self._learning_pulse_timer = QTimer(self)
        self._learning_pulse_timer.setInterval(80)
        self._learning_pulse_timer.timeout.connect(self._on_learning_pulse_tick)

        self._btn_ide.clicked.connect(self.ide_toggle_clicked.emit)
        self._btn_learning.clicked.connect(self.learning_clicked.emit)
        self._btn_mic.clicked.connect(self.mic_clicked.emit)
        self._btn_min.clicked.connect(self.minimize_clicked.emit)
        self._btn_max.clicked.connect(self.maximize_clicked.emit)
        self._btn_close.clicked.connect(parent_window.close)
        self._btn_profile.clicked.connect(self.profile_clicked.emit)
        self._btn_settings.clicked.connect(self.settings_clicked.emit)
        self._drag_pos = None

    def set_learning_state(self, state: LearningState) -> None:
        """MainWindow는 색을 직접 만지지 않고 이 API만 호출."""
        self._learning_state = state
        recording_like = state in {LearningState.RECORDING, LearningState.PROCESSING}
        self._btn_learning.blockSignals(True)
        self._btn_learning.setChecked(recording_like)
        self._btn_learning.blockSignals(False)
        self._btn_learning.setEnabled(state != LearningState.PROCESSING)
        if state == LearningState.IDLE:
            tip = "업무 학습 시작"
        elif state == LearningState.RECORDING:
            tip = "업무 학습 종료"
        elif state == LearningState.PROCESSING:
            tip = "업무 학습 정리 중…"
        else:
            tip = "업무 학습 오류"
        self._btn_learning.setToolTip(tip)
        if state == LearningState.PROCESSING:
            if not self._learning_pulse_timer.isActive():
                self._learning_pulse = 1.0
                self._learning_pulse_dir = -1
                self._learning_pulse_timer.start()
        else:
            self._learning_pulse_timer.stop()
            self._learning_pulse = 1.0
            self._btn_learning.setIcon(_learning_icon(state, pulse=1.0))

    def _on_learning_pulse_tick(self) -> None:
        self._learning_pulse += 0.08 * self._learning_pulse_dir
        if self._learning_pulse <= 0.4:
            self._learning_pulse = 0.4
            self._learning_pulse_dir = 1
        elif self._learning_pulse >= 1.0:
            self._learning_pulse = 1.0
            self._learning_pulse_dir = -1
        self._btn_learning.setIcon(
            _learning_icon(LearningState.PROCESSING, pulse=self._learning_pulse)
        )

    def set_mic_recording(self, recording: bool) -> None:
        self._btn_mic.blockSignals(True)
        self._btn_mic.setChecked(recording)
        self._btn_mic.blockSignals(False)
        self._btn_mic.setIcon(_waveform_mic_icon(active=recording))
        self._btn_mic.setToolTip("음성 인식 끄기" if recording else "음성 인식 켜기")

    def set_ide_companion_active(self, active: bool) -> None:
        """Companion(Iris≈20%): 상태행 숨김, IDE 버튼 표시, 최소화 숨김."""
        self._status_column.setVisible(not active)
        self._btn_ide.setVisible(active)
        self._btn_min.setVisible(not active)
        self._btn_ide.setToolTip("일반 레이아웃으로 복귀" if active else "IDE Companion")
        self._btn_ide.setProperty("companionActive", active)
        self._btn_ide.style().unpolish(self._btn_ide)
        self._btn_ide.style().polish(self._btn_ide)
        # 좁은 폭에서 타이틀이 컨트롤을 밀지 않게
        self._title.setStyleSheet(
            "font-size: 18px; letter-spacing: 2px;" if active else ""
        )

    def place_status_rows(self, primary: QWidget, backend: QWidget) -> None:
        """STATE/MODEL/TTS + 백엔드 — 단일 3열 그리드 또는 2행 블록."""
        # ponytail: setParent(None) 금지 — 숨긴 조상에서 떼면 top-level 창이 됨
        while self._status_column_lay.count():
            item = self._status_column_lay.takeAt(0)
            child = item.widget()
            if child is not None:
                child.hide()
        self._status_column_lay.addWidget(primary)
        primary.show()
        if backend.maximumHeight() > 0 and backend.isVisible():
            self._status_column_lay.addWidget(backend)
            backend.show()
        self._status_column.show()

    def place_primary_status(self, widget: QWidget) -> None:
        """레거시 호환 — primary만 넣을 때 backend 슬롯은 비움."""
        empty = QWidget()
        empty.setFixedHeight(0)
        empty.hide()
        self.place_status_rows(widget, empty)

    def set_maximized(self, maximized: bool) -> None:
        """Update maximize/restore button state."""
        if maximized:
            self._btn_max.setText("❐")
            self._btn_max.setToolTip("창 복원")
        else:
            self._btn_max.setText("□")
            self._btn_max.setToolTip("전체 화면")

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._drag_pos is not None and e.buttons() & Qt.MouseButton.LeftButton:
            if not self._win.isMaximized():
                self._win.move(e.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.maximize_clicked.emit()
        super().mouseDoubleClickEvent(e)
