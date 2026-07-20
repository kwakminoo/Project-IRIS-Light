"""실행 화면 + 모니터링 대상 통합 패널 — 우측 영역, 세로 1열.

요구사항 (사용자 지시):
- 두 영역(실행 화면 / 모니터링 대상)을 하나로 합침
- 썸네일은 세로 한 줄(1열)로 배치
- 실제 창 화면을 반영 (가려진 창 포함) → PrintWindow API 사용
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from iris.automation.window_controller import (
    WindowInfo,
    focus_and_place,
    focus_window_by_hwnd,
    list_visible_windows,
)
from iris.monitoring.screen_capture import (
    CaptureResult,
    capture_region,
    capture_window_by_hwnd,
)

from iris.ui.glass_panel import wrap_glass_panel
from iris.ui.section_header import apply_section_panel_layout, make_section_header
from iris.ui.theme_tokens import TOKENS

if TYPE_CHECKING:
    from iris.storage.database import Database

_REFRESH_MS = 4_000   # 4초마다 썸네일 갱신
_MAX_WINDOWS = 12
_CAPTURE_PER_WINDOW_SEC = 2.5  # PrintWindow 무한 대기 방지
_THUMB_W = 320
_THUMB_H = 180

_STATUS_COLOR = {
    "NORMAL": "#22c55e",
    "APPROVAL_WAITING": "#eab308",
    "ERROR_DETECTED": "#ef4444",
    "GENERATION_FAILED": "#ef4444",
    "TASK_STALLED": "#f97316",
    "RESPONSE_READY": "#3b82f6",
    "BUILD_NOT_STARTED": "#3b82f6",
    "USER_ACTION_REQUIRED": "#eab308",
    "UNKNOWN": "#64748b",
}


@dataclass
class _WindowSnap:
    """캡처 결과 + 메타. rgb_bytes 빈값이면 캡처 실패."""

    info: WindowInfo
    cap: Optional[CaptureResult]


@dataclass
class _MonitorMeta:
    """DB 모니터링 대상의 메타정보."""

    status: str
    last_event: str
    last_checked_at: str


class _CaptureSignals(QObject):
    done = pyqtSignal(list)  # list[_WindowSnap]


class _CaptureThumbLabel(QLabel):
    """캡처 화면 — 고정 썸네일 박스(320×180) 안에 비율 유지."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source: Optional[QPixmap] = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(_THUMB_W, _THUMB_H)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background: transparent; border: none;")

    def set_capture(self, cap: Optional[CaptureResult]) -> None:
        if cap and cap.rgb_bytes and cap.width > 0 and cap.height > 0:
            qimg = QImage(
                cap.rgb_bytes,
                cap.width,
                cap.height,
                cap.width * 3,
                QImage.Format.Format_RGB888,
            ).copy()
            self._source = QPixmap.fromImage(qimg)
            self.setText("")
            self.setStyleSheet("background: transparent; border: none;")
            self._apply_pixmap()
        else:
            self._source = None
            self.clear()
            self.setText("캡처 불가")
            self.setStyleSheet(
                "color: #64748b; font-size: 11px; background: transparent; border: none;"
            )

    def _apply_pixmap(self) -> None:
        if self._source is None or self._source.isNull():
            return
        scaled = self._source.scaled(
            _THUMB_W,
            _THUMB_H,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)


class UnifiedMonitorPanel(QWidget):
    """실행 중인 창의 라이브 썸네일 + 모니터링 상태를 한 패널·1열로 표시.

    - 캡처는 데몬 스레드에서 수행, pyqtSignal로 메인 스레드 갱신
    - 화면은 메모리 내 QPixmap으로만 유지(디스크 미저장 — Safety Policy)
    - 모니터링 등록된 창은 추가 상태 정보 표시
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("UnifiedMonitorPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(
            """
            QWidget#UnifiedMonitorPanel {
                background: transparent;
                border: none;
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            """
        )
        self._db: Optional["Database"] = None

        inner = QWidget()
        inner.setObjectName("UnifiedMonitorPanelInner")
        root = QVBoxLayout(inner)
        apply_section_panel_layout(root)

        root.addWidget(make_section_header("MONITOR / SCREEN"))

        self._scroll = QScrollArea()
        self._scroll.setObjectName("PanelScrollArea")
        self._scroll.setWidgetResizable(True)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._inner = QWidget()
        self._inner_lay = QVBoxLayout(self._inner)
        self._inner_lay.setContentsMargins(0, 0, 0, 0)
        self._inner_lay.setSpacing(8)
        self._inner_lay.addStretch(1)
        self._scroll.setWidget(self._inner)
        root.addWidget(self._scroll, 1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(wrap_glass_panel(inner))

        self._signals = _CaptureSignals(self)
        self._signals.done.connect(self._on_capture_done)
        self._capturing = False
        self._shutdown = False
        self.destroyed.connect(self._on_panel_destroyed)

        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_MS)
        self._timer.timeout.connect(self._start_capture)
        self._timer.start()
        # 첫 캡처는 창 표시·이벤트 루프 기동 후 — PrintWindow가 show() 중 메인 스레드를 막는 경우 완화
        QTimer.singleShot(600, self._start_capture)

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    def set_database(self, db: "Database") -> None:
        self._db = db

    def refresh_now(self) -> None:
        self._start_capture()

    def _on_panel_destroyed(self) -> None:
        # 패널 파괴 후 백그라운드 스레드가 Qt 시그널을 emit 하지 않도록
        self._shutdown = True
        self._timer.stop()

    # ------------------------------------------------------------------
    # capture
    # ------------------------------------------------------------------

    def _start_capture(self) -> None:
        if self._shutdown or self._capturing:
            return
        self._capturing = True
        sig = self._signals
        threading.Thread(
            target=_capture_all_windows,
            args=(sig,),
            daemon=True,
            name="iris-unified-capture",
        ).start()

    def _on_capture_done(self, snaps: list) -> None:
        self._capturing = False
        monitors = self._load_monitor_meta()
        self._render(snaps, monitors)

    def _load_monitor_meta(self) -> dict[str, _MonitorMeta]:
        """DB에서 모니터링 대상 메타 로드 — 제목(소문자)으로 키."""
        out: dict[str, _MonitorMeta] = {}
        if not self._db:
            return out
        try:
            rows = self._db.list_targets(True)
        except Exception:
            return out
        for row in rows:
            try:
                title = str(row["title"] or "").strip().lower()
                if not title:
                    continue
                out[title] = _MonitorMeta(
                    status=str(row["status"] or "UNKNOWN"),
                    last_event=str(row["last_event"] or "-"),
                    last_checked_at=str(row["last_checked_at"] or "-"),
                )
            except Exception:
                continue
        return out

    # ------------------------------------------------------------------
    # render
    # ------------------------------------------------------------------

    def _render(self, snaps: list[_WindowSnap], monitors: dict[str, _MonitorMeta]) -> None:
        # 기존 위젯 제거
        while self._inner_lay.count():
            item = self._inner_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not snaps:
            hint = QLabel(
                "No active screen preview\nSelect a running window to inspect."
            )
            hint.setObjectName("PanelEmptyHint")
            hint.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            hint.setWordWrap(True)
            hint.setStyleSheet(
                f"color: {TOKENS.text_muted}; font-size: {TOKENS.font_size_caption};"
                f" padding: {TOKENS.spacing_md}px; background: transparent; border: none;"
            )
            self._inner_lay.addWidget(hint)
        else:
            for snap in snaps:
                meta = _match_monitor(snap.info.title, monitors)
                card = _make_card(snap, meta, self._focus_window)
                self._inner_lay.addWidget(card)

        self._inner_lay.addStretch(1)

    def _focus_window(self, info: WindowInfo) -> None:
        ok = False
        if info.hwnd:
            ok = focus_window_by_hwnd(info.hwnd)
        if not ok:
            try:
                focus_and_place(info.title, info.left, info.top, info.width, info.height)
            except Exception:
                pass


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def _capture_all_windows(sig: _CaptureSignals) -> None:
    """데몬 스레드에서 모든 창 캡처. PrintWindow 우선, 실패 시 mss 폴백."""
    try:
        wins = list_visible_windows()
    except Exception:
        wins = []
    wins = wins[:_MAX_WINDOWS]

    snaps: list[_WindowSnap] = []
    for info in wins:
        cap: Optional[CaptureResult] = None
        # 1) PrintWindow (가려진 창 포함, hwnd 필요)
        if info.hwnd:
            cap = capture_window_by_hwnd(
                info.hwnd,
                timeout_sec=_CAPTURE_PER_WINDOW_SEC,
            )
        # 2) 폴백: mss 화면 영역 캡처
        if cap is None and info.width > 0 and info.height > 0:
            cap = capture_region(info.left, info.top, info.width, info.height)
        snaps.append(_WindowSnap(info, cap))

    try:
        sig.done.emit(snaps)
    except RuntimeError:
        # 패널이 닫힌 뒤 _CaptureSignals C++ 객체가 삭제된 경우
        pass


def _match_monitor(title: str, monitors: dict[str, _MonitorMeta]) -> Optional[_MonitorMeta]:
    """창 제목과 모니터링 대상 제목 매칭 (부분 일치, 소문자)."""
    if not monitors:
        return None
    tl = title.strip().lower()
    if tl in monitors:
        return monitors[tl]
    # 부분 일치
    for key, meta in monitors.items():
        if key and (key in tl or tl in key):
            return meta
    return None


def _make_card(
    snap: _WindowSnap,
    meta: Optional[_MonitorMeta],
    on_click,
) -> QFrame:
    """1열 카드: [썸네일] / [제목] / [모니터링 상태(있을 때)]"""
    fr = QFrame()
    fr.setFrameShape(QFrame.Shape.NoFrame)
    fr.setStyleSheet(
        "QFrame { background: transparent; border: none; }"
    )
    fr.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    fr.setCursor(Qt.CursorShape.PointingHandCursor)

    v = QVBoxLayout(fr)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(6)

    img_lbl = _CaptureThumbLabel()
    img_lbl.set_capture(snap.cap)

    v.addWidget(img_lbl, alignment=Qt.AlignmentFlag.AlignLeft)
    title = snap.info.title
    title_lbl = QLabel(title)
    title_lbl.setToolTip(title)
    title_lbl.setWordWrap(True)
    title_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    title_lbl.setStyleSheet(
        "color: #e2e8f0; font-size: 12px; font-weight: 600; background: transparent; border: none;"
    )
    v.addWidget(title_lbl, alignment=Qt.AlignmentFlag.AlignLeft)

    # 3) 모니터링 상태 (등록된 경우)
    if meta is not None:
        color = _STATUS_COLOR.get(meta.status, "#94a3b8")
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(6)
        dot = QLabel("●")
        dot.setStyleSheet(
            f"color: {color}; font-size: 12px; background: transparent; border: none;"
        )
        status_row.addWidget(dot)
        st = QLabel(f"상태: {meta.status}")
        st.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: 600;"
            "background: transparent; border: none;"
        )
        status_row.addWidget(st)
        status_row.addStretch(1)
        status_wrap = QWidget()
        status_wrap.setStyleSheet("background: transparent;")
        status_wrap.setLayout(status_row)
        v.addWidget(status_wrap)

        if meta.last_event and meta.last_event != "-":
            ev = QLabel(meta.last_event[:160])
            ev.setWordWrap(True)
            ev.setStyleSheet(
                "color: #94a3b8; font-size: 10px;"
                "background: transparent; border: none;"
            )
            v.addWidget(ev)

    # 클릭 → 포커스
    info = snap.info

    def _click(_ev: object, i: WindowInfo = info) -> None:  # type: ignore[misc]
        on_click(i)

    fr.mousePressEvent = _click  # type: ignore[method-assign]
    img_lbl.mousePressEvent = _click  # type: ignore[method-assign]

    return fr
