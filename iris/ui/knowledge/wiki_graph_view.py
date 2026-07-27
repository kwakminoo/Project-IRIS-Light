"""Iris Wiki 그래프 뷰 — 점(노트)과 선(구조·위키링크)으로 그린 LLM wiki 맵."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from iris.knowledge.iris_wiki import WIKI_NAME, IrisWiki

_LINK_RE = re.compile(r"\[\[([^\]|#]+)")
_PAD = 44.0
_HIT_RADIUS = 16.0


@dataclass
class _Node:
    rel: str  # 노트 rel_path ("" = root/hub)
    label: str
    kind: str  # "root" | "hub" | "note"
    nx: float
    ny: float


class WikiGraphView(QWidget):
    """정적 레이아웃 그래프 — 노트 클릭 시 node_selected 방출."""

    node_selected = pyqtSignal(str)  # rel_path

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WikiGraphView")
        self.setMinimumSize(360, 320)
        self.setMouseTracking(True)
        self._nodes: list[_Node] = []
        self._edges: list[tuple[int, int, str]] = []
        self._selected_rel = ""
        self._hover_idx = -1

    def build(self, wiki: IrisWiki | None) -> None:
        self._nodes = []
        self._edges = []
        if wiki is None:
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
            self._edges.append((root_idx, hub_idx, "structure"))

            members = groups[folder]
            m = len(members)
            # 가지처럼: 루트→허브 바깥 방향(ang)을 중심으로 부채꼴로 펼친다.
            spread = math.radians(min(150.0, 40.0 + 14.0 * m))
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
                self._edges.append((hub_idx, ni, "structure"))
                title_to_idx[note.title] = ni

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
                    self._edges.append((idx, dst, "link"))
        self.update()

    def select(self, rel_path: str) -> None:
        self._selected_rel = rel_path or ""
        self.update()

    # ---- 좌표 ----
    def _to_px(self, nx: float, ny: float) -> QPointF:
        w = max(self.width() - 2 * _PAD, 1.0)
        h = max(self.height() - 2 * _PAD, 1.0)
        return QPointF(_PAD + nx * w, _PAD + ny * h)

    def _node_radius(self, node: _Node, *, selected: bool, hover: bool) -> float:
        base = {"root": 9.0, "hub": 6.0, "note": 4.0}[node.kind]
        if selected:
            base += 3.0
        elif hover:
            base += 1.5
        return base

    # ---- 이벤트 ----
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        idx = self._hit_test(event.position())
        if idx >= 0:
            node = self._nodes[idx]
            if node.kind == "note" and node.rel:
                self._selected_rel = node.rel
                self.update()
                self.node_selected.emit(node.rel)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        idx = self._hit_test(event.position())
        if idx != self._hover_idx:
            self._hover_idx = idx
            hovering = idx >= 0 and self._nodes[idx].kind == "note"
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if hovering else Qt.CursorShape.ArrowCursor
            )
            self.update()
        super().mouseMoveEvent(event)

    def _hit_test(self, pos: QPointF) -> int:
        best = -1
        best_d = _HIT_RADIUS
        for idx, node in enumerate(self._nodes):
            p = self._to_px(node.nx, node.ny)
            d = math.hypot(p.x() - pos.x(), p.y() - pos.y())
            if d <= best_d:
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

        # 선
        for a, b, kind in self._edges:
            pa = self._to_px(self._nodes[a].nx, self._nodes[a].ny)
            pb = self._to_px(self._nodes[b].nx, self._nodes[b].ny)
            if kind == "link":
                pen = QPen(QColor(56, 189, 248, 150), 1.6)
            else:
                pen = QPen(QColor(56, 189, 248, 45), 1.0)
            painter.setPen(pen)
            painter.drawLine(pa, pb)

        # 점 + 라벨
        label_font = QFont()
        label_font.setPointSize(8)
        for idx, node in enumerate(self._nodes):
            p = self._to_px(node.nx, node.ny)
            selected = node.kind == "note" and node.rel == self._selected_rel
            hover = idx == self._hover_idx
            r = self._node_radius(node, selected=selected, hover=hover)

            if node.kind == "root":
                fill = QColor(34, 211, 238)
            elif node.kind == "hub":
                fill = QColor(59, 130, 246)
            else:
                fill = QColor(148, 197, 253) if not selected else QColor(34, 211, 238)

            if selected:
                painter.setPen(QPen(QColor(34, 211, 238, 220), 2.0))
            else:
                painter.setPen(QPen(QColor(15, 23, 42, 160), 1.0))
            painter.setBrush(fill)
            painter.drawEllipse(p, r, r)

            # 라벨: 루트·허브는 항상, 노트는 선택/호버 시 강조
            if node.kind in ("root", "hub"):
                painter.setPen(QColor(224, 242, 254))
            elif selected or hover:
                painter.setPen(QColor(224, 242, 254))
            else:
                painter.setPen(QColor(100, 116, 139))
            painter.setFont(label_font)
            painter.drawText(QPointF(p.x() + r + 4, p.y() + 4), node.label)
