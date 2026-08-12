"""Iris 시작 프로토콜 위저드 — Core 강제 + Optional 스킵 가능."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from iris.config.settings import Settings
from iris.system.setup_protocol import (
    CORE_STEP_IDS,
    CORE_STEP_LABELS,
    OPTIONAL_IDS,
    SetupProtocol,
    SetupStepResult,
    is_core_ready,
    is_setup_demo,
    is_setup_preview,
    reset_core_ready,
)
from iris.ui.settings.hud_dialog import configure_hud_dialog, make_hint, make_title
from iris.ui.shared.theme_tokens import TOKENS
from iris.ui.workers.setup_protocol_worker import SetupProtocolWorker

_STATUS_MARK = {
    "pending": "○",
    "installing": "…",
    "verifying": "…",
    "needs_user": "!",
    "done": "✓",
    "failed": "✗",
    "skipped": "–",
}


class _NeedsUserCard(QFrame):
    done_clicked = pyqtSignal(str)  # pasted value (optional)
    later_clicked = pyqtSignal()
    install_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("NeedsUserCard")
        self._url = ""
        lay = QVBoxLayout(self)
        lay.setSpacing(TOKENS.spacing_sm)
        self._why = QLabel("")
        self._why.setWordWrap(True)
        lay.addWidget(self._why)
        self._hint = QLabel("")
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet(f"color: {TOKENS.text_secondary};")
        lay.addWidget(self._hint)
        self._paste = QLineEdit()
        self._paste.setPlaceholderText("필요 시 키를 붙여넣기")
        self._paste.setEchoMode(QLineEdit.EchoMode.Password)
        self._paste.hide()
        lay.addWidget(self._paste)
        row = QHBoxLayout()
        self._open_btn = QPushButton("열기")
        self._open_btn.clicked.connect(self._open_url)
        self._open_btn.hide()
        row.addWidget(self._open_btn)
        self._install_btn = QPushButton("설치")
        self._install_btn.clicked.connect(self.install_clicked.emit)
        self._install_btn.hide()
        row.addWidget(self._install_btn)
        row.addStretch(1)
        self._later_btn = QPushButton("나중에")
        self._later_btn.clicked.connect(self.later_clicked.emit)
        row.addWidget(self._later_btn)
        self._done_btn = QPushButton("완료했어요")
        self._done_btn.clicked.connect(lambda: self.done_clicked.emit(self._paste.text()))
        row.addWidget(self._done_btn)
        lay.addLayout(row)

    def bind(self, result: SetupStepResult, *, allow_skip: bool) -> None:
        self._why.setText(result.message or result.label)
        self._hint.setText(result.action_hint or "")
        self._url = (result.action_url or "").strip()
        self._open_btn.setVisible(bool(self._url))
        self._install_btn.setVisible(bool(result.can_install))
        # 키 붙여넣기는 external_api 등 hint에 '붙여넣'이 있을 때만
        need_paste = "붙여넣" in (result.action_hint or "") or "키" in (result.action_hint or "")
        self._paste.setVisible(need_paste and result.step_id in ("external_api",))
        self._paste.clear()
        self._later_btn.setVisible(allow_skip)
        self.setVisible(True)

    def _open_url(self) -> None:
        if self._url:
            QDesktopServices.openUrl(QUrl(self._url))


class SetupWizard(QDialog):
    """첫 실행 / 환경 다시 설정 위저드."""

    setup_finished = pyqtSignal(bool)

    def __init__(
        self,
        settings: Settings,
        *,
        mode: str = "first_run",  # first_run | repair
        parent=None,
    ) -> None:
        super().__init__(parent)
        configure_hud_dialog(
            self,
            title="Iris 시작 프로토콜",
            min_w=640,
            min_h=520,
            default_w=720,
            default_h=640,
        )
        self.setModal(True)
        self._settings = settings
        self._mode = mode
        self._worker: SetupProtocolWorker | None = None
        self._core_phase = True
        self._step_status: dict[str, str] = {s: "pending" for s in CORE_STEP_IDS}
        self._finished = False

        root = QVBoxLayout(self)
        root.setContentsMargins(TOKENS.spacing_xl, TOKENS.spacing_lg, TOKENS.spacing_xl, TOKENS.spacing_lg)
        root.setSpacing(TOKENS.spacing_md)
        root.addWidget(make_title("START PROTOCOL"))
        self._subtitle = QLabel(
            "【UI 데모】실제 설치는 하지 않습니다. 프로토콜 UX만 체험합니다."
            if is_setup_demo()
            else (
                "필수 환경을 순서대로 준비합니다. Core는 건너뛸 수 없습니다."
                if mode == "first_run"
                else "환경을 다시 점검·설치합니다."
            )
        )
        self._subtitle.setWordWrap(True)
        root.addWidget(self._subtitle)
        root.addWidget(
            make_hint(
                "【데모】NeedsUser 카드가 뜨면 「완료했어요」/「나중에」를 눌러 보세요. "
                "API 키·설치 파일은 변경되지 않습니다."
                if is_setup_demo()
                else "사람 손이 필요한 단계만 안내창이 뜹니다. API 키는 로그에 표시되지 않습니다."
            )
        )

        self._progress = QProgressBar()
        self._progress.setRange(0, len(CORE_STEP_IDS))
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFormat("Core %v / %m")
        root.addWidget(self._progress)

        self._current = QLabel("준비 중…")
        self._current.setWordWrap(True)
        root.addWidget(self._current)

        self._list = QListWidget()
        for sid in CORE_STEP_IDS:
            item = QListWidgetItem(f"{_STATUS_MARK['pending']}  {CORE_STEP_LABELS[sid]}")
            item.setData(Qt.ItemDataRole.UserRole, sid)
            self._list.addItem(item)
        root.addWidget(self._list, 1)

        self._card = _NeedsUserCard()
        self._card.hide()
        self._card.done_clicked.connect(self._on_user_done)
        self._card.later_clicked.connect(self._on_user_later)
        self._card.install_clicked.connect(self._on_user_install)
        root.addWidget(self._card)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(120)
        root.addWidget(self._log)

        btn_row = QHBoxLayout()
        self._retry_btn = QPushButton("재시도")
        self._retry_btn.hide()
        self._retry_btn.clicked.connect(self._start_worker)
        btn_row.addWidget(self._retry_btn)
        btn_row.addStretch(1)
        self._enter_btn = QPushButton("메인으로 들어가기")
        self._enter_btn.hide()
        self._enter_btn.clicked.connect(self._accept_ok)
        btn_row.addWidget(self._enter_btn)
        root.addLayout(btn_row)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._worker is None and not self._finished:
            self._start_worker()

    def _start_worker(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._retry_btn.hide()
        self._enter_btn.hide()
        self._card.hide()
        self._core_phase = True
        self._progress.setRange(0, len(CORE_STEP_IDS))
        self._progress.setFormat("Core %v / %m")
        if self._mode == "repair":
            reset_core_ready()
        proto = SetupProtocol(
            ollama_base_url=self._settings.ollama_base_url,
            hermes_base_url=self._settings.hermes_base_url,
            hermes_command=self._settings.hermes_command,
            min_model=self._settings.ollama_model or "",
        )
        worker = SetupProtocolWorker(
            proto,
            run_optional=True,
            optional_ids=OPTIONAL_IDS,
            parent=self,
        )
        self._worker = worker
        worker.step_changed.connect(self._on_step)
        worker.needs_user.connect(self._on_needs_user)
        worker.log_line.connect(self._append_log)
        worker.phase_changed.connect(self._on_phase)
        worker.failed.connect(self._on_failed)
        worker.finished_ok.connect(self._on_finished)
        worker.start()

    def _append_log(self, line: str) -> None:
        text = (line or "").strip()
        if text:
            self._log.append(text)

    def _on_phase(self, phase: str) -> None:
        self._core_phase = phase == "core"
        if phase == "optional":
            self._subtitle.setText("추가 기능(선택) — 「나중에」로 건너뛸 수 있습니다.")
            self._progress.setRange(0, 0)  # indeterminate
            self._progress.setFormat("Optional…")
        elif phase == "done":
            self._progress.setRange(0, len(CORE_STEP_IDS))
            self._progress.setValue(len(CORE_STEP_IDS))
            self._progress.setFormat("Core Ready")

    def _on_step(self, result: object) -> None:
        if not isinstance(result, SetupStepResult):
            return
        if result.step_id in self._step_status:
            self._step_status[result.step_id] = result.status
            self._refresh_list()
            done_n = sum(1 for s in CORE_STEP_IDS if self._step_status.get(s) == "done")
            if self._core_phase:
                self._progress.setValue(done_n)
            self._current.setText(f"{result.label}: {result.message or result.status}")
        elif result.status != "needs_user":
            self._current.setText(f"{result.label}: {result.message or result.status}")

    def _refresh_list(self) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            sid = item.data(Qt.ItemDataRole.UserRole)
            st = self._step_status.get(sid, "pending")
            mark = _STATUS_MARK.get(st, "?")
            item.setText(f"{mark}  {CORE_STEP_LABELS.get(sid, sid)}")

    def _on_needs_user(self, result: object) -> None:
        if not isinstance(result, SetupStepResult):
            return
        allow_skip = not self._core_phase or result.step_id not in CORE_STEP_IDS
        # Core needs_user도 재시도만 — later 숨김
        if result.step_id in CORE_STEP_IDS:
            allow_skip = False
        self._current.setText(result.message or result.label)
        self._card.bind(result, allow_skip=allow_skip)

    def _on_user_done(self, _paste: str) -> None:
        self._card.hide()
        if self._worker is not None:
            self._worker.resume_user("done")

    def _on_user_later(self) -> None:
        self._card.hide()
        if self._worker is not None:
            self._worker.resume_user("skip")

    def _on_user_install(self) -> None:
        self._card.hide()
        self._current.setText("설치 실행 중… UAC가 뜨면 허용해 주세요.")
        self._append_log("설치 시작…")
        if self._worker is not None:
            self._worker.resume_user("install")

    def _on_failed(self, err: str) -> None:
        self._append_log(f"실패: {err}")
        self._current.setText(f"실패 — {err}")
        self._retry_btn.show()

    def _on_finished(self, ok: bool) -> None:
        self._worker = None
        if ok and is_core_ready():
            self._finished = True
            self._current.setText("Core Ready — 메인 HUD로 들어갈 수 있습니다.")
            self._enter_btn.show()
            self.setup_finished.emit(True)
            # 자동 진입은 하지 않음 — 사용자가 확인
        else:
            self._retry_btn.show()
            self.setup_finished.emit(False)

    def _accept_ok(self) -> None:
        self.accept()

    def reject(self) -> None:
        # 데모/repair: 닫기 허용. first_run 실사용: Core 미완료면 차단
        if not is_setup_preview() and self._mode != "repair" and not is_core_ready():
            self._append_log("Core가 아직 준비되지 않았습니다. 재시도하세요.")
            return
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_abort()
            self._worker.wait(3000)
        if self._mode == "repair" and not is_core_ready() and not is_setup_preview():
            from iris.system.setup_protocol import mark_core_ready_if_healthy

            mark_core_ready_if_healthy(
                ollama_base_url=self._settings.ollama_base_url,
                hermes_base_url=self._settings.hermes_base_url,
                hermes_command=self._settings.hermes_command,
            )
        super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        if not is_setup_preview() and self._mode != "repair" and not is_core_ready():
            event.ignore()
            self._append_log("Core 완료 전까지 창을 닫을 수 없습니다.")
            return
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_abort()
            self._worker.wait(3000)
        if self._mode == "repair" and not is_core_ready() and not is_setup_preview():
            from iris.system.setup_protocol import mark_core_ready_if_healthy

            mark_core_ready_if_healthy(
                ollama_base_url=self._settings.ollama_base_url,
                hermes_base_url=self._settings.hermes_base_url,
                hermes_command=self._settings.hermes_command,
            )
        super().closeEvent(event)
