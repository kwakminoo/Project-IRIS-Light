"""HUD system metrics panel — CPU/GPU/MEM + API 월 할당량."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from iris.infrastructure.api_quota import ApiQuota, format_quota_pair
from iris.system.metrics_snapshot import MetricsSnapshot
from iris.ui.shared.glass_panel import wrap_glass_panel
from iris.ui.shared.section_header import apply_section_panel_layout, make_section_header
from iris.ui.shared.theme_tokens import TOKENS

_ROW_GAP_PX = 2
_LABEL_MIN_W = 58
_USAGE_MIN_W = 52
_BAR_H = 7
_LINE_CORE_PX = 1.5


class _NeonLineBar(QWidget):
    """얇은 네온 사인 라인 게이지 (직사각형·끝 둥글지 않음)."""

    def __init__(self, fill_color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HudNeonLineBar")
        self._ratio = 0.0
        self._color = QColor(fill_color)
        self.setFixedHeight(_BAR_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

    def set_fill_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def set_ratio(self, ratio: float) -> None:
        self._ratio = max(0.0, min(1.0, float(ratio)))
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        mid_y = h * 0.5
        track = QColor(TOKENS.metric_track)
        painter.setPen(QPen(track, _LINE_CORE_PX))
        painter.drawLine(0, int(mid_y), w, int(mid_y))

        fill_w = int(round(w * self._ratio))
        if fill_w <= 0:
            painter.end()
            return

        c = self._color
        glow = QColor(c)
        glow.setAlpha(55)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawRect(QRectF(0, mid_y - 2.5, fill_w, 5.0))

        soft = QColor(c)
        soft.setAlpha(140)
        painter.setBrush(soft)
        painter.drawRect(QRectF(0, mid_y - 1.25, fill_w, 2.5))

        core = QColor(c)
        core.setAlpha(255)
        painter.setPen(QPen(core, _LINE_CORE_PX))
        painter.drawLine(0, int(mid_y), fill_w, int(mid_y))
        painter.end()


class _MetricRow(QWidget):
    """라벨(+사용량)과 네온 라인이 같은 줄."""

    def __init__(
        self,
        name: str,
        fill_color: str,
        *,
        show_usage: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("HudMetricRow")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, _ROW_GAP_PX, 0, _ROW_GAP_PX)
        lay.setSpacing(TOKENS.spacing_xs)

        self._name = QLabel(name)
        self._name.setObjectName("HudMetricName")
        self._name.setMinimumWidth(_LABEL_MIN_W)
        self._name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self._name, 0)

        self._usage = QLabel("")
        self._usage.setObjectName("HudMetricUsage")
        self._usage.setMinimumWidth(_USAGE_MIN_W if show_usage else 0)
        self._usage.setMaximumWidth(72 if show_usage else 0)
        self._usage.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._usage.setVisible(show_usage)
        lay.addWidget(self._usage, 0)

        self._bar = _NeonLineBar(fill_color)
        lay.addWidget(self._bar, 1)

    def apply_percent(self, percent: float | None, *, label: str | None = None) -> None:
        if label is not None:
            self._name.setText(label)
        if percent is None:
            self._bar.set_ratio(0.0)
            return
        self._bar.set_ratio(max(0.0, min(100.0, float(percent))) / 100.0)

    def apply_quota(self, quota: ApiQuota | None, *, empty_label: str | None = None) -> None:
        if empty_label is not None:
            self._name.setText(empty_label)
        if quota is None:
            self._usage.setText("-")
            self._bar.set_ratio(0.0)
            return
        self._name.setText(quota.label)
        self._usage.setText(format_quota_pair(quota.used, quota.total))
        if quota.total <= 0:
            self._bar.set_ratio(0.0)
            self.setToolTip(
                "Ollama Cloud usage: set OLLAMA_CLOUD_COOKIE or "
                "%LOCALAPPDATA%/iris-light/ollama_cookie.txt "
                "(from ollama.com/settings DevTools)"
            )
        else:
            self.setToolTip("")
            self._bar.set_ratio(quota.percent / 100.0)


class SystemMetricsPanel(QWidget):
    """Realtime CPU/GPU/memory + API 월 할당량 HUD."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SystemMetricsPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        inner = QWidget()
        inner.setObjectName("SystemMetricsPanelInner")
        lay = QVBoxLayout(inner)
        apply_section_panel_layout(lay)
        lay.setSpacing(_ROW_GAP_PX)
        lay.addWidget(make_section_header("SYSTEM METRICS", title_object_name="SidebarTitle"))

        self._cpu = _MetricRow("CPU", TOKENS.metric_fill_cpu)
        self._gpu = _MetricRow("GPU", TOKENS.metric_fill_gpu)
        self._mem = _MetricRow("MEMORY", TOKENS.metric_fill_mem)
        for row in (self._cpu, self._gpu, self._mem):
            lay.addWidget(row)

        self._api_rows: dict[str, _MetricRow] = {
            "serp": _MetricRow("SERP", TOKENS.metric_fill_api, show_usage=True),
            "fire": _MetricRow("FIRE", TOKENS.metric_fill_api, show_usage=True),
            "sess": _MetricRow("SESS", TOKENS.metric_fill_api, show_usage=True),
            "week": _MetricRow("WEEK", TOKENS.metric_fill_api, show_usage=True),
        }
        for row in self._api_rows.values():
            row.hide()
            lay.addWidget(row)

        lay.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(wrap_glass_panel(inner))

    def apply_snapshot(self, snap: MetricsSnapshot) -> None:
        self._cpu.apply_percent(snap.cpu_percent)
        self._mem.apply_percent(snap.memory_percent)
        if snap.gpu_percent is None:
            self._gpu.apply_percent(None, label=snap.gpu_label.upper())
        else:
            self._gpu.apply_percent(snap.gpu_percent, label="GPU")

    def apply_quotas(self, quotas: object) -> None:
        by_key: dict[str, ApiQuota] = {}
        if isinstance(quotas, list):
            for q in quotas:
                if isinstance(q, ApiQuota):
                    by_key[q.key] = q
        for key, row in self._api_rows.items():
            q = by_key.get(key)
            if q is None:
                row.hide()
                continue
            row.show()
            row.apply_quota(q)
