"""Iris 시작 프로토콜 위저드 — Core 강제 + Optional 스킵 가능."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QGuiApplication, QPainter, QPen, QTextCursor
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
    OPTIONAL_LABELS,
    VISIBLE_CONSOLE_STEPS,
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

_STATUS_A11Y = {
    "pending": "대기",
    "installing": "진행 중",
    "verifying": "검증 중",
    "needs_user": "사용자 확인 필요",
    "done": "완료",
    "failed": "실패",
    "skipped": "건너뜀",
}


# 설치·기동 중 터미널 패널을 띄울 Core/Optional 단계
_STREAM_STEPS = {
    "mcp_venv",
    "ollama_install",
    "ollama_model",
    "ollama_cloud",
    "hermes_install",
    "hermes_env",
    "hermes_provider",
    "iris_control_sync",
    "hermes_gateway",
    "core_smoke",
    "voice",
    "voice_full",
    "learning",
    "emulator",
    "mobile_mcp",
    "iris_ide",
}

# needs_user 장시간 방치 시 힌트 (ms)
_NEEDS_USER_IDLE_HINT_MS = 120_000


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
        self._open_app = ""
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
        self._open_app = (result.open_local_app or "").strip().lower()
        self._open_btn.setText(result.login_label if result.can_login else "열기")
        # 앱 열기 또는 URL 중 하나라도 있으면 버튼 표시
        self._open_btn.setVisible(bool(self._open_app) or bool(self._url) or result.can_login)
        self._install_btn.setText(result.install_label or "설치")
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
        self._console_hint.setVisible(self._step_id in VISIBLE_CONSOLE_STEPS)
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

    def append_hint(self, text: str) -> None:
        extra = (text or "").strip()
        if not extra:
            return
        cur = self._hint.text() or ""
        if extra in cur:
            return
        self._hint.setText((cur + "\n" if cur else "") + extra)
        self._hint.show()

    def finish_install(self, *, message: str = "") -> None:
        """설치 종료 — 터미널 로그는 유지."""
        self._spin_timer.stop()
        self._loading_row.hide()
        self._console_hint.hide()
        self._bar.hide()
        if message:
            self._why.setText(message)
            self._why.show()
        self._term.show()
        self.setVisible(True)

    def _open_url(self) -> None:
        if self._open_app == "ollama":
            try:
                from iris.system.ollama_server import ensure_ollama_running, open_ollama_app

                ok, detail = open_ollama_app()
                ensure_ollama_running("http://127.0.0.1:11434/v1", wait_sec=8.0)
                if ok:
                    self._hint.setText(
                        "Ollama 앱을 열었습니다. 앱에서 클라우드 로그인한 뒤 "
                        "「완료했어요」를 누르면 연결을 다시 확인합니다."
                    )
                    self._hint.show()
                else:
                    # 앱을 못 열면 브라우저 로그인으로 폴백
                    if self._url:
                        QDesktopServices.openUrl(QUrl(self._url))
                    self._hint.setText(
                        f"Ollama 앱을 열지 못했습니다 ({detail}). "
                        "브라우저 로그인 페이지를 열었습니다."
                    )
                    self._hint.show()
                return
            except Exception as exc:  # noqa: BLE001
                self._hint.setText(f"Ollama 열기 실패: {exc}")
                self._hint.show()
                if self._url:
                    QDesktopServices.openUrl(QUrl(self._url))
                return
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
        self._optional_total = len(OPTIONAL_IDS)
        self._needs_user_idle = QTimer(self)
        self._needs_user_idle.setSingleShot(True)
        self._needs_user_idle.timeout.connect(self._on_needs_user_idle)
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
            label = CORE_STEP_LABELS[sid]
            item = QListWidgetItem(f"{_STATUS_MARK['pending']}  {label}")
            item.setData(Qt.ItemDataRole.UserRole, sid)
            item.setData(
                Qt.ItemDataRole.AccessibleDescriptionRole,
                f"{label}, {_STATUS_A11Y['pending']}",
            )
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
        self._copy_diag_btn = QPushButton("진단 정보 복사")
        self._copy_diag_btn.hide()
        self._copy_diag_btn.clicked.connect(self._copy_gateway_diagnosis)
        btn_row.addWidget(self._copy_diag_btn)
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
        # 재시도/재검사: 이전 워커를 끊고 진단 잔상·목록을 비운 뒤 새로 시작한다.
        if self._worker is not None:
            if self._worker.isRunning() or self._worker.is_install_running():
                self._append_log("이전 실행을 종료하는 중…")
                self._abort_worker()
                if self._worker is not None and self._worker.isRunning():
                    if not self._worker.wait(8000):
                        self._append_log(
                            "이전 설치가 아직 정리 중입니다. 잠시 후 재시도하세요."
                        )
                        self._retry_btn.show()
                        return
            try:
                self._worker.failed.disconnect(self._on_failed)
                self._worker.finished_ok.disconnect(self._on_finished)
            except TypeError:
                pass
            self._worker = None

        try:
            from iris.system.hermes_gateway import clear_last_gateway_diagnosis

            clear_last_gateway_diagnosis()
        except Exception:  # noqa: BLE001
            pass

        self._needs_user_idle.stop()
        self._retry_btn.hide()
        self._copy_diag_btn.hide()
        self._enter_btn.hide()
        self._card.hide()
        self._card.end_install()
        self._core_phase = True
        self._finished = False
        self._step_status = {s: "pending" for s in CORE_STEP_IDS}
        self._refresh_list()
        self._progress.setRange(0, len(CORE_STEP_IDS))
        self._progress.setValue(0)
        self._progress.setFormat("Core %v / %m")
        self._current.setText("준비 중…")
        self._log.clear()
        if self._mode == "repair":
            reset_core_ready()
        proto = SetupProtocol(
            ollama_base_url=self._settings.ollama_base_url,
            hermes_base_url=self._settings.hermes_base_url,
            hermes_command=self._settings.hermes_command,
            min_model=self._settings.ollama_model or "",
            allow_core_skip=(self._mode == "repair"),
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
        worker.optional_progress.connect(self._on_optional_progress)
        worker.failed.connect(self._on_failed)
        worker.finished_ok.connect(self._on_finished)
        worker.start()
        if is_setup_preview():
            self._append_log("미리보기 모드 — 실제 설치는 하지 않습니다.")
        else:
            self._append_log("실제 설치 모드 — 「설치」를 누르면 공식 스크립트/winget이 실행됩니다.")

    def _append_log(self, line: str) -> None:
        text = (line or "").strip()
        if text:
            self._log.append(text)

    def _on_phase(self, phase: str) -> None:
        self._core_phase = phase == "core"
        if phase == "optional":
            self._subtitle.setText("추가 기능(선택) — 「나중에」로 건너뛸 수 있습니다.")
            self._progress.setRange(0, self._optional_total)
            self._progress.setValue(0)
            self._progress.setFormat("Optional %v / %m")
        elif phase == "done":
            self._progress.setRange(0, len(CORE_STEP_IDS))
            self._progress.setValue(len(CORE_STEP_IDS))
            self._progress.setFormat("Core Ready")

    def _on_optional_progress(self, index: int, total: int, step_id: str) -> None:
        self._optional_total = max(1, int(total))
        self._progress.setRange(0, self._optional_total)
        # index는 시작 시점(1-based) — 진행 바는 완료 수에 가깝게 index-1
        self._progress.setValue(max(0, int(index) - 1))
        self._progress.setFormat("Optional %v / %m")
        label = OPTIONAL_LABELS.get(step_id, step_id)
        self._current.setText(f"Optional {index}/{total}: {label}")

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
            if (
                not self._core_phase
                and result.step_id in OPTIONAL_IDS
                and result.status in ("done", "skipped", "failed")
            ):
                # optional 완료 반영 — optional_progress 시작값과 맞춤
                cur = self._progress.value()
                if cur < self._progress.maximum():
                    self._progress.setValue(cur + 1)
        if result.status == "installing":
            self._current.setText(f"{result.label}: {result.message or '진행 중…'}")
        if result.step_id in self._step_status:
            self._step_status[result.step_id] = result.status
            self._refresh_list()
            done_n = sum(1 for s in CORE_STEP_IDS if self._step_status.get(s) == "done")
            if self._core_phase:
                self._progress.setValue(done_n)
            if result.status != "installing":
                self._current.setText(f"{result.label}: {result.message or result.status}")
        elif result.status not in ("needs_user", "installing"):
            self._current.setText(f"{result.label}: {result.message or result.status}")

    def _refresh_list(self) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            sid = item.data(Qt.ItemDataRole.UserRole)
            st = self._step_status.get(sid, "pending")
            mark = _STATUS_MARK.get(st, "?")
            a11y = _STATUS_A11Y.get(st, st)
            label = CORE_STEP_LABELS.get(sid, sid)
            item.setText(f"{mark}  {label}")
            item.setData(
                Qt.ItemDataRole.AccessibleDescriptionRole,
                f"{label}, {a11y}",
            )

    def _on_needs_user(self, result: object) -> None:
        if not isinstance(result, SetupStepResult):
            return
        allow_skip = not self._core_phase or result.step_id not in CORE_STEP_IDS
        # Core: first_run 은 스킵 금지. repair 만 위험 고지 후 허용.
        if result.step_id in CORE_STEP_IDS:
            allow_skip = self._mode == "repair"
        self._current.setText(result.message or result.label)
        if allow_skip and result.step_id in CORE_STEP_IDS:
            # 위험 고지 — 카드 hint에 덧붙임
            warned = SetupStepResult(
                step_id=result.step_id,
                status=result.status,
                message=result.message,
                action_url=result.action_url,
                action_hint=(
                    (result.action_hint or "")
                    + ("\n" if result.action_hint else "")
                    + "【주의】repair 전용 건너뛰기 — 이 단계가 준비되지 않으면 채팅/MCP가 실패할 수 있습니다."
                ),
                label=result.label,
                can_install=result.can_install,
                can_login=result.can_login,
                install_label=result.install_label,
                login_label=result.login_label,
                open_local_app=result.open_local_app,
            )
            )
            self._card.bind(warned, allow_skip=True)
        else:
            self._card.bind(result, allow_skip=allow_skip)
        self._needs_user_idle.start(_NEEDS_USER_IDLE_HINT_MS)

    def _on_needs_user_idle(self) -> None:
        self._append_log(
            "이 단계에서 대기 중입니다. 「완료했어요」/「나중에」/「설치」를 눌러 주세요."
        )
        if self._card.isVisible() and not self._card.is_installing():
            self._card.append_hint("오래 기다리셨다면 버튼을 눌러 주세요.")

    def _on_user_done(self, _paste: str) -> None:
        self._needs_user_idle.stop()
        self._card.hide()
        if self._worker is not None:
            self._worker.resume_user("done")

    def _on_user_later(self) -> None:
        self._needs_user_idle.stop()
        self._card.hide()
        if self._worker is not None:
            self._worker.resume_user("skip")

    def _on_user_install(self) -> None:
        self._needs_user_idle.stop()
        self._card.begin_install("설치 실행 중… UAC가 뜨면 허용해 주세요.", reset=True)
        self._append_log("설치 시작…")
        if self._worker is not None:
            self._worker.resume_user("install")

    def _on_install_chunk(self, text: str, percent: object, replace: bool) -> None:
        """설치 중에는 카드 터미널만 전체 스트림 — 하단 로그는 요약(상태행)만."""
        pct = percent if isinstance(percent, int) else None
        line = (text or "").strip()
        if line and replace:
            self._current.setText(line if pct is None else f"{line} ({pct}%)")
        elif line and not replace:
            self._current.setText(line)
        if self._card.is_installing() or self._card.isVisible():
            self._card.set_install_chunk(text, pct, bool(replace))

    def _copy_gateway_diagnosis(self) -> None:
        try:
            from iris.system.hermes_gateway import (
                get_last_gateway_diagnosis,
                gateway_diagnosis_path,
            )

            diag = get_last_gateway_diagnosis()
            if diag is not None:
                text = diag.copy_text()
            else:
                path = gateway_diagnosis_path()
                text = path.read_text(encoding="utf-8") if path.is_file() else ""
            if not text:
                text = self._current.text() or "진단 정보 없음"
            QGuiApplication.clipboard().setText(text)
            self._append_log("진단 정보를 클립보드에 복사했습니다.")
        except Exception as exc:  # noqa: BLE001
            self._append_log(f"진단 복사 실패: {exc}")

    def _on_failed(self, err: str) -> None:
        self._card.end_install()
        self._append_log(f"실패: {err}")
        self._current.setText(f"실패 — {err}")
        self._retry_btn.show()
        # gateway 진단 코드가 있으면 복사 버튼 표시
        low = (err or "").lower()
        if "[" in (err or "") or "gateway" in low or "health" in low or "hermes" in low:
            self._copy_diag_btn.show()

    def _on_finished(self, ok: bool) -> None:
        self._worker = None
        self._card.end_install()
        if ok and is_core_ready():
            self._finished = True
            self._current.setText("Core Ready — 메인 HUD로 들어갈 수 있습니다.")
            self._enter_btn.show()
            self._copy_diag_btn.hide()
            self.setup_finished.emit(True)
            # 자동 진입은 하지 않음 — 사용자가 확인
        else:
            self._retry_btn.show()
            self._copy_diag_btn.show()
            self.setup_finished.emit(False)

    def _accept_ok(self) -> None:
        self.accept()

    def _is_install_running(self) -> bool:
        if self._card.is_installing():
            return True
        # gateway 재기동 등은 _active_proc 이 없어도 워커가 바쁘다
        if self._worker is not None and self._worker.isRunning():
            return True
        return False

    def _abort_worker(self) -> None:
        self._needs_user_idle.stop()
        if self._worker is not None and self._worker.isRunning():
            # request_abort → protocol.abort → taskkill /T 프로세스 트리
            self._worker.request_abort()
            # ponytail: UI 스레드에서 수 초 wait 하면 응답없음. 짧게 폴링만.
            for _ in range(6):
                if self._worker.wait(200):
                    break

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
        # ponytail: mark_core_ready_if_healthy 를 UI 스레드에서 돌리면
        # Ollama/Hermes warm 으로 응답없음이 난다 — 닫기 경로에서는 생략.
        super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self.allow_close():
            event.ignore()
            return
        self._abort_worker()
        super().closeEvent(event)
