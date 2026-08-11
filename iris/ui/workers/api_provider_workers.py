"""커스텀 API probe / OpenAI 호환 채팅 워커."""

from __future__ import annotations

from urllib.parse import urlparse

from PyQt6.QtCore import QThread, pyqtSignal

from iris.infrastructure import openai_compat_client as oai
from iris.storage.api_providers import ApiProvider


def _host_label(base_url: str) -> str:
    try:
        return urlparse(oai.normalize_base_url(base_url)).netloc or base_url
    except Exception:
        return base_url or "api"


class ApiProbeWorker(QThread):
    """연결 테스트 — (provider_id, ok, detail, models)."""

    finished_probe = pyqtSignal(str, bool, str, object)  # id, ok, detail, models list

    def __init__(self, provider: ApiProvider, parent=None) -> None:
        super().__init__(parent)
        self._provider = provider

    def run(self) -> None:
        p = self._provider
        model_hint = p.models[0] if p.models else ""
        try:
            ok, detail, models = oai.probe(
                p.base_url,
                p.api_key,
                model=model_hint,
            )
            # 수동 목록이 있으면 병합
            merged = list(models)
            for m in p.models:
                if m not in merged:
                    merged.append(m)
            if not merged and p.models:
                merged = list(p.models)
            self.finished_probe.emit(p.id, ok, detail, merged)
        except Exception as exc:
            self.finished_probe.emit(p.id, False, str(exc)[:300], [])


class OpenAICompatChatWorker(QThread):
    """직접 호출 채팅 스트림 — Ollama/Hermes 워커와 동일 시그널 계약."""

    connecting = pyqtSignal(str, str)  # model, host
    thinking_started = pyqtSignal()
    thinking_chunk = pyqtSignal(str)
    thinking_done = pyqtSignal()
    content_chunk = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        *,
        display_model: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._messages = messages
        self._display = display_model or model
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        host = _host_label(self._base_url)
        self.connecting.emit(self._display, host)
        parts: list[str] = []
        try:
            for ev in oai.stream_chat(
                self._base_url,
                self._api_key,
                self._model,
                self._messages,
            ):
                if self._cancel:
                    break
                ch = ev.get("content")
                if isinstance(ch, str) and ch:
                    parts.append(ch)
                    self.content_chunk.emit(ch)
                if ev.get("done"):
                    break
            self.finished_ok.emit("".join(parts))
        except Exception as exc:
            self.failed.emit(str(exc))
