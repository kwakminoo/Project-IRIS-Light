"""사이드바 하단 유틸리티 영역."""

from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from iris.ui.monitor.system_metrics_panel import SystemMetricsPanel
from iris.ui.sidebar.voice_hint_panel import VoiceHintPanel
from iris.ui.sidebar.workspace_action_panel import WorkspaceActionPanel


class SidebarUtilityPanel(QWidget):
  """시스템 메트릭 + 음성 명령 힌트 + Workspace 액션."""

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    lay = QVBoxLayout(self)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    self.metrics = SystemMetricsPanel(self)
    # 아이콘 그리드 바로 위 — 상황별 문장 힌트가 뜨는 자리
    self.voice_hint = VoiceHintPanel(self)
    self.actions = WorkspaceActionPanel(self)
    lay.addWidget(self.metrics, 1)
    lay.addWidget(self.voice_hint, 0)
    lay.addWidget(self.actions, 0)
