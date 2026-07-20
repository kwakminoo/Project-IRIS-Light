"""Iris 상태 비주얼라이저 — 구체 코어를 감싼 얇은 래퍼."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QEvent, QObject, QPointF, QRect, Qt, QTimer
from PyQt6.QtWidgets import QWidget

from iris.core.state_machine import AppState
from iris.ui.particle_visualizer import ParticleVisualizer

_DEBUG_ORB = os.environ.get("IRIS_DEBUG_ORB_GEOMETRY") == "1"
_MAX_STABILIZE_ATTEMPTS = 12
_SNAPSHOT_TOLERANCE_PX = 1
# ParticleVisualizer 기본 Y 비율과 동일 — 창 콘텐츠 기준 구체 목표 위치
_ORB_CENTER_Y_RATIO = 0.36


@dataclass(frozen=True)
class _GeomSnapshot:
    """안정화 검사용 geometry 스냅샷."""

    visualizer_rect: QRect
    anchor_geom: QRect
    local_center: QPointF
    window_state: Qt.WindowState
    device_pixel_ratio: float
    overlay_geom: QRect | None = None


class Visualizer(QWidget):
    """
    MainWindow가 기대하는 API(set_state(AppState), set_mic_level)를 유지하고
    실제 렌더링은 구체 코어 컴포넌트에 위임한다.
    창 전체 오버레이 레이어로 쓰일 때 geometry로 꽉 채운다.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self._particle = ParticleVisualizer(self)
        self._orb_anchor: QWidget | None = None
        self._anchor_filter: _OrbAnchorEventFilter | None = None
        self._watch_filters: list[_GeometryWatchFilter] = []
        self._last_center: tuple[float, float] | None = None
        self._pending_sync_reason = ""
        self._stabilize_attempts = 0
        self._prev_snapshot: _GeomSnapshot | None = None

        self._anchor_sync_timer = QTimer(self)
        self._anchor_sync_timer.setSingleShot(True)
        self._anchor_sync_timer.timeout.connect(self._begin_stabilized_sync)

        self._stabilize_timer = QTimer(self)
        self._stabilize_timer.setSingleShot(True)
        self._stabilize_timer.timeout.connect(self._continue_stabilized_sync)

    def set_orb_anchor(self, widget: QWidget | None) -> None:
        """구체 표시 여부·동기화 트리거용 앵커 (위치는 창 콘텐츠 중앙 고정)."""
        if self._orb_anchor is not None and self._anchor_filter is not None:
            self._orb_anchor.removeEventFilter(self._anchor_filter)
        self._orb_anchor = widget
        if widget is not None:
            self._anchor_filter = _OrbAnchorEventFilter(self)
            widget.installEventFilter(self._anchor_filter)
        else:
            self._anchor_filter = None
        self.request_sync_orb_anchor("set_orb_anchor")

    def register_geometry_watch(self, *widgets: QWidget) -> None:
        """anchor 외 레이아웃 변화를 감지할 위젯에 이벤트 필터를 설치한다."""
        for widget in widgets:
            filt = _GeometryWatchFilter(self)
            widget.installEventFilter(filt)
            self._watch_filters.append(filt)

    def request_sync_orb_anchor(self, reason: str = "") -> None:
        """레이아웃 완료 후 anchor 좌표 재계산 — 단일 타이머로 요청 병합."""
        if reason:
            self._pending_sync_reason = reason
        self._anchor_sync_timer.start(0)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._particle.setGeometry(self.rect())
        self.request_sync_orb_anchor("visualizer_resize")

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.request_sync_orb_anchor("visualizer_show")

    def live_anchor_center_local(self) -> tuple[float, float] | None:
        """디버그·테스트용 — 창(visualizer) 콘텐츠 기준 구체 목표 중심."""
        if self._orb_anchor is None:
            return None
        return self._window_content_center_local()

    def orb_center_offset(self) -> tuple[float, float] | None:
        """디버그·테스트용 — 목표 중심과 particle 실제 렌더링 중심 차이."""
        target = self.live_anchor_center_local()
        if target is None:
            return None
        if self._particle.custom_center() is None:
            return None
        eff = self._particle.effective_center()
        return (eff[0] - target[0], eff[1] - target[1])

    def _window_content_center_local(self) -> tuple[float, float]:
        """Visualizer(창 콘텐츠 영역) 기준 구체 목표 중심 — 화면 이동과 무관."""
        vr = self.rect()
        w, h = max(vr.width(), 1), max(vr.height(), 1)
        return (w * 0.5, h * _ORB_CENTER_Y_RATIO)

    def _map_anchor_center_local(self, anchor: QWidget) -> tuple[float, float] | None:
        """레거시·디버그용 — orb_spacer 중심 (배치에는 사용하지 않음)."""
        if not self._same_top_level_window(anchor):
            return None
        local_pt = anchor.mapTo(self, anchor.rect().center())
        return (float(local_pt.x()), float(local_pt.y()))

    @staticmethod
    def _same_top_level_window(a: QWidget, b: QWidget | None = None) -> bool:
        target = b or a
        return a.window() is target.window()

    def _begin_stabilized_sync(self) -> None:
        self._stabilize_attempts = 0
        self._prev_snapshot = None
        self._continue_stabilized_sync()

    def _continue_stabilized_sync(self) -> None:
        anchor = self._orb_anchor
        if anchor is None:
            if self._last_center is not None:
                self._particle.set_custom_center(self._last_center[0], self._last_center[1])
            else:
                self._particle.clear_custom_center()
            self._pending_sync_reason = ""
            return
        if not anchor.isVisible():
            self._hold_last_center("anchor_hidden")
            return

        snap = self._capture_snapshot()
        if snap is None:
            self._hold_last_center("snapshot_unavailable")
            return

        if self._prev_snapshot is not None and self._snapshots_match(self._prev_snapshot, snap):
            self._apply_center_candidate(snap, accepted=True)
            return

        self._prev_snapshot = snap
        self._stabilize_attempts += 1
        if self._stabilize_attempts >= _MAX_STABILIZE_ATTEMPTS:
            self._apply_center_candidate(snap, accepted=self._is_valid_center(snap.local_center))
            return
        self._stabilize_timer.start(0)

    def _capture_snapshot(self) -> _GeomSnapshot | None:
        anchor = self._orb_anchor
        if anchor is None:
            return None

        local = self._window_content_center_local()

        window = self.window()
        overlay = self._find_ui_overlay()
        return _GeomSnapshot(
            visualizer_rect=QRect(self.rect()),
            anchor_geom=QRect(anchor.geometry()),
            local_center=QPointF(local[0], local[1]),
            window_state=window.windowState() if window is not None else Qt.WindowState.WindowNoState,
            device_pixel_ratio=float(self.devicePixelRatioF()),
            overlay_geom=QRect(overlay.geometry()) if overlay is not None else None,
        )

    def _find_ui_overlay(self) -> QWidget | None:
        parent = self.parentWidget()
        if parent is None:
            return None
        for child in parent.children():
            if isinstance(child, QWidget) and child.objectName() == "UiOverlay":
                return child
        return None

    @staticmethod
    def _snapshots_match(a: _GeomSnapshot, b: _GeomSnapshot) -> bool:
        tol = _SNAPSHOT_TOLERANCE_PX

        def close_rect(r1: QRect, r2: QRect) -> bool:
            return (
                abs(r1.width() - r2.width()) <= tol
                and abs(r1.height() - r2.height()) <= tol
                and abs(r1.x() - r2.x()) <= tol
                and abs(r1.y() - r2.y()) <= tol
            )

        if not close_rect(a.visualizer_rect, b.visualizer_rect):
            return False
        if abs(a.local_center.x() - b.local_center.x()) > tol:
            return False
        if abs(a.local_center.y() - b.local_center.y()) > tol:
            return False
        if a.window_state != b.window_state:
            return False
        if abs(a.device_pixel_ratio - b.device_pixel_ratio) > 0.01:
            return False
        if a.overlay_geom is not None and b.overlay_geom is not None:
            if not close_rect(a.overlay_geom, b.overlay_geom):
                return False
        return True

    def _is_valid_center(self, center: QPointF) -> bool:
        vr = self.rect()
        if vr.width() <= 0 or vr.height() <= 0:
            return False

        cx, cy = center.x(), center.y()
        if cx < 0 or cy < 0:
            return False
        if cx > vr.width() or cy > vr.height():
            return False
        return True

    def _apply_center_candidate(self, snap: _GeomSnapshot, *, accepted: bool) -> None:
        reason = self._pending_sync_reason or "sync"
        self._pending_sync_reason = ""
        cx, cy = snap.local_center.x(), snap.local_center.y()
        prev = self._last_center

        if accepted and self._is_valid_center(snap.local_center):
            self._last_center = (cx, cy)
            self._particle.set_custom_center(cx, cy)
            reject_reason = None
        else:
            reject_reason = "invalid_candidate" if not accepted else "validation_failed"
            self._hold_last_center(reject_reason or "rejected")

        if _DEBUG_ORB:
            self._log_geometry_debug(
                reason=reason,
                snap=snap,
                prev=prev,
                candidate=(cx, cy),
                accepted=accepted and reject_reason is None,
                reject_reason=reject_reason,
            )

    def _hold_last_center(self, reason: str) -> None:
        anchor = self._orb_anchor
        if anchor is not None and anchor.isVisible():
            if _DEBUG_ORB:
                snap = self._capture_snapshot()
                if snap is not None:
                    self._log_geometry_debug(
                        reason=reason,
                        snap=snap,
                        prev=self._last_center,
                        candidate=(snap.local_center.x(), snap.local_center.y()),
                        accepted=False,
                        reject_reason=reason,
                    )
        center = self._window_content_center_local()
        self._last_center = center
        self._particle.set_custom_center(center[0], center[1])
        self._pending_sync_reason = ""

    def _sync_orb_anchor(self) -> None:
        """레거시 호환 — 안정화 동기화로 위임."""
        self.request_sync_orb_anchor("legacy_sync")

    def _log_geometry_debug(
        self,
        *,
        reason: str,
        snap: _GeomSnapshot,
        prev: tuple[float, float] | None,
        candidate: tuple[float, float],
        accepted: bool,
        reject_reason: str | None,
    ) -> None:
        anchor = self._orb_anchor
        window = self.window()
        main_geom = window.geometry() if window is not None else QRect()
        bg = self.parentWidget()
        bg_geom = bg.geometry() if bg is not None else QRect()
        overlay_geom = snap.overlay_geom or QRect()
        assistant = window.findChild(QWidget, "AssistantWorkspacePage") if window else None
        assistant_geom = assistant.geometry() if assistant is not None else QRect()
        splitter_sizes: list[int] = []
        if assistant is not None:
            splitter = getattr(assistant, "splitter", None)
            if splitter is not None and hasattr(splitter, "sizes"):
                splitter_sizes = list(splitter.sizes())
        orb_geom = anchor.geometry() if anchor is not None else QRect()
        spacer_local = ""
        if anchor is not None:
            mapped = self._map_anchor_center_local(anchor)
            if mapped is not None:
                spacer_local = f"spacer_local=({mapped[0]:.1f},{mapped[1]:.1f}) "
        global_center = ""
        if anchor is not None:
            g = anchor.mapToGlobal(anchor.rect().center())
            global_center = f"({g.x()},{g.y()})"

        target = self._particle.custom_center()
        effective = self._particle.effective_center()
        render_dx = effective[0] - candidate[0]
        render_dy = effective[1] - candidate[1]
        target_str = (
            f"({target[0]:.1f},{target[1]:.1f})" if target is not None else "None"
        )

        print(
            f"[IRIS_DEBUG_ORB] reason={reason!r} "
            f"window_state={int(snap.window_state)} "
            f"main={main_geom.width()}x{main_geom.height()} "
            f"bg={bg_geom.width()}x{bg_geom.height()} "
            f"overlay={overlay_geom.width()}x{overlay_geom.height()} "
            f"viz={snap.visualizer_rect.width()}x{snap.visualizer_rect.height()} "
            f"assistant={assistant_geom.width()}x{assistant_geom.height()} "
            f"splitter={splitter_sizes} "
            f"orb_spacer={orb_geom.width()}x{orb_geom.height()}@({orb_geom.x()},{orb_geom.y()}) "
            f"{spacer_local}"
            f"window_center=({candidate[0]:.1f},{candidate[1]:.1f}) "
            f"target={target_str} "
            f"effective=({effective[0]:.1f},{effective[1]:.1f}) "
            f"render_offset=({render_dx:.1f},{render_dy:.1f}) "
            f"global_diag={global_center} "
            f"prev={prev} "
            f"accepted={accepted} "
            f"reject={reject_reason!r} "
            f"dpr={snap.device_pixel_ratio:.3f}"
        )

    def set_state(self, state: AppState) -> None:
        self._particle.set_state(state.name)

    def set_mic_level(self, level: float) -> None:
        self._particle.set_audio_level(level)

    def particle_core(self) -> ParticleVisualizer:
        """TTS/레벨 미터 등에서 직접 ParticleVisualizer에 접근할 때 사용."""
        return self._particle


class _OrbAnchorEventFilter(QObject):
    """앵커 위젯 이동·리사이즈 시 구체 위치 동기화."""

    def __init__(self, visualizer: Visualizer) -> None:
        super().__init__(visualizer)
        self._visualizer = visualizer

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
            QEvent.Type.Show,
            QEvent.Type.Hide,
            QEvent.Type.LayoutRequest,
            QEvent.Type.ParentChange,
        ):
            self._visualizer.request_sync_orb_anchor(f"anchor_{event.type().name}")
        return super().eventFilter(watched, event)


class _GeometryWatchFilter(QObject):
    """레이아웃 트리 상위·형제 위젯 geometry 변화 감지."""

    _WATCH_TYPES = (
        QEvent.Type.Resize,
        QEvent.Type.Move,
        QEvent.Type.Show,
        QEvent.Type.Hide,
        QEvent.Type.LayoutRequest,
        QEvent.Type.ParentChange,
        QEvent.Type.WindowStateChange,
    )

    def __init__(self, visualizer: Visualizer) -> None:
        super().__init__(visualizer)
        self._visualizer = visualizer

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() in self._WATCH_TYPES:
            name = watched.objectName() if isinstance(watched, QWidget) else ""
            self._visualizer.request_sync_orb_anchor(f"watch_{name}_{event.type().name}")
        return super().eventFilter(watched, event)
