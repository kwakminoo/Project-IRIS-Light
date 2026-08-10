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
    QPushButton,
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
from iris.monitoring.pin_store import MAX_PINS, PinStore, PinnedTarget
from iris.monitoring.pinned_monitor import status_label
from iris.monitoring.screen_capture import (
    CaptureResult,
    capture_region,
    capture_window_by_hwnd,
)

from iris.ui.shared.glass_panel import wrap_glass_panel
from iris.ui.shared.section_header import apply_section_panel_layout, make_section_header
from iris.ui.shared.theme_tokens import TOKENS

if TYPE_CHECKING:
    from iris.storage.database import Database

_REFRESH_MS = 4_000   # 4초마다 썸네일 갱신
_MAX_WINDOWS = 12
_CAPTURE_PER_WINDOW_SEC = 2.5  # PrintWindow 무한 대기 방지
_THUMB_W = 320
_THUMB_H = 180

# U+1F588 BLACK PUSHPIN + VS15(U+FE0E, 텍스트 표현 요청).
# 📌(U+1F4CC)·📍(U+1F4CD)는 폰트가 자체 색을 가진 컬러 이모지라 color가
# 먹지 않아 회색/흰색으로 칠할 수 없다. 이 글리프는 단색이라 color가 적용된다.
_PIN_GLYPH = "\U0001F588︎"

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

    def set_capture(self, cap: Optional[CaptureResult], minimized: bool = False) -> None:
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
            self.setText("최소화됨" if minimized else "캡처 불가")
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
    - 제목 옆 고정(📌) 버튼으로 최대 3개까지 AI 감시 대상 지정
    """

    pin_changed = pyqtSignal()

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
        self._pins: Optional[PinStore] = None
        self._last_snaps: list[_WindowSnap] = []

        inner = QWidget()
        inner.setObjectName("UnifiedMonitorPanelInner")
        root = QVBoxLayout(inner)
        apply_section_panel_layout(root)

        root.addWidget(make_section_header("MONITOR / SCREEN"))

        self._pin_hint = QLabel("")
        self._pin_hint.setWordWrap(True)
        self._pin_hint.setStyleSheet(
            f"color: {TOKENS.text_muted}; font-size: 10px;"
            " background: transparent; border: none;"
        )
        self._pin_hint.hide()
        root.addWidget(self._pin_hint)

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

    def set_pin_store(self, pins: PinStore) -> None:
        """고정 목록 연결 — 설정되기 전에는 고정 버튼이 표시되지 않는다."""
        self._pins = pins
        self._update_pin_hint()

    def refresh_now(self) -> None:
        self._start_capture()

    def rerender_pins(self) -> None:
        """분석 결과만 바뀐 경우 — 캡처 없이 마지막 스냅으로 다시 그린다."""
        if self._shutdown:
            return
        self._update_pin_hint()
        self._render(self._last_snaps, self._load_monitor_meta())

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
        self._last_snaps = snaps
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
                pin = self._pins.get(snap.info.title) if self._pins else None
                card = _make_card(
                    snap,
                    meta,
                    self._focus_window,
                    pin=pin,
                    pin_enabled=self._pins is not None,
                    on_toggle_pin=self._toggle_pin,
                )
                self._inner_lay.addWidget(card)

        self._inner_lay.addStretch(1)

    # ------------------------------------------------------------------
    # pin
    # ------------------------------------------------------------------

    def _toggle_pin(self, info: WindowInfo) -> None:
        if self._pins is None:
            return
        ok, reason = self._pins.toggle(info.title, info.hwnd)
        if not ok and reason == "full":
            self._flash_pin_hint(
                f"고정은 최대 {MAX_PINS}개까지입니다 — 다른 창을 먼저 해제하세요."
            )
        else:
            self._update_pin_hint()
            self.pin_changed.emit()
        self.rerender_pins()

    def _update_pin_hint(self) -> None:
        if self._pins is None:
            self._pin_hint.hide()
            return
        count = self._pins.count()
        if count <= 0:
            self._pin_hint.hide()
            return
        self._pin_hint.setStyleSheet(
            f"color: {TOKENS.text_muted}; font-size: 10px;"
            " background: transparent; border: none;"
        )
        self._pin_hint.setText(f"AI 감시 중 {count}/{MAX_PINS}")
        self._pin_hint.show()

    def _flash_pin_hint(self, message: str) -> None:
        self._pin_hint.setStyleSheet(
            "color: #eab308; font-size: 10px; background: transparent; border: none;"
        )
        self._pin_hint.setText(message)
        self._pin_hint.show()
        QTimer.singleShot(4_000, self._update_pin_hint)

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
        #    최소화 창은 그 자리에 아무것도 없으므로 폴백을 쓰면 뒤에 있는
        #    다른 창을 캡처해 버린다 — PrintWindow가 실패하면 캡처 없이 둔다.
        if cap is None and not info.minimized and info.width > 0 and info.height > 0:
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


def _make_pin_button(
    info: WindowInfo, pinned: bool, on_toggle
) -> QPushButton:
    """제목 옆 고정 버튼 — 누르면 AI가 그 창을 주기적으로 분석한다."""
    btn = QPushButton(_PIN_GLYPH)
    btn.setFixedSize(22, 22)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setToolTip(
        f"AI 감시 해제: {info.title}" if pinned else f"AI 감시 고정 (최대 {MAX_PINS}개): {info.title}"
    )
    # padding: 0 필수 — 테마의 기본 QPushButton 규칙이 padding 6px 12px라서,
    # 22×22 고정 크기 버튼에서는 글리프가 밀려나 아무것도 안 보인다.
    color = "#ffffff" if pinned else TOKENS.text_secondary
    btn.setStyleSheet(
        f"""
        QPushButton {{
            background: transparent;
            border: none;
            padding: 0;
            font-size: 15px;
            color: {color};
        }}
        QPushButton:hover {{ color: #ffffff; }}
        """
    )
    btn.clicked.connect(lambda _=False, i=info: on_toggle(i))
    return btn


def _make_pin_status_widget(pin: PinnedTarget) -> QWidget:
    """고정된 창의 AI 분석 결과 블록."""
    box = QWidget()
    box.setStyleSheet("background: transparent;")
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(2)

    color = _STATUS_COLOR.get(pin.status.value, "#94a3b8")
    head = QHBoxLayout()
    head.setContentsMargins(0, 0, 0, 0)
    head.setSpacing(6)

    dot = QLabel("●")
    dot.setStyleSheet(f"color: {color}; font-size: 11px; background: transparent; border: none;")
    head.addWidget(dot)

    if pin.analyzing:
        text = "AI 분석 중…"
    else:
        text = status_label(pin.status)
        if pin.confidence > 0:
            text += f" · {pin.confidence:.0%}"
        if pin.last_checked_at:
            text += f" · {pin.last_checked_at}"
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {color}; font-size: 11px; font-weight: 600;"
        " background: transparent; border: none;"
    )
    head.addWidget(lbl)
    head.addStretch(1)

    head_wrap = QWidget()
    head_wrap.setStyleSheet("background: transparent;")
    head_wrap.setLayout(head)
    lay.addWidget(head_wrap)

    if pin.reason and not pin.analyzing:
        reason = QLabel(pin.reason[:200])
        reason.setWordWrap(True)
        reason.setStyleSheet(
            "color: #94a3b8; font-size: 10px; background: transparent; border: none;"
        )
        lay.addWidget(reason)

    if pin.recommended_action and not pin.analyzing:
        act = QLabel(f"권장: {pin.recommended_action[:160]}")
        act.setWordWrap(True)
        act.setStyleSheet(
            "color: #cbd5e1; font-size: 10px; background: transparent; border: none;"
        )
        lay.addWidget(act)

    return box


def _make_card(
    snap: _WindowSnap,
    meta: Optional[_MonitorMeta],
    on_click,
    *,
    pin: Optional[PinnedTarget] = None,
    pin_enabled: bool = False,
    on_toggle_pin=None,
) -> QFrame:
    """1열 카드: [썸네일] / [제목 + 고정버튼] / [AI 분석 상태] / [모니터링 상태]"""
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
    img_lbl.set_capture(snap.cap, snap.info.minimized)

    v.addWidget(img_lbl, alignment=Qt.AlignmentFlag.AlignLeft)

    # 2) 제목 + 고정 버튼
    title = snap.info.title
    title_lbl = QLabel(title)
    title_lbl.setToolTip(title)
    title_lbl.setWordWrap(True)
    title_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    title_lbl.setStyleSheet(
        "color: #e2e8f0; font-size: 12px; font-weight: 600; background: transparent; border: none;"
    )

    title_row = QHBoxLayout()
    title_row.setContentsMargins(0, 0, 0, 0)
    title_row.setSpacing(4)
    title_row.addWidget(title_lbl, 1)
    if pin_enabled and on_toggle_pin is not None:
        title_row.addWidget(
            _make_pin_button(snap.info, pin is not None, on_toggle_pin), 0
        )
    title_wrap = QWidget()
    title_wrap.setStyleSheet("background: transparent;")
    title_wrap.setLayout(title_row)
    title_wrap.setFixedWidth(_THUMB_W)
    v.addWidget(title_wrap, alignment=Qt.AlignmentFlag.AlignLeft)

    # 3) AI 감시 결과 (고정된 경우)
    if pin is not None:
        v.addWidget(_make_pin_status_widget(pin))

    # 4) 모니터링 상태 (등록된 경우)
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
