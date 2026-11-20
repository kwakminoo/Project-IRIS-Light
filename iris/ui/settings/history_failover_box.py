"""설정 — 위키 History 기록·검색.

`build_history_failover_box(db)` 가 QGroupBox 를 돌려주고, 위젯을 박스 속성으로
달아 둔다. 저장은 `save_history_failover` 가 맡는다 — HistorySettings 만 저장한다.
모델 자동 전환 UI는 AI Hub `AiRoutingPanel` 로 옮겼다.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from iris.storage.database import Database
from iris.storage.failover_prefs import (
    HistorySettings,
    load_history_settings,
    save_history_settings,
)
from iris.ui.settings.hud_dialog import (
    TOKENS,
    configure_form,
    make_form_label,
    make_hint,
)


def build_history_failover_box(db: Database) -> QGroupBox:
    """History 기록·검색 설정."""
    history = load_history_settings(db)

    box = QGroupBox("대화 기록 (History)")
    lay = QVBoxLayout(box)
    lay.setSpacing(TOKENS.spacing_sm)
    lay.addWidget(
        make_hint(
            "아이리스와 나눈 대화, 수행한 일, 만든 것, 들어온 데이터를 Iris Wiki "
            "History에 쌓고 검색해 씁니다. 모델을 바꾸거나 할당량이 떨어져 다른 "
            "모델로 넘어갈 때 이 기록에서 맥락을 되찾습니다. 전부 이 PC 안에만 "
            "저장됩니다."
        )
    )

    enabled = QCheckBox("History 기록·검색 사용")
    enabled.setChecked(history.enabled)
    lay.addWidget(enabled)

    kinds_row = QHBoxLayout()
    rec_chat = QCheckBox("대화")
    rec_actions = QCheckBox("수행")
    rec_artifacts = QCheckBox("생성물")
    rec_inputs = QCheckBox("입력 데이터")
    rec_chat.setChecked(history.record_chat)
    rec_actions.setChecked(history.record_actions)
    rec_artifacts.setChecked(history.record_artifacts)
    rec_inputs.setChecked(history.record_inputs)
    for widget in (rec_chat, rec_actions, rec_artifacts, rec_inputs):
        kinds_row.addWidget(widget)
    kinds_row.addStretch(1)
    lay.addLayout(kinds_row)

    past_chats = QCheckBox("새 채팅에서도 이전 대화 참고 (참고한 기록은 답변 위에 표시)")
    past_chats.setChecked(history.reference_past_chats)
    lay.addWidget(past_chats)

    form = QFormLayout()
    configure_form(form)

    retrieval = QSpinBox()
    retrieval.setRange(0, 20)
    retrieval.setValue(history.retrieval_limit)
    retrieval.setMinimumHeight(32)
    form.addRow(make_form_label("모델에 붙일 과거 기록 수"), retrieval)

    embed_enabled = QCheckBox("의미 검색 사용 (Ollama 임베딩 모델 필요)")
    embed_enabled.setChecked(history.embed_enabled)
    form.addRow(make_form_label("검색 방식"), embed_enabled)

    embed_model = QLineEdit(history.embed_model)
    embed_model.setPlaceholderText("비우면 설치된 것 중 자동 선택 (bge-m3 권장)")
    embed_model.setMinimumHeight(32)
    form.addRow(make_form_label("임베딩 모델"), embed_model)
    lay.addLayout(form)
    lay.addWidget(
        make_hint(
            "임베딩 모델이 없으면 키워드 검색만 씁니다. `ollama pull bge-m3` 로 "
            "한국어 의미 검색을 켤 수 있습니다."
        )
    )

    def _sync_enabled() -> None:
        on = enabled.isChecked()
        for widget in (
            rec_chat,
            rec_actions,
            rec_artifacts,
            rec_inputs,
            past_chats,
            retrieval,
            embed_enabled,
            embed_model,
        ):
            widget.setEnabled(on)
        embed_model.setEnabled(on and embed_enabled.isChecked())

    enabled.toggled.connect(_sync_enabled)
    embed_enabled.toggled.connect(_sync_enabled)
    _sync_enabled()

    box.history_enabled = enabled  # type: ignore[attr-defined]
    box.record_chat = rec_chat  # type: ignore[attr-defined]
    box.record_actions = rec_actions  # type: ignore[attr-defined]
    box.record_artifacts = rec_artifacts  # type: ignore[attr-defined]
    box.record_inputs = rec_inputs  # type: ignore[attr-defined]
    box.retrieval_limit = retrieval  # type: ignore[attr-defined]
    box.reference_past_chats = past_chats  # type: ignore[attr-defined]
    box.embed_enabled = embed_enabled  # type: ignore[attr-defined]
    box.embed_model = embed_model  # type: ignore[attr-defined]
    return box


def save_history_failover(db: Database, box: QGroupBox) -> None:
    """박스의 History 값만 저장한다. 다이얼로그 Save 에서 부른다."""
    save_history_settings(
        db,
        HistorySettings(
            enabled=box.history_enabled.isChecked(),  # type: ignore[attr-defined]
            record_chat=box.record_chat.isChecked(),  # type: ignore[attr-defined]
            record_actions=box.record_actions.isChecked(),  # type: ignore[attr-defined]
            record_artifacts=box.record_artifacts.isChecked(),  # type: ignore[attr-defined]
            record_inputs=box.record_inputs.isChecked(),  # type: ignore[attr-defined]
            retrieval_limit=box.retrieval_limit.value(),  # type: ignore[attr-defined]
            embed_model=box.embed_model.text(),  # type: ignore[attr-defined]
            embed_enabled=box.embed_enabled.isChecked(),  # type: ignore[attr-defined]
            reference_past_chats=box.reference_past_chats.isChecked(),  # type: ignore[attr-defined]
        ),
    )
