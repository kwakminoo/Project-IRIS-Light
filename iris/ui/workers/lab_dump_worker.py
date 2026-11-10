"""PDF lab-script dump stays off the Qt GUI thread."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from iris.knowledge.lab_script_dump import dump_lab_scripts, format_lab_dump_reply


class LabDumpWorker(QThread):
    finished_ok = pyqtSignal(object)  # LabDumpReply
    finished_err = pyqtSignal(str)

    def __init__(
        self,
        pdf_path: str,
        project_root: str,
        *,
        query: str = "",
        out_subdir: str = "labs",
        image_reader=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.project_root = project_root
        self.query = query
        self.out_subdir = out_subdir
        self.image_reader = image_reader

    def request_cancel(self) -> None:
        self.requestInterruption()

    def run(self) -> None:
        try:
            result = dump_lab_scripts(
                self.pdf_path,
                self.project_root,
                out_subdir=self.out_subdir,
                vision_reader=self.image_reader,
            )
            if self.isInterruptionRequested():
                return
            self.finished_ok.emit(format_lab_dump_reply(result))
        except Exception as exc:  # noqa: BLE001
            self.finished_err.emit(f"실습 스크립트 추출 실패 ({type(exc).__name__}): {exc}")
