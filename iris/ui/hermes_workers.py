"""백그라운드 Hermes API 워커."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from iris.infrastructure.hermes_client import HermesClient, host_label_for_hermes


class HermesHealthWorker(QThread):
    """Hermes gateway 헬스 체크."""

    finished_ok = pyqtSignal(bool)
    failed = pyqtSignal(str)

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str = "",
        command: str = "hermes",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._api_key = api_key
        self._command = command

    def run(self) -> None:
        try:
            client = HermesClient(
                self._base_url,
                api_key=self._api_key,
                command=self._command,
            )
            self.finished_ok.emit(client.health_ok())
        except Exception as e:
            self.failed.emit(str(e))


class HermesModelSyncWorker(QThread):
    """Iris 모델 선택 → Hermes config 동기화."""

    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str = "",
        command: str = "hermes",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._model = model
        self._api_key = api_key
        self._command = command

    def run(self) -> None:
        try:
            client = HermesClient(
                self._base_url,
                api_key=self._api_key,
                command=self._command,
            )
            client.set_inference_model(self._model)
            self.finished_ok.emit()
        except Exception as e:
            self.failed.emit(str(e))


class HermesChatWorker(QThread):
    """Hermes API 채팅 스트림."""

    connecting = pyqtSignal(str, str)  # model, host
    tool_progress = pyqtSignal(str)
    content_chunk = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        base_url: str,
        model: str,
        messages: list[dict[str, str]],
        *,
        api_key: str = "",
        command: str = "hermes",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._model = model
        self._messages = messages
        self._api_key = api_key
        self._command = command
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        host = host_label_for_hermes(self._base_url)
        self.connecting.emit(self._model, host)
        content_parts: list[str] = []
        try:
            client = HermesClient(
                self._base_url,
                api_key=self._api_key,
                command=self._command,
            )
            client.set_inference_model(self._model)
            for ev in client.stream_chat(self._model, self._messages):
                if self._cancel:
                    break
                tool = ev.get("tool_progress")
                if isinstance(tool, str) and tool:
                    self.tool_progress.emit(tool)
                chunk = ev.get("content")
                if isinstance(chunk, str) and chunk:
                    content_parts.append(chunk)
                    self.content_chunk.emit(chunk)
                if ev.get("done"):
                    break
            self.finished_ok.emit("".join(content_parts))
        except Exception as e:
            self.failed.emit(str(e))
