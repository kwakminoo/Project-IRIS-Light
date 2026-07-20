"""Iris Light 설정 — Ollama / Hermes 연결."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from iris.config.settings import Settings


@dataclass(frozen=True)
class LightSettingsSelection:
    ollama_base_url: str
    ollama_model: str
    hermes_enabled: bool
    hermes_command: str


class SettingsDialog(QDialog):
    """클라우드/API 연결 설정 (STT/TTS·오케스트레이터 제외)."""

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Iris Light 설정")
        self.setMinimumWidth(480)
        self._settings = settings
        self._result: LightSettingsSelection | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        self.setStyleSheet(
            """
            QDialog, QWidget {
                font-family: "Noto Sans KR", "Segoe UI Variable", "Segoe UI", "Malgun Gothic";
                font-size: 13px;
            }
            QLineEdit {
                background-color: #1a1c24;
                color: #ffffff;
                border: 1px solid #3f3f5f;
                border-radius: 4px;
                padding: 6px;
            }
            """
        )

        title = QLabel("설정")
        title.setObjectName("PanelTitle")
        root.addWidget(title)

        hint = QLabel(
            "Ollama 클라우드/로컬 모델과 Hermes Agent 연결을 설정합니다. "
            "대화·도구 실행 연동은 이후 단계에서 연결됩니다."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self._ollama_url = QLineEdit(settings.ollama_base_url)
        self._ollama_model = QLineEdit(settings.ollama_model)
        self._hermes_cmd = QLineEdit(settings.hermes_command)
        self._hermes_on = QCheckBox("Hermes Agent 사용")
        self._hermes_on.setChecked(settings.hermes_enabled)

        form.addRow("Ollama Base URL", self._ollama_url)
        form.addRow("Ollama Model", self._ollama_model)
        form.addRow("Hermes 명령", self._hermes_cmd)
        form.addRow("", self._hermes_on)
        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _accept(self) -> None:
        self._result = LightSettingsSelection(
            ollama_base_url=self._ollama_url.text().strip() or "http://127.0.0.1:11434/v1",
            ollama_model=self._ollama_model.text().strip(),
            hermes_enabled=self._hermes_on.isChecked(),
            hermes_command=self._hermes_cmd.text().strip() or "hermes",
        )
        self.accept()

    def selection(self) -> LightSettingsSelection | None:
        return self._result
