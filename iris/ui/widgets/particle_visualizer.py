"""Animated Iris core visualizer — 사이버스페이스 입자 네트워크 orb."""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PyQt6.QtWidgets import QWidget

_BOOT_RNG = random.Random(7)

# 상태별 시각 프로필 — 청색·시안 네온 계열
# spin: 외곽 링 회전 배율 (동작 상태는 기존 fast의 30%)
_STATE_PROFILES: dict[str, dict[str, float | tuple[int, int, int]]] = {
    "IDLE": {
        "pulse": 0.022,
        "speed": 0.65,
        "spin": 2.8,
        "accent": (59, 130, 246),
    },
    "LISTENING": {
        "pulse": 0.065,
        "speed": 1.25,
        "spin": 21.6,
        "accent": (34, 211, 238),
    },
    "PROCESSING": {
        "pulse": 0.048,
        "speed": 2.0,
        "spin": 33.0,
        "accent": (96, 165, 250),
    },
    "EXECUTING": {
        "pulse": 0.080,
        "speed": 2.5,
        "spin": 42.0,
        "accent": (56, 189, 248),
    },
    "RESPONDING": {
        "pulse": 0.070,
        "speed": 1.55,
        "spin": 25.5,
        "accent": (34, 211, 238),
    },
    "MONITORING": {
        "pulse": 0.035,
        "speed": 0.95,
        "spin": 2.4,
        "accent": (129, 140, 248),
    },
    "ALERTING": {
        "pulse": 0.100,
        "speed": 2.8,
        "spin": 45.0,
        "accent": (251, 191, 36),
    },
    "ERROR": {
        "pulse": 0.075,
        "speed": 2.1,
        "spin": 36.0,
        "accent": (248, 113, 113),
    },
}

_PARTICLE_COUNT = 52
_CONNECT_DIST = 0.38
# 레이아웃 여유 — 이전 glow 기준과 동일한 크기 산정 (시각 glow는 미사용)
_VISUAL_HALO_FACTOR = 2.05
_EDGE_PAD = 10.0
_DEFAULT_CY_RATIO = 0.36
_COMPACT_HEIGHT = 320
_COMPACT_CY_RATIO = 0.52
_ORB_RAW_R_RATIO = 0.18
# custom_center 모드(IDE companion 등) 기준 반경 — 메인 화면 구체(기본 창 크기 기준
# 약 140px)와 비슷하게 맞춘 고정값. 창 폭과 무관하게 size_scale로만 조절되므로
# IDE를 풀스크린으로 키워도 컬럼 폭에 비례해 커지지 않는다.
_CUSTOM_CENTER_BASE_R = 60.0


def orb_size_scale_for_square_fill(side: int) -> float:
  """정사각 슬롯에 맞추는 size_scale (이전과 동일 산식)."""
  side = max(1, int(side))
  return (side / 2 / _VISUAL_HALO_FACTOR) / (side * _ORB_RAW_R_RATIO)


def _asset_path(relative_path: str) -> Path:
    return Path(__file__).resolve().parents[3] / "assets" / relative_path


def _fibonacci_sphere(n: int, seed: int = 42) -> list[tuple[float, float, float]]:
    """구 표면 균등 분포 좌표."""
    rng = random.Random(seed)
    pts: list[tuple[float, float, float]] = []
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(n):
        y = 1.0 - (i / float(max(n - 1, 1))) * 2.0
        r = math.sqrt(max(0.0, 1.0 - y * y))
        theta = golden * i
        x = math.cos(theta) * r
        z = math.sin(theta) * r
        jitter = 0.04 * rng.random()
        pts.append((x + jitter, y + jitter, z + jitter))
    return pts


class ParticleVisualizer(QWidget):
    """중앙 사이버스페이스 orb — 입자 네트워크 + 상태 반응."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._state_name = "IDLE"
        self._t = 0.0
        self._audio_level = 0.0
        self._smooth_audio = 0.0
        self._activity_level = 1.0
        self._state_burst = 0.0
        self._cx = 0.0
        self._cy = 0.0
        self._core_r = 60.0
        self._custom_center: tuple[float, float] | None = None
        self._companion_mode = False
        self._size_scale = 1.0
        self._sphere_pts = _fibonacci_sphere(_PARTICLE_COUNT)
        self._core_image = QPixmap(str(_asset_path("visuals/iris_core.png")))
        # 기동 인트로 — 0이면 미표시, 1이면 정상 / glitch는 치지직 강도
        self._boot_reveal = 1.0
        self._boot_glitch = 0.0

        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._recompute_geometry()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._recompute_geometry()
        self.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self.stop()

    def set_state(self, state: str) -> None:
        name = str(state).strip().upper()
        if name not in _STATE_PROFILES:
            name = "IDLE"
        if name != self._state_name:
            self._state_name = name
            self._state_burst = 1.0
        self.update()

    def set_audio_level(self, level: float) -> None:
        self._audio_level = max(0.0, min(1.0, float(level)))

    def set_activity_level(self, level: float) -> None:
        self._activity_level = max(0.0, min(2.0, float(level)))

    def set_custom_center(self, cx: float, cy: float) -> None:
        """레이아웃 앵커 등으로 구체 중심을 고정한다."""
        self._custom_center = (float(cx), float(cy))
        self._recompute_geometry()
        self.update()

    def clear_custom_center(self) -> None:
        self._custom_center = None
        self._recompute_geometry()

    def custom_center(self) -> tuple[float, float] | None:
        """현재 custom center (테스트·디버그)."""
        return self._custom_center

    def effective_center(self) -> tuple[float, float]:
        """paintEvent가 실제 사용하는 현재 렌더링 중심."""
        return (self._cx, self._cy)

    def set_size_scale(self, scale: float) -> None:
        """구체 반경 배율 — IDE 패널 등 컴팩트 영역 확대용."""
        self._size_scale = max(0.25, float(scale))
        self._recompute_geometry()

    def set_companion_mode(self, companion: bool) -> None:
        """IDE Companion 여부 — custom_center는 항상(앵커 동기화로) 채워지므로
        companion 여부로 크기 계산 방식을 나눈다(고정 반경 vs 창 비례)."""
        self._companion_mode = bool(companion)
        self._recompute_geometry()
        self.update()

    def set_boot_reveal(self, value: float) -> None:
        """기동 등장 진행(0=숨김, 1=완전 표시)."""
        self._boot_reveal = max(0.0, min(1.0, float(value)))
        self.update()

    def set_boot_glitch(self, value: float) -> None:
        """디지털 화면 치지직 강도(0=없음, 1=최대)."""
        self._boot_glitch = max(0.0, min(1.0, float(value)))
        self.update()

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _fit_core_radius(self, width: int, height: int) -> float:
        """레이아웃 여유 박스(이전 glow 기준)가 잘리지 않도록 core_r 상한."""
        limit = min(width, height)
        return max(8.0, (limit - 2 * _EDGE_PAD) / (2 * _VISUAL_HALO_FACTOR))

    def _recompute_geometry(self) -> None:
        width, height = max(self.width(), 1), max(self.height(), 1)
        if self._custom_center is None:
            raw_r = min(width, height) * _ORB_RAW_R_RATIO * self._size_scale
            self._cx = width * 0.5
            fit_r = self._fit_core_radius(width, height)
            self._core_r = min(raw_r, fit_r)
            halo = self._core_r * _VISUAL_HALO_FACTOR
            cy_ratio = (
                _COMPACT_CY_RATIO if height <= _COMPACT_HEIGHT else _DEFAULT_CY_RATIO
            )
            preferred_cy = height * cy_ratio
            min_cy = halo + _EDGE_PAD
            max_cy = height - halo - _EDGE_PAD
            if min_cy <= max_cy:
                self._cy = max(min_cy, min(preferred_cy, max_cy))
            else:
                # ponytail: 극소 영역은 중앙 + fit_r로만 맞춤
                self._core_r = fit_r
                self._cy = height * 0.5
        else:
            # custom_center는 앵커 동기화가 한 번이라도 돌면 항상 채워진다 — 메인
            # 화면도 예외가 아니다. companion 여부로만 크기 계산을 나눠야 한다.
            self._cx, self._cy = self._custom_center
            if self._companion_mode:
                # 창 폭과 무관한 고정 기준 반경 — width에 비례시키면 IDE를
                # 풀스크린으로 키울 때 컬럼 폭도 같이 커져서 구체가 거대해졌었다.
                self._core_r = _CUSTOM_CENTER_BASE_R * self._size_scale
            else:
                # 메인 화면 — 이전과 동일하게 창 크기에 비례.
                self._core_r = min(width, height) * _ORB_RAW_R_RATIO * self._size_scale

    def _profile(self) -> dict[str, float | tuple[int, int, int]]:
        return _STATE_PROFILES.get(self._state_name, _STATE_PROFILES["IDLE"])

    def _tick(self) -> None:
        speed = float(self._profile()["speed"]) * self._activity_level
        self._t += 0.026 * max(0.35, speed)
        self._smooth_audio += (self._audio_level - self._smooth_audio) * 0.14
        self._audio_level *= 0.88
        self._state_burst *= 0.90
        if self._state_burst < 0.01:
            self._state_burst = 0.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ARG002, N802
        if self.width() < 4 or self.height() < 4:
            return
        if self._boot_reveal <= 0.001:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        cx, cy = self._cx, self._cy
        profile = self._profile()
        accent = profile["accent"]
        assert isinstance(accent, tuple)
        synthetic_voice = self._synthetic_voice_level()
        energy = min(1.0, max(self._smooth_audio, synthetic_voice) + self._state_burst * 0.32)

        # 치지직 중엔 가로 찢김·스캔라인용으로 안티앨리어싱 약화
        if self._boot_glitch > 0.05:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        painter.save()
        painter.setOpacity(0.15 + 0.85 * self._boot_reveal)
        if self._boot_glitch > 0.08:
            tear = int((_BOOT_RNG.random() - 0.5) * 14.0 * self._boot_glitch)
            painter.translate(tear, int((_BOOT_RNG.random() - 0.5) * 4.0 * self._boot_glitch))

        self._draw_core_image(painter, cx, cy, energy)
        self._draw_front_sheen(painter, cx, cy, accent, energy)
        painter.restore()

        if self._boot_glitch > 0.02:
            self._draw_boot_static(painter, cx, cy, accent)

        painter.end()

    def _draw_boot_static(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        accent: tuple[int, int, int],
    ) -> None:
        """디지털 화면이 치지직 거리며 뜨는 느낌."""
        g = self._boot_glitch
        side = self._core_r * 2.4
        rect = QRectF(cx - side / 2, cy - side / 2, side, side)
        clip = QPainterPath()
        clip.addEllipse(rect)
        painter.save()
        painter.setClipPath(clip)
        painter.setOpacity(min(1.0, 0.35 + g * 0.75))

        # 가로 스캔라인
        y = rect.top()
        while y < rect.bottom():
            h = 1.0 + _BOOT_RNG.random() * 2.5 * g
            alpha = int(30 + 90 * g * _BOOT_RNG.random())
            painter.fillRect(
                QRectF(rect.left(), y, rect.width(), h),
                QColor(accent[0], accent[1], accent[2], alpha),
            )
            y += 2.0 + _BOOT_RNG.random() * 5.0

        # 노이즈 블록
        for _ in range(int(6 + 18 * g)):
            bw = 4 + _BOOT_RNG.random() * side * 0.22 * g
            bh = 2 + _BOOT_RNG.random() * 8 * g
            bx = rect.left() + _BOOT_RNG.random() * (rect.width() - bw)
            by = rect.top() + _BOOT_RNG.random() * (rect.height() - bh)
            bright = _BOOT_RNG.random() > 0.55
            color = (
                QColor(226, 242, 255, int(80 + 140 * g))
                if bright
                else QColor(accent[0], accent[1], accent[2], int(50 + 100 * g))
            )
            painter.fillRect(QRectF(bx, by, bw, bh), color)

        # RGB 채널 찢김
        if g > 0.25:
            shift = 3.0 + 8.0 * g
            painter.setOpacity(0.22 * g)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            painter.fillRect(
                QRectF(rect.left() + shift, rect.top(), rect.width(), rect.height() * 0.18),
                QColor(255, 60, 80, int(40 + 80 * g)),
            )
            painter.fillRect(
                QRectF(rect.left() - shift, cy, rect.width(), rect.height() * 0.14),
                QColor(40, 220, 255, int(40 + 80 * g)),
            )

        painter.restore()

    def _project_sphere(
        self,
        cx: float,
        cy: float,
        radius: float,
        energy: float,
    ) -> list[tuple[float, float, float, float]]:
        """3D 구 좌표 → 2D (x, y, depth, size)."""
        rot_y = self._t * 0.55
        rot_x = self._t * 0.28
        cos_y, sin_y = math.cos(rot_y), math.sin(rot_y)
        cos_x, sin_x = math.cos(rot_x), math.sin(rot_x)
        out: list[tuple[float, float, float, float]] = []
        scale = radius * (1.0 + float(self._profile()["pulse"]) * math.sin(self._t * 1.6))
        for px, py, pz in self._sphere_pts:
            x1 = px * cos_y + pz * sin_y
            z1 = -px * sin_y + pz * cos_y
            y2 = py * cos_x - z1 * sin_x
            z2 = py * sin_x + z1 * cos_x
            depth = (z2 + 1.0) * 0.5
            sx = cx + x1 * scale
            sy = cy + y2 * scale * 0.92
            size = 1.2 + depth * 1.8 + energy * 0.4
            out.append((sx, sy, depth, size))
        return out

    def _draw_particle_network(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        accent: tuple[int, int, int],
        energy: float,
    ) -> list[tuple[float, float, float, float]]:
        projected = self._project_sphere(cx, cy, self._core_r * 1.05, energy)
        n = len(projected)
        connect_sq = (_CONNECT_DIST * self._core_r) ** 2

        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

        for i in range(n):
            x1, y1, d1, _ = projected[i]
            for j in range(i + 1, n):
                x2, y2, d2, _ = projected[j]
                dx, dy = x2 - x1, y2 - y1
                if dx * dx + dy * dy > connect_sq:
                    continue
                avg_d = (d1 + d2) * 0.5
                alpha = int((12 + 28 * energy) * avg_d)
                pen = QPen(QColor(accent[0], accent[1], accent[2], alpha))
                pen.setWidthF(0.6)
                painter.setPen(pen)
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        for x, y, depth, size in projected:
            alpha = int(40 + 180 * depth + 60 * energy)
            r = size * (0.9 + energy * 0.25)
            grad = QRadialGradient(x, y, r * 2)
            grad.setColorAt(0.0, QColor(255, 255, 255, min(255, alpha + 40)))
            grad.setColorAt(0.35, QColor(accent[0], accent[1], accent[2], alpha))
            grad.setColorAt(1.0, QColor(accent[0], accent[1], accent[2], 0))
            painter.setBrush(grad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(x - r, y - r, r * 2, r * 2))

        painter.restore()
        return projected

    def _synthetic_voice_level(self) -> float:
        if self._state_name == "LISTENING":
            return 0.22 + 0.16 * (0.5 + 0.5 * math.sin(self._t * 4.0))
        if self._state_name == "PROCESSING":
            return 0.18 + 0.12 * (0.5 + 0.5 * math.sin(self._t * 7.5))
        if self._state_name == "EXECUTING":
            return 0.30 + 0.18 * (0.5 + 0.5 * math.sin(self._t * 6.2))
        if self._state_name == "RESPONDING":
            return 0.26 + 0.22 * (0.5 + 0.5 * math.sin(self._t * 8.0))
        if self._state_name == "ALERTING":
            return 0.50 + 0.25 * (0.5 + 0.5 * math.sin(self._t * 10.0))
        return 0.0

    def _draw_core_image(self, painter: QPainter, cx: float, cy: float, energy: float) -> None:
        if self._core_image.isNull():
            self._draw_procedural_core(painter, cx, cy, energy)
            return

        pulse = float(self._profile()["pulse"])
        breathe = math.sin(self._t * 1.5)
        side = self._core_r * 2.2 * (1.0 + pulse * breathe + energy * 0.03)
        rect = QRectF(cx - side / 2, cy - side / 2, side, side)

        source_side = min(self._core_image.width(), self._core_image.height()) * 0.92
        source_rect = QRectF(
            (self._core_image.width() - source_side) / 2,
            (self._core_image.height() - source_side) / 2 - source_side * 0.015,
            source_side,
            source_side,
        )

        outer_clip = QPainterPath()
        outer_clip.addEllipse(rect)
        inner_side = side * 0.52
        inner_rect = QRectF(cx - inner_side / 2, cy - inner_side / 2, inner_side, inner_side)
        inner_clip = QPainterPath()
        inner_clip.addEllipse(inner_rect)
        # 동작 중 spin 배율 ↑ → 외곽 링이 빠르게 회전
        rotation = self._t * float(self._profile()["spin"])

        painter.save()
        painter.setOpacity(0.50 + min(0.22, energy * 0.20))
        painter.setClipPath(outer_clip.subtracted(inner_clip))
        painter.translate(cx, cy)
        painter.rotate(rotation)
        painter.translate(-cx, -cy)
        painter.drawPixmap(rect, self._core_image, source_rect)
        painter.restore()

        painter.save()
        painter.setOpacity(0.95)
        painter.setClipPath(inner_clip)
        painter.drawPixmap(rect, self._core_image, source_rect)
        painter.restore()

    def _draw_procedural_core(self, painter: QPainter, cx: float, cy: float, energy: float) -> None:
        """에셋 없을 때 절차적 코어."""
        r = self._core_r * 0.42 * (1.0 + energy * 0.06)
        grad = QRadialGradient(cx, cy, r)
        profile = self._profile()
        accent = profile["accent"]
        assert isinstance(accent, tuple)
        grad.setColorAt(0.0, QColor(255, 255, 255, int(180 + 40 * energy)))
        grad.setColorAt(0.35, QColor(accent[0], accent[1], accent[2], int(140 + 60 * energy)))
        grad.setColorAt(1.0, QColor(accent[0], accent[1], accent[2], 0))
        painter.setBrush(grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

    def _draw_front_sheen(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        accent: tuple[int, int, int],
        energy: float,
    ) -> None:
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        radius = self._core_r * (0.55 + energy * 0.06)
        sheen = QRadialGradient(cx - radius * 0.2, cy - radius * 0.26, radius)
        sheen.setColorAt(0.0, QColor(255, 255, 255, int(18 + energy * 28)))
        sheen.setColorAt(0.34, QColor(accent[0], accent[1], accent[2], int(8 + energy * 18)))
        sheen.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(QRectF(cx - radius, cy - radius, radius * 2, radius * 2), sheen)
        painter.restore()
