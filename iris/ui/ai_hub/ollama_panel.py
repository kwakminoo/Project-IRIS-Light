"""AI Hub — Iris-recommended local (Ollama) models: list, pull, CLI paste, library link."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from iris.config.settings import Settings
from iris.infrastructure.local_model_catalog import (
    OLLAMA_LIBRARY_URL,
    RECOMMENDED_LOCAL_MODELS,
    LocalCatalogEntry,
    is_installed,
    parse_ollama_cli,
    with_install_flags,
)
from iris.infrastructure.local_vision import delete_model, pull_model
from iris.infrastructure.ollama_client import OllamaClient
from iris.ui.settings.hud_dialog import make_hint
from iris.ui.shared.theme_tokens import TOKENS

_MODALITY_KO = {
    "chat": "채팅",
    "vision": "비전",
    "embedding": "임베딩",
}


class _InstalledListWorker(QThread):
    """Installed model names only — does not block the dialog."""

    finished_ok = pyqtSignal(object)  # list[str]
    failed = pyqtSignal(str)

    def __init__(self, base_url: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base_url = base_url

    def run(self) -> None:
        try:
            models = OllamaClient(self._base_url).list_models()
            names = [m.name for m in models if getattr(m, "name", None)]
            self.finished_ok.emit(names)
        except Exception as e:
            self.failed.emit(str(e)[:200])


class _PullWorker(QThread):
    progress = pyqtSignal(str, object)  # status, pct|None
    finished_ok = pyqtSignal(str)  # pull_name
    failed = pyqtSignal(str, str)  # pull_name, error

    def __init__(
        self,
        base_url: str,
        pull_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._pull_name = pull_name
        self._abort = False

    def request_abort(self) -> None:
        self._abort = True

    def run(self) -> None:
        def on_progress(status: str, pct: int | None) -> None:
            self.progress.emit(status or "", pct)

        err = pull_model(
            self._base_url,
            self._pull_name,
            on_progress=on_progress,
            should_abort=lambda: self._abort or self.isInterruptionRequested(),
        )
        if err:
            self.failed.emit(self._pull_name, err)
        else:
            self.finished_ok.emit(self._pull_name)


class _DeleteWorker(QThread):
    finished_ok = pyqtSignal(str)  # name
    failed = pyqtSignal(str, str)  # name, error

    def __init__(
        self,
        base_url: str,
        name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._name = name

    def run(self) -> None:
        err = delete_model(self._base_url, self._name)
        if err:
            self.failed.emit(self._name, err)
        else:
            self.finished_ok.emit(self._name)


def _term_stylesheet(object_name: str) -> str:
    return f"""
            QPlainTextEdit#{object_name} {{
                background-color: {TOKENS.void_black};
                color: {TOKENS.neon_cyan};
                border: 1px solid {TOKENS.panel_border};
                border-radius: {TOKENS.radius_sm}px;
                font-family: {TOKENS.font_mono};
                font-size: {TOKENS.font_size_micro};
                padding: 6px;
            }}
            """


class AiOllamaPanel(QGroupBox):
    """Recommended local models + in-app Pull + Ollama CLI paste + library link."""

    models_changed = pyqtSignal()
    model_use_requested = pyqtSignal(str)

    def __init__(
        self,
        settings: Settings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Ollama (로컬)", parent)
        self._settings = settings
        self._installed: set[str] = set()
        self._list_worker: _InstalledListWorker | None = None
        self._pull_worker: _PullWorker | None = None
        self._delete_worker: _DeleteWorker | None = None
        self._pull_busy = False
        self._delete_busy = False
        self._pull_succeeded = False
        self._delete_succeeded = False
        self._row_btns: dict[str, QPushButton] = {}
        self._inst_row_btns: dict[str, tuple[QPushButton, QPushButton]] = {}
        self._busy_refresh = False
        self._shown_once = False

        lay = QVBoxLayout(self)
        lay.setSpacing(TOKENS.spacing_sm)
        lay.addWidget(
            make_hint(
                "Iris가 추천하는 로컬 모델입니다. 「받기」로 설치하거나, "
                "Ollama 사이트의 CLI를 붙여 넣고 「설치」를 누르세요."
            )
        )

        self._status = QLabel("설치 목록을 확인하는 중…")
        self._status.setWordWrap(True)
        self._status.setObjectName("HudHint")
        lay.addWidget(self._status)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setMinimumHeight(14)
        self._progress.setTextVisible(False)
        lay.addWidget(self._progress)

        self._rows_host = QWidget(self)
        self._rows_lay = QVBoxLayout(self._rows_host)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        self._rows_lay.setSpacing(TOKENS.spacing_sm)
        lay.addWidget(self._rows_host)
        self._rebuild_rows()

        more = QPushButton("모델 더 보기")
        more.setFlat(True)
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        more.setStyleSheet(
            f"QPushButton {{ color: {TOKENS.neon_cyan}; background: transparent; "
            f"border: none; padding: 4px 0; font-size: {TOKENS.font_size_caption}; }}"
            f"QPushButton:hover {{ text-decoration: underline; }}"
        )
        more.clicked.connect(self._open_library)
        lay.addWidget(more, 0, Qt.AlignmentFlag.AlignHCenter)

        cli_row = QHBoxLayout()
        cli_row.setSpacing(8)
        self._cli_input = QLineEdit()
        self._cli_input.setPlaceholderText("ollama run qwen3.8 또는 ollama pull 모델")
        self._cli_input.returnPressed.connect(self._on_cli_install)
        cli_row.addWidget(self._cli_input, 1)
        self._install_btn = QPushButton("설치")
        self._install_btn.setMinimumHeight(28)
        self._install_btn.clicked.connect(self._on_cli_install)
        cli_row.addWidget(self._install_btn, 0)
        lay.addLayout(cli_row)

        self._term = QPlainTextEdit()
        self._term.setObjectName("AiHubOllamaTerm")
        self._term.setReadOnly(True)
        self._term.setMaximumBlockCount(800)
        self._term.setMinimumHeight(96)
        self._term.setMaximumHeight(160)
        self._term.setStyleSheet(_term_stylesheet("AiHubOllamaTerm"))
        self._term.hide()
        lay.addWidget(self._term)

        installed_title = QLabel("설치된 모델")
        installed_title.setObjectName("HudHint")
        lay.addWidget(installed_title)

        self._installed_host = QWidget(self)
        self._installed_lay = QVBoxLayout(self._installed_host)
        self._installed_lay.setContentsMargins(0, 0, 0, 0)
        self._installed_lay.setSpacing(TOKENS.spacing_sm)
        lay.addWidget(self._installed_host)
        self._rebuild_installed_rows()

        self._delete_term = QPlainTextEdit()
        self._delete_term.setObjectName("AiHubOllamaDeleteTerm")
        self._delete_term.setReadOnly(True)
        self._delete_term.setMaximumBlockCount(800)
        self._delete_term.setMinimumHeight(96)
        self._delete_term.setMaximumHeight(160)
        self._delete_term.setStyleSheet(_term_stylesheet("AiHubOllamaDeleteTerm"))
        self._delete_term.hide()
        lay.addWidget(self._delete_term)

        self._start_refresh()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._shown_once:
            if not self._busy_refresh and not self._pull_busy and not self._delete_busy:
                self._start_refresh()
        self._shown_once = True

    def _open_library(self) -> None:
        QDesktopServices.openUrl(QUrl(OLLAMA_LIBRARY_URL))

    def _base_url(self) -> str:
        return str(
            getattr(self._settings, "ollama_base_url", "") or "http://127.0.0.1:11434/v1"
        )

    def _ensure_term_visible(self) -> None:
        if not self._term.isVisible():
            self._term.show()

    def _append_term(self, line: str) -> None:
        self._ensure_term_visible()
        self._term.appendPlainText(line)

    def _ensure_delete_term_visible(self) -> None:
        if not self._delete_term.isVisible():
            self._delete_term.show()

    def _append_delete_term(self, line: str) -> None:
        self._ensure_delete_term_visible()
        self._delete_term.appendPlainText(line)

    def _action_busy(self) -> bool:
        return self._pull_busy or self._delete_busy

    def _on_cli_install(self) -> None:
        raw = self._cli_input.text()
        name = parse_ollama_cli(raw)
        if name is None:
            self._append_term("오류: Ollama CLI 형식이 아닙니다. 예: ollama pull 모델")
            self._status.setText("CLI 형식이 올바르지 않습니다")
            return
        self._append_term(f"설치 시작: {name}")
        self._start_pull(name)

    def _start_refresh(self) -> None:
        if self._list_worker is not None and self._list_worker.isRunning():
            return
        if self._action_busy():
            return
        self._busy_refresh = True
        self._progress.setRange(0, 0)
        self._progress.setVisible(True)
        self._status.setText("설치 목록을 확인하는 중…")
        worker = _InstalledListWorker(self._base_url(), self)
        self._list_worker = worker
        worker.finished_ok.connect(self._on_list_ok)
        worker.failed.connect(self._on_list_fail)
        worker.finished.connect(self._on_list_finished)
        worker.start()

    def _on_list_finished(self) -> None:
        self._busy_refresh = False

    def _on_list_ok(self, names: object) -> None:
        if isinstance(names, list):
            self._installed = {str(n) for n in names if str(n).strip()}
        else:
            self._installed = set()
        self._rebuild_rows()
        self._rebuild_installed_rows()
        if not self._action_busy():
            self._progress.setVisible(False)
            self._status.setText(f"로컬 설치 {len(self._installed)}개 확인")

    def _on_list_fail(self, err: str) -> None:
        # Keep last-good `_installed` so recommended flags stay coherent.
        if not self._action_busy():
            self._progress.setVisible(False)
            self._status.setText(f"설치 목록을 가져오지 못했습니다: {err or '알 수 없음'}")
        self._rebuild_rows()
        self._rebuild_installed_rows()

    def _rebuild_rows(self) -> None:
        while self._rows_lay.count():
            item = self._rows_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._row_btns.clear()

        flagged = with_install_flags(RECOMMENDED_LOCAL_MODELS, self._installed)
        for entry, installed in flagged:
            self._rows_lay.addWidget(self._make_row(entry, installed))

    def _make_row(self, entry: LocalCatalogEntry, installed: bool) -> QWidget:
        row = QWidget(self._rows_host)
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        modality = _MODALITY_KO.get(entry.modality, entry.modality)
        size = f"약 {entry.approx_size_gb:g}GB"
        state = "설치됨" if installed else "미설치"
        label = QLabel(f"{entry.display_name} · {modality} · {size} · {state}")
        label.setWordWrap(True)
        h.addWidget(label, 1)
        btn = QPushButton("설치됨" if installed else "받기")
        btn.setMinimumHeight(28)
        if installed or self._action_busy():
            btn.setEnabled(False)
        else:
            btn.setEnabled(True)
            btn.clicked.connect(
                lambda _checked=False, name=entry.pull_name: self._start_pull(name)
            )
        self._row_btns[entry.pull_name] = btn
        h.addWidget(btn, 0)
        return row

    def _rebuild_installed_rows(self) -> None:
        while self._installed_lay.count():
            item = self._installed_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._inst_row_btns.clear()

        names = sorted(self._installed)
        if not names:
            empty = QLabel("설치된 모델 없음")
            empty.setObjectName("HudHint")
            self._installed_lay.addWidget(empty)
            return

        busy = self._action_busy()
        for name in names:
            self._installed_lay.addWidget(self._make_installed_row(name, busy))

    def _make_installed_row(self, name: str, busy: bool) -> QWidget:
        row = QWidget(self._installed_host)
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        label = QLabel(name)
        label.setWordWrap(True)
        h.addWidget(label, 1)
        use_btn = QPushButton("사용")
        use_btn.setMinimumHeight(28)
        use_btn.setEnabled(not busy)
        use_btn.clicked.connect(
            lambda _checked=False, n=name: self.model_use_requested.emit(n)
        )
        del_btn = QPushButton("삭제")
        del_btn.setMinimumHeight(28)
        del_btn.setEnabled(not busy)
        del_btn.clicked.connect(
            lambda _checked=False, n=name: self._start_delete(n)
        )
        self._inst_row_btns[name] = (use_btn, del_btn)
        h.addWidget(use_btn, 0)
        h.addWidget(del_btn, 0)
        return row

    def _set_install_controls_enabled(self, enabled: bool) -> None:
        self._install_btn.setEnabled(enabled)
        self._cli_input.setEnabled(enabled)
        for name, btn in self._row_btns.items():
            if enabled and not is_installed(name, self._installed):
                btn.setEnabled(True)
            else:
                btn.setEnabled(False)
        for use_btn, del_btn in self._inst_row_btns.values():
            use_btn.setEnabled(enabled)
            del_btn.setEnabled(enabled)

    def _start_pull(self, pull_name: str) -> None:
        if self._action_busy():
            return
        if self._list_worker is not None and self._list_worker.isRunning():
            return
        if is_installed(pull_name, self._installed):
            self._append_term(f"{pull_name} 이미 설치됨")
            self._status.setText(f"{pull_name} 이미 설치됨")
            return
        self._pull_busy = True
        self._pull_succeeded = False
        self._set_install_controls_enabled(False)
        self._ensure_term_visible()
        self._append_term(f"> pull {pull_name}")
        self._progress.setVisible(True)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._status.setText(f"{pull_name} 받는 중…")
        worker = _PullWorker(self._base_url(), pull_name, self)
        self._pull_worker = worker
        worker.progress.connect(self._on_pull_progress)
        worker.finished_ok.connect(self._on_pull_ok)
        worker.failed.connect(self._on_pull_fail)
        worker.finished.connect(self._on_pull_finished)
        worker.start()

    def _on_pull_progress(self, status: str, pct: object) -> None:
        if isinstance(pct, int):
            self._progress.setRange(0, 100)
            self._progress.setValue(max(0, min(100, pct)))
            line = f"{status or '받는 중'} ({pct}%)"
            self._status.setText(line)
            self._append_term(line)
        else:
            self._progress.setRange(0, 0)
            if status:
                self._status.setText(status)
                self._append_term(status)

    def _on_pull_ok(self, pull_name: str) -> None:
        self._pull_succeeded = True
        self._installed.add(pull_name)
        msg = f"{pull_name} 설치 완료"
        self._status.setText(msg)
        self._append_term(msg)
        self.models_changed.emit()

    def _on_pull_fail(self, pull_name: str, err: str) -> None:
        self._pull_succeeded = False
        msg = f"{pull_name} 설치 실패: {err or '알 수 없음'}"
        self._status.setText(msg)
        self._append_term(msg)

    def _on_pull_finished(self) -> None:
        self._pull_busy = False
        self._set_install_controls_enabled(True)
        if self._pull_succeeded:
            self._start_refresh()
            return
        self._progress.setVisible(False)
        self._rebuild_rows()
        self._rebuild_installed_rows()

    def _start_delete(self, name: str) -> None:
        if self._action_busy():
            return
        if self._list_worker is not None and self._list_worker.isRunning():
            return
        self._delete_busy = True
        self._delete_succeeded = False
        self._set_install_controls_enabled(False)
        self._append_delete_term(f"> delete {name}")
        self._status.setText(f"{name} 삭제 중…")
        worker = _DeleteWorker(self._base_url(), name, self)
        self._delete_worker = worker
        worker.finished_ok.connect(self._on_delete_ok)
        worker.failed.connect(self._on_delete_fail)
        worker.finished.connect(self._on_delete_finished)
        worker.start()

    def _on_delete_ok(self, name: str) -> None:
        self._delete_succeeded = True
        self._installed.discard(name)
        self._rebuild_installed_rows()
        self._append_delete_term("삭제 완료")
        self._status.setText(f"{name} 삭제 완료")
        self.models_changed.emit()
        # Graft: do not auto-pick another model in the panel after deleting active.

    def _on_delete_fail(self, name: str, err: str) -> None:
        self._delete_succeeded = False
        self._append_delete_term(f"삭제 실패: {err or '알 수 없음'}")
        self._status.setText(f"{name} 삭제 실패: {err or '알 수 없음'}")

    def _on_delete_finished(self) -> None:
        self._delete_busy = False
        self._set_install_controls_enabled(True)
        if self._delete_succeeded:
            self._start_refresh()
            return
        self._rebuild_rows()
        self._rebuild_installed_rows()

    def shutdown(self) -> None:
        """Dialog close must call this — QGroupBox may not get closeEvent."""
        self._stop_workers()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.shutdown()
        super().closeEvent(event)

    def _stop_workers(self) -> None:
        list_w = self._list_worker
        if list_w is not None and list_w.isRunning():
            list_w.wait(2000)
        pull_w = self._pull_worker
        if pull_w is not None and pull_w.isRunning():
            pull_w.request_abort()
            pull_w.requestInterruption()
            pull_w.wait(2000)
        delete_w = self._delete_worker
        if delete_w is not None and delete_w.isRunning():
            delete_w.wait(2000)
