"""File extraction stays off the Qt GUI thread."""
from PyQt6.QtCore import QThread, pyqtSignal
from iris.runtime.attachment_context import prepare_attachments


class AttachmentWorker(QThread):
    prepared = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, paths, *, workspace_root="", query="", store=None, image_reader=None, parent=None):
        super().__init__(parent)
        self.paths = tuple(paths)
        self.workspace_root = workspace_root
        self.query = query
        self.store = store
        self.image_reader = image_reader

    def request_cancel(self):
        self.requestInterruption()

    def run(self):
        from iris.runtime.attachment_context import bind_chat_image_reader, reset_chat_image_reader

        token = bind_chat_image_reader(self.image_reader)
        try:
            result = prepare_attachments(self.paths, workspace_root=self.workspace_root, query=self.query,
                                         cancelled=self.isInterruptionRequested, store=self.store)
            if not self.isInterruptionRequested():
                self.prepared.emit(result)
        except Exception as exc:
            self.failed.emit(f"첨부 파일 처리 실패 ({type(exc).__name__}).")
        finally:
            reset_chat_image_reader(token)
