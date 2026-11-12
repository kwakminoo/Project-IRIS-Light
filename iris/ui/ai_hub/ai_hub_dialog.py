"""AI Hub dialog — Models/LLM providers, routing (failover), Analytics."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QMessageBox,
    QVBoxLayout,
)

from iris.config.settings import Settings
from iris.storage.database import Database
from iris.system.iris_agent_tool_choice import (
    TOOL_CHOICE_AUTO,
    TOOL_CHOICE_REQUIRED,
    load_hermes_tool_choice,
    set_hermes_tool_choice,
)
from iris.ui.ai_hub.analytics_panel import AiAnalyticsPanel
from iris.ui.ai_hub.catalog_panel import AiCatalogPanel
from iris.ui.ai_hub.providers_panel import AiProvidersPanel
from iris.ui.ai_hub.routing_panel import AiRoutingPanel
from iris.ui.settings.hud_dialog import (
    configure_form,
    configure_hud_dialog,
    make_form_label,
    make_hint,
    make_scroll_body,
    make_title,
)
from iris.ui.shared.theme_tokens import TOKENS


class AiHubDialog(QDialog):
    """Iris AI Hub. Open with parent=None from frameless MainWindow (0xC0000409)."""

    def __init__(
        self,
        db: Database | None,
        settings: Settings,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._settings = settings
        configure_hud_dialog(
            self,
            title="AI HUB",
            min_w=640,
            min_h=560,
            default_w=760,
            default_h=720,
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(
            TOKENS.spacing_xl, TOKENS.spacing_lg, TOKENS.spacing_xl, TOKENS.spacing_lg
        )
        root.setSpacing(TOKENS.spacing_md)
        root.addWidget(make_title("AI HUB"))
        root.addWidget(
            make_hint(
                "LLM 제공자와 모델 목록, 자동 전환 체인을 여기서 관리합니다. "
                "검색·캘린더 API는 설정에 있습니다."
            )
        )

        scroll, content_lay = make_scroll_body()
        self._providers = AiProvidersPanel(db, settings, self)
        self._catalog = AiCatalogPanel(db, self)
        self._routing = AiRoutingPanel(db, self)
        self._analytics = AiAnalyticsPanel(db, self)
        tool_choice_box = QGroupBox("Agent 도구 호출")
        tool_choice_lay = QVBoxLayout(tool_choice_box)
        tool_choice_lay.addWidget(
            make_hint(
                "Auto는 모델이 필요한 경우에만 도구를 호출하고 바로 답변할 수 있습니다. "
                "Required는 매 응답에 도구 호출을 강제하며 respond 종료 도구를 추가합니다."
            )
        )
        tool_choice_form = QFormLayout()
        configure_form(tool_choice_form)
        self._tool_choice = QComboBox()
        self._tool_choice.addItem("Auto (권장)", TOOL_CHOICE_AUTO)
        self._tool_choice.addItem("Required", TOOL_CHOICE_REQUIRED)
        index = self._tool_choice.findData(load_hermes_tool_choice())
        self._tool_choice.setCurrentIndex(max(0, index))
        self._tool_choice.setMinimumHeight(32)
        tool_choice_form.addRow(make_form_label("Tool choice"), self._tool_choice)
        tool_choice_lay.addLayout(tool_choice_form)
        content_lay.addWidget(tool_choice_box)
        content_lay.addWidget(self._providers)
        content_lay.addWidget(self._catalog)
        content_lay.addWidget(self._routing)
        content_lay.addWidget(self._analytics)
        content_lay.addStretch(1)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _accept(self) -> None:
        _, status = set_hermes_tool_choice(str(self._tool_choice.currentData() or ""))
        if not status.startswith("hermes agent.tool_choice"):
            QMessageBox.warning(self, "Tool choice 저장 실패", status)
            return
        self._providers.persist()
        self._routing.persist()
        self.accept()
