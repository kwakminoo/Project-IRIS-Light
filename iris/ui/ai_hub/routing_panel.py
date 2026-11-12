"""AI Hub — 모델 자동 전환(failover) 체인. Settings History에서 이동."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from iris.runtime.model_failover import MODE_MODEL_CHAIN, MODE_OFF, MODE_RETRY
from iris.storage.database import Database
from iris.storage.failover_prefs import (
    BACKENDS,
    FailoverSettings,
    FallbackEntry,
    load_failover_settings,
    save_failover_settings,
)
from iris.ui.settings.hud_dialog import configure_form, make_form_label, make_hint
from iris.ui.shared.theme_tokens import TOKENS


def _entry_label(entry: FallbackEntry) -> str:
    tail = " · 무료" if entry.free else ""
    return f"{entry.model}  [{entry.backend}]{tail}"


class AiRoutingPanel(QGroupBox):
    """Failover mode / retry / preempt / chain. Persist → save_failover_settings."""

    def __init__(
        self,
        db: Database | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("모델 자동 전환", parent)
        self._db = db
        failover = load_failover_settings(db) if db is not None else FailoverSettings()

        lay = QVBoxLayout(self)
        lay.setSpacing(TOKENS.spacing_sm)
        lay.addWidget(
            make_hint(
                "쓰던 모델이 할당량 소진(429)이나 서버 오류로 막히면 아래 순서대로 "
                "다음 모델에 다시 요청합니다. 대화 맥락은 같이 넘어갑니다. "
                "한도에 걸린 후보는 쿨다운 동안 체인에서 건너뜁니다."
            )
        )

        self._enabled = QCheckBox("모델 자동 전환 사용")
        self._enabled.setChecked(failover.enabled)
        lay.addWidget(self._enabled)

        f_form = QFormLayout()
        configure_form(f_form)

        self._mode = QComboBox()
        self._mode.addItem("다른 모델로 전환", MODE_MODEL_CHAIN)
        self._mode.addItem("같은 모델로 재시도", MODE_RETRY)
        self._mode.addItem("전환 안 함", MODE_OFF)
        idx = self._mode.findData(failover.mode)
        self._mode.setCurrentIndex(idx if idx >= 0 else 0)
        self._mode.setMinimumHeight(32)
        f_form.addRow(make_form_label("실패했을 때"), self._mode)

        self._retry_count = QSpinBox()
        self._retry_count.setRange(0, 10)
        self._retry_count.setValue(failover.retry_count)
        self._retry_count.setMinimumHeight(32)
        f_form.addRow(make_form_label("재시도 횟수"), self._retry_count)

        self._preempt_enabled = QCheckBox("한도에 가까워지면 미리 전환")
        self._preempt_enabled.setChecked(failover.preempt_enabled)
        f_form.addRow(make_form_label("선제 전환"), self._preempt_enabled)

        self._preempt_percent = QSpinBox()
        self._preempt_percent.setRange(50, 100)
        self._preempt_percent.setSuffix(" %")
        self._preempt_percent.setValue(int(failover.preempt_percent))
        self._preempt_percent.setMinimumHeight(32)
        f_form.addRow(make_form_label("선제 전환 기준"), self._preempt_percent)

        self._ask_summary = QCheckBox("전환 전에 쓰던 모델이 인수인계문을 쓰게 함")
        self._ask_summary.setChecked(failover.ask_old_model_summary)
        f_form.addRow(make_form_label("인수인계"), self._ask_summary)
        lay.addLayout(f_form)

        self._chain_list = QListWidget()
        self._chain_list.setMinimumHeight(96)
        for entry in failover.chain:
            item = QListWidgetItem(_entry_label(entry))
            item.setData(256, entry)
            self._chain_list.addItem(item)
        lay.addWidget(self._chain_list)

        add_row = QHBoxLayout()
        self._new_model = QLineEdit()
        self._new_model.setPlaceholderText("전환할 모델 이름 (예: gemma4:free)")
        self._new_model.setMinimumHeight(32)
        self._new_backend = QComboBox()
        for backend in BACKENDS:
            self._new_backend.addItem(backend, backend)
        self._new_backend.setMinimumHeight(32)
        add_btn = QPushButton("추가")
        up_btn = QPushButton("↑")
        down_btn = QPushButton("↓")
        del_btn = QPushButton("삭제")
        for widget in (
            self._new_model,
            self._new_backend,
            add_btn,
            up_btn,
            down_btn,
            del_btn,
        ):
            add_row.addWidget(widget)
        lay.addLayout(add_row)
        lay.addWidget(
            make_hint(
                "Iris Agent가 켜져 있으면(기본값) 모든 후보를 Iris Agent 게이트웨이로 시도합니다. "
                "Iris Agent를 끄면 지금 쓰는 모델과 같은 종류의 후보만 쓸 수 있습니다 — "
                "Ollama 모델이면 Ollama 후보만, 커스텀 API 모델이면 API 후보만 시도합니다."
            )
        )

        add_btn.clicked.connect(self._add)
        self._new_model.returnPressed.connect(self._add)
        up_btn.clicked.connect(lambda: self._move(-1))
        down_btn.clicked.connect(lambda: self._move(1))
        del_btn.clicked.connect(self._delete)

        self._chain_widgets = (
            self._mode,
            self._retry_count,
            self._preempt_enabled,
            self._ask_summary,
            self._chain_list,
            self._new_model,
            self._new_backend,
            add_btn,
            up_btn,
            down_btn,
            del_btn,
        )
        self._enabled.toggled.connect(self._sync_enabled)
        self._preempt_enabled.toggled.connect(self._sync_enabled)
        self._mode.currentIndexChanged.connect(self._sync_enabled)
        self._sync_enabled()

    def _add(self) -> None:
        name = self._new_model.text().strip()
        if not name:
            return
        entry = FallbackEntry(
            model=name, backend=self._new_backend.currentData(), free=True
        )
        item = QListWidgetItem(_entry_label(entry))
        item.setData(256, entry)
        self._chain_list.addItem(item)
        self._new_model.clear()

    def _move(self, delta: int) -> None:
        row = self._chain_list.currentRow()
        target = row + delta
        if row < 0 or not (0 <= target < self._chain_list.count()):
            return
        item = self._chain_list.takeItem(row)
        self._chain_list.insertItem(target, item)
        self._chain_list.setCurrentRow(target)

    def _delete(self) -> None:
        row = self._chain_list.currentRow()
        if row >= 0:
            self._chain_list.takeItem(row)

    def _sync_enabled(self) -> None:
        f_on = self._enabled.isChecked()
        for widget in self._chain_widgets:
            widget.setEnabled(f_on)
        self._retry_count.setEnabled(f_on and self._mode.currentData() == MODE_RETRY)
        self._preempt_percent.setEnabled(f_on and self._preempt_enabled.isChecked())

    def _chain_entries(self) -> list[FallbackEntry]:
        out: list[FallbackEntry] = []
        for row in range(self._chain_list.count()):
            entry = self._chain_list.item(row).data(256)
            if isinstance(entry, FallbackEntry):
                out.append(entry)
        return out

    def persist(self) -> None:
        if self._db is None:
            return
        save_failover_settings(
            self._db,
            FailoverSettings(
                enabled=self._enabled.isChecked(),
                mode=self._mode.currentData(),
                retry_count=self._retry_count.value(),
                preempt_percent=float(self._preempt_percent.value()),
                preempt_enabled=self._preempt_enabled.isChecked(),
                ask_old_model_summary=self._ask_summary.isChecked(),
                chain=self._chain_entries(),
            ),
        )
