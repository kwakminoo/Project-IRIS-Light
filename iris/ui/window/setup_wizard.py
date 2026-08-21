"""Iris 시작 프로토콜 위저드 — Core 강제 + Optional 스킵 가능."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QPainter, QPen, QTextCursor
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
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
from iris.ui.settings.hud_dialog import configure_hud_dialog, make_hint, make_title, run_hud_confirm
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


_STREAM_STEPS = {
    "mcp_venv",
    "ollama_install",
    "ollama_model",
    "hermes_install",
    "voice",
    "emulator",
}

# winget/UAC 승격이 멈추는 걸 막으려고 콘솔 창을 일부러 숨기지 않는 단계들
# (setup_protocol.py의 _run_streamed(..., hidden=False) 호출부와 동일 목록).
# 이 창은 출력이 전부 파이프로 Iris 로그에 새 나가서 화면엔 빈 채로 떠 있다 —
# 사용자가 "멈췄다"고 오해하기 쉬워 안내 문구를 따로 보여준다.
_VISIBLE_CONSOLE_STEPS = {"ollama_install", "hermes_install", "emulator"}


class _SpinnerWidget(QWidget):
    """직접 그리는 로딩 스피너 — 유니코드 브라유 문자는 PC마다 대체 글꼴이 달라
    굵기·정렬이 어긋나 보였다. 벡터로 그리면 항상 동일하게 보인다."""

    def __init__(self, parent: QWidget | None = None, *, size: int = 14) -> None:
        super().__init__(parent)
        self._size = size
        self._angle = 0
        self.setFixedSize(size, size)

    def tick(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ARG002, N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(TOKENS.neon_cyan))
        pen.setWidthF(1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        m = 2
        rect = self.rect().adjusted(m, m, -m, -m)
        span = 270 * 16
        p.drawArc(rect, -self._angle * 16, span)
        p.end()


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
        self._console_hint = QLabel(
            "설치 중 뜨는 검은 창은 내용이 비어 있는 게 정상입니다 — "
            "진행 상황은 이 아래 로그에 표시됩니다."
        )
        self._console_hint.setWordWrap(True)
        self._console_hint.setStyleSheet(f"color: {TOKENS.warning};")
        self._console_hint.hide()
        lay.addWidget(self._console_hint)
        self._step_id = ""
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
        # 설치 시작 시 _install_btn 자리를 대신 차지하는 로딩 표시 — 버튼이 그냥
        # 사라지지 않고 "지금 여기서 설치 중"임을 보여준다.
        self._loading_row = QWidget()
        loading_lay = QHBoxLayout(self._loading_row)
        loading_lay.setContentsMargins(10, 4, 10, 4)
        loading_lay.setSpacing(6)
        self._loading_row.setObjectName("SetupInstallLoadingBtn")
        self._loading_row.setStyleSheet(
            f"""
            QWidget#SetupInstallLoadingBtn {{
                border: 1px solid {TOKENS.neon_cyan};
                border-radius: {TOKENS.radius_sm}px;
                background-color: transparent;
            }}
            """
        )
        self._spinner = _SpinnerWidget()
        loading_lay.addWidget(self._spinner)
        self._loading_label = QLabel("설치 중…")
        self._loading_label.setStyleSheet(f"color: {TOKENS.neon_cyan}; border: none; background: transparent;")
        loading_lay.addWidget(self._loading_label)
        self._loading_row.hide()
        row.addWidget(self._loading_row)
        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(90)
        self._spin_timer.timeout.connect(self._spinner.tick)
        row.addStretch(1)
        self._later_btn = QPushButton("나중에")
        self._later_btn.clicked.connect(self.later_clicked.emit)
        row.addWidget(self._later_btn)
        self._done_btn = QPushButton("완료했어요")
        self._done_btn.clicked.connect(lambda: self.done_clicked.emit(self._paste.text()))
        row.addWidget(self._done_btn)
        lay.addLayout(row)
        self._bar = QProgressBar()
        self._bar.setObjectName("SetupInstallBar")
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(3)
        self._bar.setRange(0, 0)
        self._bar.setStyleSheet(
            f"""
            QProgressBar#SetupInstallBar {{
                background-color: {TOKENS.metric_track};
                border: none;
                border-radius: 1px;
                max-height: 3px;
                min-height: 3px;
            }}
            QProgressBar#SetupInstallBar::chunk {{
                background-color: {TOKENS.neon_cyan};
                border-radius: 1px;
            }}
            """
        )
        self._bar.hide()
        lay.addWidget(self._bar)
        self._term = QPlainTextEdit()
        self._term.setObjectName("SetupInstallTerm")
        self._term.setReadOnly(True)
        self._term.setMaximumBlockCount(800)
        self._term.setMinimumHeight(96)
        self._term.setMaximumHeight(160)
        self._term.setStyleSheet(
            f"""
            QPlainTextEdit#SetupInstallTerm {{
                background-color: {TOKENS.void_black};
                color: {TOKENS.neon_cyan};
                border: 1px solid {TOKENS.panel_border};
                border-radius: {TOKENS.radius_sm}px;
                font-family: {TOKENS.font_mono};
                font-size: {TOKENS.font_size_micro};
                padding: 6px;
            }}
            """
        )
        self._term.hide()
        lay.addWidget(self._term)

    def bind(self, result: SetupStepResult, *, allow_skip: bool) -> None:
        self.end_install()
        self._step_id = result.step_id
        self._why.setText(result.message or result.label)
        self._hint.setText(result.action_hint or "")
        self._hint.setVisible(bool(result.action_hint))
        self._url = (result.action_url or "").strip()
        self._open_btn.setVisible(bool(self._url))
        self._install_btn.setVisible(bool(result.can_install))
        # 키 붙여넣기는 external_api 등 hint에 '붙여넣'이 있을 때만
        need_paste = "붙여넣" in (result.action_hint or "") or "키" in (result.action_hint or "")
        self._paste.setVisible(need_paste and result.step_id in ("external_api",))
        self._paste.clear()
        self._later_btn.setVisible(allow_skip)
        self._done_btn.setVisible(True)
        self.setVisible(True)

    def is_installing(self) -> bool:
        return self._bar.isVisible()

    def begin_install(self, why: str = "", *, reset: bool = True, step_id: str = "") -> None:
        if why:
            self._why.setText(why)
        if step_id:
            self._step_id = step_id
        self._hint.hide()
        self._console_hint.setVisible(self._step_id in _VISIBLE_CONSOLE_STEPS)
        self._paste.hide()
        self._open_btn.hide()
        self._install_btn.hide()
        self._later_btn.hide()
        self._done_btn.hide()
        self._loading_row.show()
        self._spin_timer.start()
        if reset or not self._bar.isVisible():
            self._bar.setRange(0, 0)
            self._bar.setValue(0)
            if reset:
                self._term.clear()
        self._bar.show()
        self._term.show()
        self.setVisible(True)

    def set_install_chunk(self, text: str, percent: int | None, replace: bool) -> None:
        if not self._bar.isVisible():
            self.begin_install(reset=False)
        if percent is not None:
            self._bar.setRange(0, 100)
            self._bar.setValue(max(0, min(100, int(percent))))
        line = (text or "").rstrip()
        if line:
            if replace:
                cursor = self._term.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                cursor.movePosition(
                    QTextCursor.MoveOperation.StartOfBlock,
                    QTextCursor.MoveMode.KeepAnchor,
                )
                cursor.insertText(line)
                self._term.setTextCursor(cursor)
            else:
                self._term.appendPlainText(line)
            bar = self._term.verticalScrollBar()
            bar.setValue(bar.maximum())

    def end_install(self) -> None:
        self._spin_timer.stop()
        self._loading_row.hide()
        self._console_hint.hide()
        self._bar.hide()
        self._term.hide()

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
        self._force_close = False
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
        worker.install_chunk.connect(self._on_install_chunk)
        worker.phase_changed.connect(self._on_phase)
        worker.failed.connect(self._on_failed)
        worker.finished_ok.connect(self._on_finished)
        worker.start()
        if is_setup_preview():
            self._append_log("미리보기 모드 — 실제 설치는 하지 않습니다.")
        else:
            self._append_log("실제 설치 모드 — 「설치」를 누르면 winget/공식 스크립트가 실행됩니다.")

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
        if result.status == "installing" and result.step_id in _STREAM_STEPS:
            self._card.begin_install(
                result.message or result.label,
                reset=not self._card.is_installing(),
                step_id=result.step_id,
            )
        elif result.status in ("done", "failed", "skipped"):
            if self._card.is_installing():
                self._card.end_install()
                self._card.hide()
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
        self._card.begin_install("설치 실행 중… UAC가 뜨면 허용해 주세요.", reset=True)
        self._append_log("설치 시작…")
        if self._worker is not None:
            self._worker.resume_user("install")

    def _on_install_chunk(self, text: str, percent: object, replace: bool) -> None:
        pct = percent if isinstance(percent, int) else None
        self._card.set_install_chunk(text, pct, bool(replace))

    def _on_failed(self, err: str) -> None:
        self._card.end_install()
        self._append_log(f"실패: {err}")
        self._current.setText(f"실패 — {err}")
        self._retry_btn.show()

    def _on_finished(self, ok: bool) -> None:
        self._worker = None
        self._card.end_install()
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

    def _is_install_running(self) -> bool:
        if self._card.is_installing():
            return True
        return bool(self._worker is not None and self._worker.is_install_running())

    def _abort_worker(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_abort()
            self._worker.wait(5000)

    def allow_close(self) -> bool:
        """설치 중이면 확인창. True면 닫기 허용."""
        if self._force_close or is_setup_preview():
            return True
        if not self._is_install_running():
            return True
        stay = run_hud_confirm(
            self,
            title="시작 프로토콜",
            body="지금 설치가 진행 중입니다. 닫으면 설치가 중단됩니다.",
            hint="「계속 진행」을 누르면 설치를 이어서 합니다.",
            badge="INSTALL",
            ok_text="계속 진행",
            cancel_text="닫기",
            default_ok=True,
        )
        return not stay

    def abort_and_close(self) -> None:
        self._force_close = True
        self._abort_worker()
        self.reject()

    def reject(self) -> None:
        if not self.allow_close():
            return
        self._abort_worker()
        if self._mode == "repair" and not is_core_ready() and not is_setup_preview():
            from iris.system.setup_protocol import mark_core_ready_if_healthy

            mark_core_ready_if_healthy(
                ollama_base_url=self._settings.ollama_base_url,
                hermes_base_url=self._settings.hermes_base_url,
                hermes_command=self._settings.hermes_command,
            )
        super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self.allow_close():
            event.ignore()
            return
        self._abort_worker()
        if self._mode == "repair" and not is_core_ready() and not is_setup_preview():
            from iris.system.setup_protocol import mark_core_ready_if_healthy

            mark_core_ready_if_healthy(
                ollama_base_url=self._settings.ollama_base_url,
                hermes_base_url=self._settings.hermes_base_url,
                hermes_command=self._settings.hermes_command,
            )
        super().closeEvent(event)
