"""Iris Wiki 그래프 뷰 — 회전하는 별자리 구체로 그린 LLM wiki 맵."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

from iris.knowledge.iris_wiki import WIKI_NAME, IrisWiki

_LINK_RE = re.compile(r"\[\[([^\]|#]+)")
_PAD = 44.0
_HIT_RADIUS = 16.0
_STAR_COUNT = 2200
_HUB_PALETTE = (QColor(251, 210, 108), QColor(125, 245, 232), QColor(170, 210, 255))


@dataclass
class _Node:
    rel: str  # 노트 rel_path ("" = root/hub)
    label: str
    kind: str  # "root" | "hub" | "note"
    nx: float
    ny: float


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
        if wiki is None:
            self._stars = []
            self._clouds = []
            self.update()
            return
        try:
            notes = wiki.list_notes()
        except Exception:  # noqa: BLE001
            notes = []

        groups: dict[str, list] = {}
        for note in notes:
            groups.setdefault(note.folder, []).append(note)
        folders = sorted(groups)

        self._nodes.append(_Node("", WIKI_NAME, "root", 0.5, 0.5))
        root_idx = 0
        title_to_idx: dict[str, int] = {}

        count = max(len(folders), 1)
        for fi, folder in enumerate(folders):
            ang = 2 * math.pi * fi / count - math.pi / 2
            hx = 0.5 + 0.30 * math.cos(ang)
            hy = 0.5 + 0.30 * math.sin(ang)
            hub_idx = len(self._nodes)
            label = folder.split("/")[-1] or folder
            self._nodes.append(_Node("", label, "hub", hx, hy))
            self._edges.append((root_idx, hub_idx, "structure", None))
            hub_color = _HUB_PALETTE[fi % len(_HUB_PALETTE)]
            self._hub_colors[hub_idx] = hub_color
            hub_dirs.append((*self._node_xyz(hx, hy), hub_color))

            members = groups[folder]
            m = len(members)
            # 가지처럼: 루트→허브 바깥 방향(ang)을 중심으로 부채꼴로 펼친다.
            spread = math.radians(min(150.0, 40.0 + 14.0 * m))
            member_idx: list[int] = []
            for mi, note in enumerate(members):
                if m <= 1:
                    a2 = ang
                else:
                    a2 = ang - spread / 2 + spread * mi / (m - 1)
                # 가지 길이를 번갈아 달리해 노드 겹침을 줄인다.
                branch = 0.14 + 0.035 * (mi % 3)
                nx = min(0.97, max(0.03, hx + branch * math.cos(a2)))
                ny = min(0.97, max(0.03, hy + branch * math.sin(a2)))
                ni = len(self._nodes)
                self._nodes.append(_Node(note.rel_path, note.title, "note", nx, ny))
                self._edges.append((hub_idx, ni, "structure", None))
                title_to_idx[note.title] = ni
                member_idx.append(ni)

            # 형제 노트끼리 아주 옅은 실선으로 이어 성단(星團) 같은 그물 질감을 준다.
            for mi, ni in enumerate(member_idx):
                for skip in (1, 2):
                    if mi + skip < len(member_idx):
                        self._edges.append((ni, member_idx[mi + skip], "ambient", hub_idx))

        # 위키링크 [[...]] → 노트 간 선
        for idx, node in enumerate(self._nodes):
            if node.kind != "note":
                continue
            try:
                text = wiki.read_note(node.rel)
            except Exception:  # noqa: BLE001
                continue
            for match in _LINK_RE.finditer(text):
                target = match.group(1).strip()
                dst = title_to_idx.get(target)
                if dst is not None and dst != idx:
                    self._edges.append((idx, dst, "link", None))

        self._stars = self._make_stars(hub_dirs)
        self._clouds = self._make_clouds(hub_dirs)
        self.update()

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
        base = {"root": 6.0, "hub": 4.2, "note": 2.2}[node.kind]
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
            # 표면 셸이 아니라 중심 쪽으로 밀도가 몰리는 폭죽처럼, 구체 안쪽까지 입자를 채운다.
            u = ((i * 61) % 1000) / 1000
            depth = 0.05 + 0.95 * (u**1.8)
            x = cr * math.cos(a) * depth
            y = cr * math.sin(a) * depth
            z = cz * depth
            size = 0.4 + 1.1 * ((i * 37) % 100) / 100
            alpha = 25 + 165 * ((i * 53) % 100) / 100
            color = self._nearest_hub_color(x, y, z, hub_dirs)
            stars.append((x, y, z, size, alpha + 35 * abs(z), color))
        return stars

    def _nearest_hub_color(
        self, x: float, y: float, z: float, hub_dirs: list[tuple[float, float, float, QColor]]
    ) -> QColor:
        mag = math.sqrt(x * x + y * y + z * z) or 1e-6
        best_color = QColor(235, 245, 255)
        best_dot = 0.82  # 클러스터 중심 가까이만 물들이고 나머지는 중립 흰색으로 남긴다.
        for hx, hy, hz, color in hub_dirs:
            dot = (x * hx + y * hy + z * hz) / mag
            if dot > best_dot:
                best_dot = dot
                best_color = color
        return best_color

    def _make_clouds(
        self, hub_dirs: list[tuple[float, float, float, QColor]]
    ) -> list[tuple[float, float, float, float, float, QColor]]:
        clouds: list[tuple[float, float, float, float, float, QColor]] = []
        for hi, (hx, hy, hz, color) in enumerate(hub_dirs):
            for j in range(3):
                a = (hi * 3 + j) * 1.913
                jx = hx + 0.10 * math.cos(a)
                jy = hy + 0.10 * math.sin(a)
                jz = hz + 0.06 * math.sin(a * 1.7)
                mag = math.sqrt(jx * jx + jy * jy + jz * jz) or 1.0
                spread = 0.16 + 0.05 * j
                alpha = 26 - 4 * j
                clouds.append((jx / mag, jy / mag, jz / mag, spread, alpha, color))
        return clouds

    def _node_xyz(self, nx: float, ny: float) -> tuple[float, float, float]:
        x = (nx - 0.5) / 0.49
        y = (ny - 0.5) / 0.49
        d2 = min(0.96, x * x + y * y)
        z = math.sqrt(max(0.0, 1.0 - d2))
        return x, y, z

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
        radius = min(bounds.width(), bounds.height()) / 2
        perspective = 1.7 / (2.45 - z)
        scale = 0.74 * perspective
        p = QPointF(center.x() + x * radius * scale, center.y() + y * radius * scale)
        alpha = int(35 + 200 * max(0.0, (z + 1.0) / 2.0))
        return p, scale, alpha, z

    # ---- 이벤트 ----
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
            p, scale, _alpha, z = self._project(*self._node_xyz(node.nx, node.ny))
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
            pa, _sa, aa, za = self._project(*self._node_xyz(self._nodes[a].nx, self._nodes[a].ny))
            pb, _sb, ab, zb = self._project(*self._node_xyz(self._nodes[b].nx, self._nodes[b].ny))
            alpha = max(4, min(24, int((aa + ab) / 16)))
            if kind == "link":
                pen = QPen(QColor(125, 211, 252, alpha), 1.0 if za + zb > 0 else 0.5)
            elif kind == "ambient":
                c = self._hub_colors.get(hub_idx, QColor(226, 232, 240))
                pen = QPen(QColor(c.red(), c.green(), c.blue(), max(3, alpha // 2)), 0.5)
            else:
                pen = QPen(QColor(226, 232, 240, max(3, alpha // 2)), 0.5)
            painter.setPen(pen)
            painter.drawLine(pa, pb)

        # 점 + 라벨
        painter.setPen(Qt.PenStyle.NoPen)
        ordered = []
        for idx, node in enumerate(self._nodes):
            p, scale, alpha, z = self._project(*self._node_xyz(node.nx, node.ny))
            ordered.append((z, idx, node, p, scale, alpha))
        for z, idx, node, p, scale, alpha in sorted(ordered, key=lambda item: item[0]):
            selected = node.kind == "note" and node.rel == self._selected_rel
            hover = idx == self._hover_idx
            r = self._node_radius(node, selected=selected, hover=hover) * max(0.58, scale)

            if node.kind == "root":
                fill = QColor(191, 247, 255)
            elif node.kind == "hub":
                fill = QColor(self._hub_colors.get(idx, _HUB_PALETTE[0]))
            else:
                fill = QColor(226, 232, 240) if not selected else QColor(165, 243, 252)

            fill.setAlpha(min(245, alpha + (60 if hover or selected else 0)))
            if node.kind in ("root", "hub") or selected or hover:
                self._draw_flare(painter, p, fill, max(9.0, r * 2.6), alpha)
                painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawEllipse(p, r, r)

            if selected or hover:
                self._draw_label(painter, p, node.label, r, prominent=selected or hover)

    def _sphere_rect(self) -> QRectF:
        size = max(1.0, min(self.width(), self.height()) - 2 * _PAD)
        return QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)

    def _draw_nebula(self, painter: QPainter) -> None:
        bounds = self._sphere_rect()
        radius = min(bounds.width(), bounds.height()) / 2
        for x, y, z, spread, alpha, color in sorted(self._clouds, key=lambda c: c[2]):
            p, scale, depth_alpha, rz = self._project(x, y, z)
            if rz < -0.72:
                continue
            a = min(70, int(alpha * depth_alpha / 150))
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
        halo = QRadialGradient(p, radius)
        halo.setColorAt(0.0, QColor(255, 255, 255, min(235, alpha + 60)))
        halo.setColorAt(0.18, QColor(color.red(), color.green(), color.blue(), min(220, alpha + 20)))
        halo.setColorAt(0.5, QColor(color.red(), color.green(), color.blue(), min(60, alpha // 3)))
        halo.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(p, radius, radius)

    def _draw_label(
        self, painter: QPainter, p: QPointF, label: str, radius: float, *, prominent: bool
    ) -> None:
        font = QFont()
        font.setPointSize(9 if prominent else 8)
        font.setBold(prominent)
        painter.setFont(font)
        fm = painter.fontMetrics()
        text = fm.elidedText(label, Qt.TextElideMode.ElideRight, 220 if prominent else 120)
        w = fm.horizontalAdvance(text) + 16
        h = fm.height() + 8
        x = min(max(8.0, p.x() + radius + 8), max(8.0, self.width() - w - 8))
        y = min(max(8.0, p.y() - h / 2), max(8.0, self.height() - h - 8))
        if prominent:
            painter.setPen(QPen(QColor(125, 211, 252, 145), 1.0))
            painter.setBrush(QColor(2, 6, 23, 215))
            painter.drawRoundedRect(QRectF(x, y, w, h), 6, 6)
        painter.setPen(QColor(240, 249, 255, 240 if prominent else 170))
        painter.drawText(QRectF(x + 8, y + 4, w - 16, h - 8), Qt.AlignmentFlag.AlignVCenter, text)
