"""업무 학습 VLM 안내 — 부적합 모델 시 대안 선택."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from iris.learning.vlm_policy import VlmVerdict
from iris.ui.settings.hud_dialog import configure_hud_dialog
from iris.ui.shared.theme_tokens import TOKENS


class VlmGuideDialog(QDialog):
    """학습 취소 | 녹화만 진행 | 다른 VLM 선택."""

    RESULT_CANCEL = "cancel"
    RESULT_RECORD_ONLY = "record_only"
    RESULT_USE_VLM = "use_vlm"

    def __init__(
        self,
        *,
        verdict: VlmVerdict,
        ollama_options: list[tuple[str, str]],
        api_options: list[tuple[str, str, str]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        configure_hud_dialog(
            self,
            title="업무 학습 · VLM 안내",
            min_w=520,
            min_h=360,
            default_w=560,
            default_h=420,
        )
        self._choice = self.RESULT_CANCEL
        self._selected_provider = ""
        self._selected_model = ""

        root = QVBoxLayout(self)
        root.setSpacing(TOKENS.spacing_md)

        title = QLabel("현재 모델로는 업무 학습(VLM)을 진행할 수 없습니다")
        title.setObjectName("HudTitle")
        title.setWordWrap(True)
        root.addWidget(title)

        reason = QLabel(
            f"선택 모델: {verdict.provider}:{verdict.model or '(없음)'}\n"
            f"사유: {verdict.reason}"
        )
        reason.setWordWrap(True)
        reason.setObjectName("HudHint")
        root.addWidget(reason)

        root.addWidget(QLabel("대안 VLM 선택"))
        self._combo = QComboBox()
        self._combo.setMinimumHeight(32)
        # value: provider|model
        for name, reason_s in ollama_options:
            self._combo.addItem(f"[Ollama] {name} — {reason_s}", f"ollama|{name}")
        for provider, model, label in api_options:
            self._combo.addItem(f"[API:{provider}] {label}", f"{provider}|{model}")
        if self._combo.count() == 0:
            self._combo.addItem("(사용 가능한 VLM 없음)", "")
            self._combo.setEnabled(False)
        root.addWidget(self._combo)

        tip = QLabel(
            "「녹화만 진행」은 화면/입력을 저장하고, VLM trace는 나중에 키가 있을 때 "
            "재처리할 수 있는 pending 상태로 둡니다."
        )
        tip.setWordWrap(True)
        tip.setObjectName("HudHint")
        root.addWidget(tip)

        row = QHBoxLayout()
        btn_cancel = QPushButton("학습 취소")
        btn_record = QPushButton("녹화만 진행")
        btn_use = QPushButton("선택한 VLM으로 학습")
        btn_use.setEnabled(self._combo.isEnabled() and bool(self._combo.currentData()))
        btn_cancel.clicked.connect(self._on_cancel)
        btn_record.clicked.connect(self._on_record)
        btn_use.clicked.connect(self._on_use)
        row.addWidget(btn_cancel)
        row.addWidget(btn_record)
        row.addWidget(btn_use)
        root.addLayout(row)

        # Esc = cancel
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        box.rejected.connect(self._on_cancel)
        box.hide()
        root.addWidget(box)

    def _on_cancel(self) -> None:
        self._choice = self.RESULT_CANCEL
        self.reject()

    def _on_record(self) -> None:
        self._choice = self.RESULT_RECORD_ONLY
        self.accept()

    def _on_use(self) -> None:
        data = str(self._combo.currentData() or "")
        if "|" not in data:
            return
        provider, _, model = data.partition("|")
        self._selected_provider = provider
        self._selected_model = model
        self._choice = self.RESULT_USE_VLM
        self.accept()

    def choice(self) -> str:
        return self._choice

    def selected_provider(self) -> str:
        return self._selected_provider

    def selected_model(self) -> str:
        return self._selected_model
