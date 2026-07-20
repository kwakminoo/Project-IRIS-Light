"""백그라운드 Ollama 워커."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from iris.infrastructure.ollama_client import OllamaClient, OllamaModelInfo, host_label_for_model


class OllamaModelListWorker(QThread):
    """모델 목록 조회."""

    finished_ok = pyqtSignal(object)  # list[OllamaModelInfo]
    failed = pyqtSignal(str)

    def __init__(self, base_url: str, parent=None) -> None:
        super().__init__(parent)
        self._base_url = base_url

    def run(self) -> None:
        try:
            client = OllamaClient(self._base_url)
            models = client.list_free_cloud_models(probe=True)
            self.finished_ok.emit(models)
        except Exception as e:
            self.failed.emit(str(e))


class OllamaChatWorker(QThread):
    """채팅 스트림 — thinking / content 분리 시그널."""

    connecting = pyqtSignal(str, str)  # model, host
    thinking_started = pyqtSignal()
    thinking_chunk = pyqtSignal(str)
    thinking_done = pyqtSignal()
    content_chunk = pyqtSignal(str)
    finished_ok = pyqtSignal(str)  # full assistant content
    failed = pyqtSignal(str)

    def __init__(
        self,
        base_url: str,
        model: str,
        messages: list[dict[str, str]],
        *,
        think: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._model = model
        self._messages = messages
        self._think = think
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        host = host_label_for_model(self._model, self._base_url)
        self.connecting.emit(self._model, host)
        content_parts: list[str] = []
        thinking_open = False
        try:
            client = OllamaClient(self._base_url)
            for ev in client.stream_chat(self._model, self._messages, think=self._think):
                if self._cancel:
                    break
                th = ev.get("thinking")
                if isinstance(th, str) and th:
                    if not thinking_open:
                        thinking_open = True
                        self.thinking_started.emit()
                    self.thinking_chunk.emit(th)
                ch = ev.get("content")
                if isinstance(ch, str) and ch:
                    if thinking_open:
                        thinking_open = False
                        self.thinking_done.emit()
                    content_parts.append(ch)
                    self.content_chunk.emit(ch)
                if ev.get("done"):
                    break
            if thinking_open:
                self.thinking_done.emit()
            self.finished_ok.emit("".join(content_parts))
        except Exception as e:
            if thinking_open:
                self.thinking_done.emit()
            self.failed.emit(str(e))
