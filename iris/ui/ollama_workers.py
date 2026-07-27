"""백그라운드 Ollama 워커."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from iris.infrastructure.ollama_client import OllamaClient, OllamaModelInfo, host_label_for_model
from iris.system.ollama_server import ensure_ollama_running, is_ollama_running


class OllamaModelListWorker(QThread):
    """모델 목록 조회 — 서버 미기동 시 자동 기동."""

    finished_ok = pyqtSignal(object)  # list[OllamaModelInfo]
    failed = pyqtSignal(str)
    notice = pyqtSignal(str)  # 서버 기동 등 상태 메시지

    def __init__(self, base_url: str, parent=None) -> None:
        super().__init__(parent)
        self._base_url = base_url

    def run(self) -> None:
        try:
            if not is_ollama_running(self._base_url):
                self.notice.emit("Ollama 서버가 꺼져 있습니다. 서버를 시작합니다…")
                if ensure_ollama_running(self._base_url):
                    self.notice.emit("Ollama 서버 시작됨.")
                else:
                    self.failed.emit(
                        "Ollama 서버를 시작할 수 없습니다. Ollama가 설치되어 있는지 확인하세요."
                    )
                    return
            client = OllamaClient(self._base_url)
            models = client.list_chat_models(probe_cloud=True)
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
