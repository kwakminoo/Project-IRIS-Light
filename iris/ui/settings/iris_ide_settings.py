"""IRIS IDE 설정/설치 UI — 시작 프로토콜과 동일한 터미널 로그."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import QDialog, QMessageBox, QPushButton, QVBoxLayout, QWidget

from iris.system.setup_protocol import SetupProtocol, SetupStepResult
from iris.ui.settings.hud_dialog import configure_hud_dialog, make_hint, make_title, run_hud_confirm
from iris.ui.shared.theme_tokens import TOKENS
from iris.ui.window.setup_wizard import _NeedsUserCard


class _IrisIdeInstallWorker(QThread):
    install_chunk = pyqtSignal(str, object, bool)
    step_changed = pyqtSignal(object)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._succeeded = False

    def run(self) -> None:
        proto = SetupProtocol()
        proto.bind_stream(lambda t, p, r: self.install_chunk.emit(t, p, r))
        try:
            result = proto.install_optional_step(
                "iris_ide",
                on_progress=lambda r: self.step_changed.emit(r),
            )
            if result.status == "done":
                self._succeeded = True
                self.finished_ok.emit(result.message or "IRIS IDE runtime ready")
            else:
                self.failed.emit((result.message or "설치 실패")[:800])
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc)[:800])
        finally:
            proto.bind_stream(None)


class IrisIdeInstallDialog(QDialog):
    """시작 프로토콜 _NeedsUserCard 와 동일한 설치 터미널 UI."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        configure_hud_dialog(
            self,
            title="IRIS IDE 설치",
            min_w=560,
            min_h=360,
            default_w=640,
            default_h=420,
        )
        self.setModal(True)
        self._worker: _IrisIdeInstallWorker | None = None
        self._succeeded = False
        self._started = False

        root = QVBoxLayout(self)
        root.setContentsMargins(
            TOKENS.spacing_xl,
            TOKENS.spacing_lg,
            TOKENS.spacing_xl,
            TOKENS.spacing_lg,
        )
        root.setSpacing(TOKENS.spacing_md)
        root.addWidget(make_title("IRIS IDE"))
        root.addWidget(
            make_hint(
                "Node · yarn · Theia 빌드 — 진행 상황은 아래 로그에 표시됩니다. "
                "시작 프로토콜 설치와 동일한 방식입니다."
            )
        )

        self._card = _NeedsUserCard(self)
        root.addWidget(self._card)

        self._close_btn = QPushButton("닫기")
        self._close_btn.hide()
        self._close_btn.clicked.connect(self.accept)
        row = QVBoxLayout()
        row.addWidget(self._close_btn, 0, Qt.AlignmentFlag.AlignRight)
        root.addLayout(row)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._started:
            self._started = True
            self._start_install()

    def _start_install(self) -> None:
        self._card.begin_install(
            "IRIS IDE 설치 중… yarn · tsc · theia build 순으로 진행됩니다.",
            reset=True,
            step_id="iris_ide",
        )
        worker = _IrisIdeInstallWorker(parent=self)
        self._worker = worker
        worker.install_chunk.connect(self._on_chunk)
        worker.step_changed.connect(self._on_step)
        worker.finished_ok.connect(self._on_ok)
        worker.failed.connect(self._on_fail)
        worker.start()

    def _on_chunk(self, text: str, percent: object, replace: bool) -> None:
        pct = percent if isinstance(percent, int) else None
        self._card.set_install_chunk(text, pct, bool(replace))

    def _on_step(self, result: object) -> None:
        if not isinstance(result, SetupStepResult):
            return
        if result.status == "installing" and result.message:
            self._card.begin_install(
                result.message or result.label,
                reset=False,
                step_id="iris_ide",
            )

    def _on_ok(self, msg: str) -> None:
        self._worker = None
        self._succeeded = True
        self._card.finish_install(message=f"설치 완료 — {msg}")
        self._close_btn.show()

    def _on_fail(self, err: str) -> None:
        self._worker = None
        self._card.finish_install(message=f"설치 실패 — {err[:240]}")
        self._card.set_install_chunk(err, None, False)
        self._close_btn.show()

    def _install_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._install_running():
            stay = run_hud_confirm(
                self,
                title="IRIS IDE 설치",
                body="지금 설치가 진행 중입니다. 닫으면 설치가 중단됩니다.",
                hint="「계속 진행」을 누르면 설치를 이어서 합니다.",
                badge="INSTALL",
                ok_text="계속 진행",
                cancel_text="닫기",
                default_ok=True,
            )
            if stay:
                event.ignore()
                return
            self._worker.wait(3000)
        super().closeEvent(event)

    @property
    def succeeded(self) -> bool:
        return self._succeeded


def prompt_iris_ide_install(parent: QWidget | None) -> bool:
    """미설치 IRIS IDE 선택 시 설치 확인. True=설치 시도 완료(성공)."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle("IRIS IDE")
    box.setText("IRIS IDE가 설치되어 있지 않습니다.")
    box.setInformativeText("IRIS에 내장된 Eclipse Theia 기반 IDE입니다. 지금 설치할까요?")
    cancel_btn = box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
    install_btn = box.addButton("설치", QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(install_btn)
    box.exec()
    if box.clickedButton() is not install_btn:
        return False
    return run_iris_ide_install_dialog(parent)


def run_iris_ide_install_dialog(parent: QWidget | None) -> bool:
    """설치/복구 — 시작 프로토콜과 동일한 터미널 로그 다이얼로그."""
    dlg = IrisIdeInstallDialog(parent)
    dlg.exec()
    return dlg.succeeded
