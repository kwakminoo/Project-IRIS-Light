"""AI Hub — analytics metric rows (요청 / 성공 / 토큰 / 지연)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from iris.storage.ai_analytics import aggregate_stats, load_samples
from iris.storage.database import Database
from iris.ui.settings.hud_dialog import make_hint
from iris.ui.shared.theme_tokens import TOKENS


def _metric_row(name: str, value: str) -> tuple[QWidget, QLabel]:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 4, 0, 4)
    lay.setSpacing(TOKENS.spacing_sm)
    name_lbl = QLabel(name)
    name_lbl.setObjectName("HudMetricName")
    name_lbl.setMinimumWidth(96)
    name_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    value_lbl = QLabel(value)
    value_lbl.setObjectName("HudMetricValue")
    value_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    lay.addWidget(name_lbl, 0)
    lay.addWidget(value_lbl, 1)
    return row, value_lbl


class AiAnalyticsPanel(QGroupBox):
    """HUD metric tiles from Iris-owned call samples."""

    def __init__(
        self,
        db: Database | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Analytics", parent)
        self._db = db

        lay = QVBoxLayout(self)
        lay.setSpacing(TOKENS.spacing_sm)
        lay.addWidget(
            make_hint(
                "최근 AI 호출의 요청·성공·토큰·지연을 Iris가 로컬에 기록합니다."
            )
        )

        req_row, self._req_value = _metric_row("요청", "0")
        ok_row, self._ok_value = _metric_row("성공", "—")
        tok_row, self._tok_value = _metric_row("토큰", "0 / 0")
        lat_row, self._lat_value = _metric_row("지연", "0 ms")
        lay.addWidget(req_row)
        lay.addWidget(ok_row)
        lay.addWidget(tok_row)
        lay.addWidget(lat_row)

        refresh = QPushButton("새로고침")
        refresh.setFixedWidth(88)
        refresh.clicked.connect(self.refresh)
        lay.addWidget(refresh, 0, Qt.AlignmentFlag.AlignLeft)

        self.refresh()

    def showEvent(self, event) -> None:  # noqa: N802
        self.refresh()
        super().showEvent(event)

    def refresh(self) -> None:
        samples = load_samples(self._db) if self._db is not None else []
        stats = aggregate_stats(samples)
        self._req_value.setText(str(stats.requests))
        if stats.requests <= 0:
            self._ok_value.setText("—")
            self._tok_value.setText("0 / 0")
            self._lat_value.setText("0 ms")
            return
        self._ok_value.setText(f"{stats.success_rate * 100:.0f}%")
        self._tok_value.setText(f"{stats.tokens_in} / {stats.tokens_out}")
        self._lat_value.setText(f"{stats.avg_latency_ms:.0f} ms")
