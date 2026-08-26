"""Iris Wiki 그래프 뷰 — 회전하는 별자리 구체로 그린 LLM wiki 맵."""

from __future__ import annotations

import math
from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPen,
    QRadialGradient,
    QWheelEvent,
)
from PyQt6.QtWidgets import QWidget

from iris.knowledge.iris_wiki import WIKI_NAME, IrisWiki

_PAD = 44.0
_HIT_RADIUS = 16.0
_STAR_COUNT = 2800
_HUB_PALETTE = (QColor(251, 210, 108), QColor(125, 245, 232), QColor(170, 210, 255))


@dataclass
class _Node:
    rel: str  # 노트 rel_path ("" = root/hub)
    label: str
    kind: str  # "root" | "hub" | "note"
    nx: float
    ny: float
    depth: float = 1.0  # 1.0 = 구 표면, 작을수록 구 안쪽으로 파고든다
    back: bool = False  # True면 z를 뒤집어 구의 뒷면 쪽에 둔다
    x3: float | None = None
    y3: float | None = None
    z3: float | None = None


class WikiGraphView(QWidget):
    """3D 투영 그래프 — 노트 클릭 시 node_selected 방출."""

    node_selected = pyqtSignal(str)  # rel_path

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WikiGraphView")
        self.setMinimumSize(360, 320)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._nodes: list[_Node] = []
        self._edges: list[tuple[int, int, str, int | None]] = []
        self._hub_colors: dict[int, QColor] = {}
        self._stars: list[tuple[float, float, float, float, float, QColor]] = []
        self._clouds: list[tuple[float, float, float, float, float, QColor]] = []
        self._selected_rel = ""
        self._hover_idx = -1
        self._zoom = 1.0
        self._angle = 0.0
        self._tilt = -0.28
        self._spin_x = 0.0
        self._spin_y = 0.0025
        self._dragging = False
        self._drag_moved = False
        self._last_drag_pos = QPointF()
        self._press_idx = -1
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def build(self, wiki: IrisWiki | None) -> None:
        self._nodes = []
        self._edges = []
        self._hub_colors = {}
        hub_dirs: list[tuple[float, float, float, QColor]] = []
        hub_positions: list[tuple[float, float, float, QColor]] = []
        if wiki is None:
            self._stars = []
            self._clouds = []
            self.update()
            return
        try:
            notes = wiki.list_notes()
        except Exception:  # noqa: BLE001
            notes = []

        wiki_groups: dict[str, list] = {}
        for note in notes:
            wiki_groups.setdefault(note.folder, []).append(note)
        wiki_folders = sorted(wiki_groups)

        self._nodes.append(_Node("", WIKI_NAME, "root", 0.5, 0.5))
        root_idx = 0

        wiki_hub_groups = [
            (folder, [(note.rel_path, note.title, note.title) for note in wiki_groups[folder]])
            for folder in wiki_folders
        ]
        self._add_cluster(root_idx, wiki_hub_groups, "note", hub_dirs, hub_positions)

        self._stars = self._make_stars(hub_dirs)
        self._clouds = self._make_clouds(hub_positions)
        self.update()

    def _add_cluster(
        self,
        root_idx: int,
        hub_groups: list[tuple[str, list[tuple[str, str, str]]]],
        kind: str,
        hub_dirs: list[tuple[float, float, float, QColor]],
        hub_positions: list[tuple[float, float, float, QColor]],
    ) -> dict[str, int]:
        """폴더별로 허브를 두고 멤버를 부채꼴로 배치한다.

        members는 (rel_path, label, link_key) 튜플. link_key -> 노드 인덱스 매핑을 돌려준다
        (위키 노트 제목으로 [[위키링크]]를 잇는다).
        """
        link_to_idx: dict[str, int] = {}
        count = max(len(hub_groups), 1)
        max_members = max((len(members) for _, members in hub_groups), default=1) or 1
        for fi, (folder, members) in enumerate(hub_groups):
            m = len(members)
            # 완벽한 원형 배치를 피하려고 각도·반지름에 고정 지터를 준다.
            ang = 2 * math.pi * fi / count - math.pi / 2 + 0.5 * math.sin(fi * 2.7 + 1.0)
            # 목표 위도(z)를 먼저 고르게 분산시킨 뒤 그걸 만드는 반지름을 역산한다 — 그래야
            # 극지방에만 쏠리지 않고 적도 쪽까지 실제로 고르게 퍼진다(별 필드와 같은 원리).
            # 세제곱 보정항은 유난히 멤버가 많은 허브(예: 70개짜리 폴더)만 골라서 극 쪽으로
            # 밀어 부채꼴을 펼칠 여유 공간을 만든다 — 나머지 평범한 허브는 거의 해시값 그대로
            # 써서 원래의 고른 위도 분포를 유지한다.
            member_frac = m / max_members
            z_target = 0.08 + 0.90 * (((fi * 53) % 100) / 100) + 0.80 * member_frac**3
            hub_radius = 0.47 * math.sqrt(max(0.0, 1.0 - min(0.99, z_target) ** 2))
            hx = 0.5 + hub_radius * math.cos(ang)
            hy = 0.5 + hub_radius * math.sin(ang)
            hub_idx = len(self._nodes)
            label = folder.split("/")[-1] or folder
            hub_depth = 0.45 + 0.5 * ((fi * 61) % 100) / 100
            hub_back = ((fi * 83) % 100) < 50
            self._nodes.append(_Node("", label, "hub", hx, hy, hub_depth, hub_back))
            hub_color = _HUB_PALETTE[fi % len(_HUB_PALETTE)]
            self._hub_colors[hub_idx] = hub_color
            hub_pos = self._node_pos(self._nodes[hub_idx])
            hub_dirs.append((*hub_pos, hub_color))
            hub_positions.append((*hub_pos, hub_color))

            member_idx: list[int] = []
            for mi, (rel_path, member_label, link_key) in enumerate(members):
                shell_a = (mi * 2.399963229728653 + fi * 0.7) % (math.pi * 2)
                shell_z = 1.0 - 2.0 * ((mi + 0.5) / max(m, 1))
                shell_r = math.sqrt(max(0.0, 1.0 - shell_z * shell_z))
                # ponytail: 상한을 0.14로 낮춰 노트 수가 많은 폴더(코드/ui 등)가
                # 구체를 독점하지 않게 함; 업그레이드 시 0.18~0.22로 올릴 것
                cluster_r = min(0.14, 0.10 + 0.006 * m)
                x3 = hub_pos[0] + cluster_r * shell_r * math.cos(shell_a)
                y3 = hub_pos[1] + cluster_r * shell_r * math.sin(shell_a)
                z3 = hub_pos[2] + cluster_r * shell_z
                mag = math.sqrt(x3 * x3 + y3 * y3 + z3 * z3)
                if mag > 0.96:
                    scale = 0.96 / mag
                    x3 *= scale
                    y3 *= scale
                    z3 *= scale
                nx = 0.5 + 0.49 * x3
                ny = 0.5 + 0.49 * y3
                ni = len(self._nodes)
                self._nodes.append(_Node(rel_path, member_label, kind, nx, ny, x3=x3, y3=y3, z3=z3))
                self._edges.append((hub_idx, ni, "structure", hub_idx))
                link_to_idx[link_key] = ni
                member_idx.append(ni)

        return link_to_idx

    def select(self, rel_path: str) -> None:
        self._selected_rel = rel_path or ""
        self.update()

    # ---- 좌표 ----
    def _tick(self) -> None:
        if not self._dragging:
            self._angle = (self._angle + self._spin_y) % (math.pi * 2)
            self._tilt = max(-1.15, min(1.15, self._tilt + self._spin_x))
            self._spin_x *= 0.94
            self._spin_y = 0.0025 + (self._spin_y - 0.0025) * 0.94
        self.update()

    def _to_px(self, nx: float, ny: float) -> QPointF:
        p, _scale, _alpha, _z = self._project(*self._node_xyz(nx, ny))
        return p

    def _node_radius(self, node: _Node, *, selected: bool, hover: bool) -> float:
        base = {"root": 7.0, "hub": 8.0, "note": 1.8}[node.kind]
        if selected:
            base += 3.0
        elif hover:
            base += 2.0
        return base

    def _make_stars(
        self, hub_dirs: list[tuple[float, float, float, QColor]]
    ) -> list[tuple[float, float, float, float, float, QColor]]:
        stars: list[tuple[float, float, float, float, float, QColor]] = []
        for i in range(_STAR_COUNT):
            a = (i * 2.399963229728653) % (math.pi * 2)
            cz = 1.0 - 2.0 * ((i + 0.5) / _STAR_COUNT)
            cr = math.sqrt(max(0.0, 1.0 - cz * cz))
            # 레퍼런스처럼 겉 원이 보이도록 입자를 구 표면 쪽에 몰아둔다.
            u = ((i * 61) % 1000) / 1000
            depth = 0.74 + 0.26 * (u**0.32)
            x = cr * math.cos(a) * depth
            y = cr * math.sin(a) * depth
            z = cz * depth
            size = 0.35 + 0.85 * ((i * 37) % 100) / 100
            alpha = 45 + 145 * ((i * 53) % 100) / 100
            stars.append((x, y, z, size, alpha + 45 * abs(z), QColor(245, 248, 255)))
        return stars

    def _nearest_hub_color(
        self, x: float, y: float, z: float, hub_dirs: list[tuple[float, float, float, QColor]]
    ) -> QColor:
        mag = math.sqrt(x * x + y * y + z * z) or 1e-6
        best_color = QColor(235, 245, 255)
        best_dot = 0.94  # 색은 큰 성운 덩어리에 맡기고, 별 입자는 대부분 중립 흰색으로 남긴다.
        for hx, hy, hz, color in hub_dirs:
            dot = (x * hx + y * hy + z * hz) / mag
            if dot > best_dot:
                best_dot = dot
                best_color = color
        return best_color

    def _make_clouds(
        self, hub_positions: list[tuple[float, float, float, QColor]]
    ) -> list[tuple[float, float, float, float, float, QColor]]:
        # 허브 주변의 흩어진 네온을 큰 덩어리 성운으로 묶는다.
        clouds: list[tuple[float, float, float, float, float, QColor]] = []
        for hi, (hx, hy, hz, color) in enumerate(hub_positions):
            for j in range(2):
                a = (hi * 2 + j) * 1.913
                jx = hx + 0.04 * math.cos(a)
                jy = hy + 0.04 * math.sin(a)
                jz = hz + 0.03 * math.sin(a * 1.7)
                spread = 0.30 + 0.10 * j
                alpha = 34 - 6 * j
                clouds.append((jx, jy, jz, spread, alpha, color))
        return clouds

    def _node_xyz(self, nx: float, ny: float) -> tuple[float, float, float]:
        x = (nx - 0.5) / 0.49
        y = (ny - 0.5) / 0.49
        d2 = min(0.99, x * x + y * y)  # 0.99까지 허용해 적도 근처까지 닿을 수 있게 한다
        z = math.sqrt(max(0.0, 1.0 - d2))
        return x, y, z

    def _node_pos(self, node: _Node) -> tuple[float, float, float]:
        """구 표면 방향에 노드별 depth를 곱하고, back이면 z를 뒤집어 뒷면에도 골고루 퍼지게 한다."""
        if node.x3 is not None and node.y3 is not None and node.z3 is not None:
            return node.x3, node.y3, node.z3
        x, y, z = self._node_xyz(node.nx, node.ny)
        if node.back:
            z = -z
        return x * node.depth, y * node.depth, z * node.depth

    def _rotate(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        ca = math.cos(self._angle)
        sa = math.sin(self._angle)
        cb = math.cos(self._tilt)
        sb = math.sin(self._tilt)
        x1 = x * ca + z * sa
        z1 = -x * sa + z * ca
        y2 = y * cb - z1 * sb
        z2 = y * sb + z1 * cb
        return x1, y2, z2

    def _project(self, x: float, y: float, z: float) -> tuple[QPointF, float, int, float]:
        x, y, z = self._rotate(x, y, z)
        bounds = self._sphere_rect()
        center = bounds.center()
        radius = min(bounds.width(), bounds.height()) / 2 * self._zoom
        perspective = 1.7 / (2.45 - z)
        scale = 0.74 * perspective
        p = QPointF(center.x() + x * radius * scale, center.y() + y * radius * scale)
        alpha = int(35 + 200 * max(0.0, (z + 1.0) / 2.0))
        return p, scale, alpha, z

    # ---- 이벤트 ----
    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta == 0:
            return
        self._zoom = max(0.5, min(3.5, self._zoom * (1.0015**delta)))
        self.update()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_moved = False
            self._last_drag_pos = event.position()
            self._press_idx = self._hit_test(event.position())
            self._spin_x = 0.0
            self._spin_y = 0.0
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._dragging:
            pos = event.position()
            dx = pos.x() - self._last_drag_pos.x()
            dy = pos.y() - self._last_drag_pos.y()
            if abs(dx) + abs(dy) > 2:
                self._drag_moved = True
            self._angle = (self._angle + dx * 0.009) % (math.pi * 2)
            self._tilt = max(-1.15, min(1.15, self._tilt + dy * 0.009))
            self._spin_y = dx * 0.0009
            self._spin_x = dy * 0.0009
            self._last_drag_pos = pos
            self.update()
            super().mouseMoveEvent(event)
            return
        idx = self._hit_test(event.position())
        if idx != self._hover_idx:
            self._hover_idx = idx
            hovering = idx >= 0 and self._nodes[idx].kind == "note"
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if hovering else Qt.CursorShape.OpenHandCursor
            )
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            idx = self._hit_test(event.position())
            if not self._drag_moved and idx == self._press_idx and idx >= 0:
                node = self._nodes[idx]
                if node.kind == "note" and node.rel:
                    self._selected_rel = node.rel
                    self.node_selected.emit(node.rel)
            self._press_idx = -1
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.update()
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover_idx != -1:
            self._hover_idx = -1
            self.unsetCursor()
            self.update()
        super().leaveEvent(event)

    def _hit_test(self, pos: QPointF) -> int:
        best = -1
        best_d = _HIT_RADIUS
        for idx, node in enumerate(self._nodes):
            if node.kind != "note":  # 허브/루트는 내용이 없는 안내점이라 클릭 대상에서 뺀다
                continue
            p, scale, _alpha, z = self._project(*self._node_pos(node))
            if z < -0.28:
                continue
            d = math.hypot(p.x() - pos.x(), p.y() - pos.y())
            if d <= best_d + 10 * scale:
                best_d = d
                best = idx
        return best

    # ---- 렌더 ----
    def paintEvent(self, event) -> None:  # noqa: ARG002, N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if not self._nodes:
            painter.setPen(QColor("#64748b"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Iris Wiki 로딩 중…")
            return

        bounds = self._sphere_rect()
        center = bounds.center()
        radius = min(bounds.width(), bounds.height()) / 2
        glow = QRadialGradient(center, radius)
        glow.setColorAt(0.0, QColor(8, 12, 22, 60))
        glow.setColorAt(0.6, QColor(4, 6, 14, 40))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(bounds)

        # 중심 성운 — 아주 옅은 청록/흰색으로 깊이감만 살짝 더한다.
        core = QRadialGradient(center, radius * 0.55)
        core.setColorAt(0.0, QColor(180, 235, 255, 22))
        core.setColorAt(0.6, QColor(120, 200, 255, 10))
        core.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(core)
        painter.drawEllipse(center, radius * 0.55, radius * 0.55)

        self._draw_sphere_nebula(painter)
        self._draw_nebula(painter)

        painter.setPen(Qt.PenStyle.NoPen)
        star_draw = []
        for x, y, z, size, alpha, color in self._stars:
            p, scale, depth_alpha, rz = self._project(x, y, z)
            star_draw.append(
                (rz, p, size * max(0.5, scale), min(238, int(alpha * depth_alpha / 205)), color)
            )
        for rz, p, size, alpha, color in sorted(star_draw, key=lambda item: item[0]):
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), alpha))
            painter.drawEllipse(p, size, size)

        # 선
        for a, b, kind, hub_idx in self._edges:
            pa, _sa, aa, za = self._project(*self._node_pos(self._nodes[a]))
            pb, _sb, ab, zb = self._project(*self._node_pos(self._nodes[b]))
            alpha = max(4, min(24, int((aa + ab) / 16)))
            if hub_idx is not None:
                c = self._hub_colors.get(hub_idx, QColor(226, 232, 240))
                pen = QPen(QColor(c.red(), c.green(), c.blue(), max(8, alpha)), 0.7)
            else:
                continue
            painter.setPen(pen)
            painter.drawLine(pa, pb)

        # 점 + 라벨
        painter.setPen(Qt.PenStyle.NoPen)
        ordered = []
        for idx, node in enumerate(self._nodes):
            p, scale, alpha, z = self._project(*self._node_pos(node))
            ordered.append((z, idx, node, p, scale, alpha))
        for z, idx, node, p, scale, alpha in sorted(ordered, key=lambda item: item[0]):
            selected = node.rel == self._selected_rel
            hover = idx == self._hover_idx
            r = self._node_radius(node, selected=selected, hover=hover) * max(0.58, scale)

            if node.kind == "root":
                fill = QColor(191, 247, 255)
                fill.setAlpha(min(190, alpha))
                self._draw_flare(painter, p, fill, max(11.0, r * 3.2), alpha)
                self._draw_particle_core(painter, p, fill, r * 0.85, alpha)
                continue
            if node.kind == "hub":
                fill = QColor(self._hub_colors.get(idx, _HUB_PALETTE[0]))
                fill.setAlpha(min(245, alpha + 40))
                self._draw_flare(painter, p, fill, max(18.0, r * 4.0), alpha)
                self._draw_particle_core(painter, p, fill, r, alpha)
                continue

            fill = QColor(245, 248, 255) if not selected else QColor(165, 243, 252)
            fill.setAlpha(min(245, alpha + (60 if hover or selected else 0)))
            if not selected and not hover:
                r *= 0.62
                self._draw_flare(painter, p, fill, max(2.8, r * 1.8), alpha)
                self._draw_particle_core(painter, p, fill, r, alpha)
                continue
            if selected or hover:
                self._draw_flare(painter, p, fill, max(9.0, r * 2.6), alpha)
                self._draw_particle_core(painter, p, fill, r, alpha)
                self._draw_label(painter, p, node.label, r)

    def _sphere_rect(self) -> QRectF:
        size = max(1.0, min(self.width(), self.height()) - 2 * _PAD)
        return QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)

    def _draw_sphere_nebula(self, painter: QPainter) -> None:
        bounds = self._sphere_rect()
        radius = min(bounds.width(), bounds.height()) / 2

        def cloud(x: float, y: float, z: float, spread: float, color: QColor, alpha: int) -> None:
            p, scale, depth_alpha, rz = self._project(x, y, z)
            if rz < -0.55:
                return
            a = int(alpha * depth_alpha / 220)
            rr = radius * spread * max(0.6, scale)
            grad = QRadialGradient(p, rr)
            grad.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), a))
            grad.setColorAt(0.50, QColor(color.red(), color.green(), color.blue(), a // 3))
            grad.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(grad)
            painter.drawEllipse(p, rr, rr * 0.45)

        cloud(-0.48, -0.12, 0.68, 0.46, QColor(112, 170, 220), 54)
        cloud(-0.12, 0.02, 0.82, 0.32, QColor(190, 225, 245), 42)
        cloud(0.25, 0.13, 0.76, 0.30, QColor(230, 120, 165), 54)
        cloud(0.58, 0.20, 0.58, 0.24, QColor(255, 94, 150), 48)
        cloud(0.66, -0.26, 0.46, 0.18, QColor(245, 100, 170), 38)
        cloud(-0.12, -0.03, 0.86, 0.16, QColor(5, 8, 20), 58)
        cloud(0.45, -0.05, 0.68, 0.15, QColor(8, 8, 22), 52)

    def _draw_nebula(self, painter: QPainter) -> None:
        bounds = self._sphere_rect()
        radius = min(bounds.width(), bounds.height()) / 2
        for x, y, z, spread, alpha, color in sorted(self._clouds, key=lambda c: c[2]):
            p, scale, depth_alpha, rz = self._project(x, y, z)
            if rz < -0.72:
                continue
            a = min(42, int(alpha * depth_alpha / 190))
            rr = radius * spread * max(0.65, scale)
            nebula = QRadialGradient(p, rr)
            nebula.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), a))
            nebula.setColorAt(0.55, QColor(color.red(), color.green(), color.blue(), a // 3))
            nebula.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(nebula)
            painter.drawEllipse(p, rr, rr * 0.82)

    def _draw_flare(
        self, painter: QPainter, p: QPointF, color: QColor, radius: float, alpha: int
    ) -> None:
        # 안개처럼 은은하게 번지는 바깥 레이어 — 코어 발광 효과는 그대로 두고 주변에만 haze를 더한다.
        fog_radius = radius * 2.3
        fog = QRadialGradient(p, fog_radius)
        fog.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), min(38, alpha // 4)))
        fog.setColorAt(0.5, QColor(color.red(), color.green(), color.blue(), min(16, alpha // 8)))
        fog.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fog)
        painter.drawEllipse(p, fog_radius, fog_radius)

        halo = QRadialGradient(p, radius)
        halo.setColorAt(0.0, QColor(255, 255, 255, min(235, alpha + 60)))
        halo.setColorAt(0.18, QColor(color.red(), color.green(), color.blue(), min(220, alpha + 20)))
        halo.setColorAt(0.5, QColor(color.red(), color.green(), color.blue(), min(60, alpha // 3)))
        halo.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(p, radius, radius)

    def _draw_particle_core(
        self, painter: QPainter, p: QPointF, color: QColor, radius: float, alpha: int
    ) -> None:
        """단색 원판 대신 입자처럼 중심이 밝고 가장자리로 갈수록 번지는 코어를 그린다."""
        core = QRadialGradient(p, max(1.0, radius))
        a = min(255, alpha + 70)
        core.setColorAt(0.0, QColor(255, 255, 255, a))
        core.setColorAt(0.45, QColor(color.red(), color.green(), color.blue(), a))
        core.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(core)
        painter.drawEllipse(p, radius, radius)

    def _draw_label(
        self, painter: QPainter, p: QPointF, label: str, radius: float, *, text_alpha: int = 220
    ) -> None:
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)
        fm = painter.fontMetrics()
        text = fm.elidedText(label, Qt.TextElideMode.ElideRight, 160)
        w = fm.horizontalAdvance(text) + 16
        h = fm.height() + 8
        x = min(max(8.0, p.x() + radius + 8), max(8.0, self.width() - w - 8))
        y = min(max(8.0, p.y() - h / 2), max(8.0, self.height() - h - 8))
        painter.setPen(QColor(240, 249, 255, text_alpha))
        painter.drawText(QRectF(x + 8, y + 4, w - 16, h - 8), Qt.AlignmentFlag.AlignVCenter, text)
