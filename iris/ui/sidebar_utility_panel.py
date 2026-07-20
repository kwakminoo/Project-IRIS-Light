"""사이드바 하단 유틸리티 영역."""

from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from iris.ui.system_metrics_panel import SystemMetricsPanel
from iris.ui.workspace_action_panel import WorkspaceActionPanel


class SidebarUtilityPanel(QWidget):
  """시스템 메트릭 + Workspace 액션."""

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    lay = QVBoxLayout(self)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    self.metrics = SystemMetricsPanel(self)
    self.actions = WorkspaceActionPanel(self)
    lay.addWidget(self.metrics, 1)
    lay.addWidget(self.actions, 0)
