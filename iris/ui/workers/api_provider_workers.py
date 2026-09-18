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
    """연결 테스트 — (provider_id, oai.ProbeResult)."""

    finished_probe = pyqtSignal(str, object)

    def __init__(self, provider: ApiProvider, parent=None) -> None:
        super().__init__(parent)
        self._provider = provider

    def run(self) -> None:
        p = self._provider
        model_hint = p.models[0] if p.models else ""
        try:
            result = oai.probe(p.base_url, p.api_key, model=model_hint)
        except Exception as exc:
            result = oai.ProbeResult("error", detail=str(exc)[:300])
        self.finished_probe.emit(p.id, result)


class ApiModelVerifyWorker(QThread):
    """모델 1건 실측 — (provider_id, model, state, tool_support, detail)."""

    finished_verify = pyqtSignal(str, str, str, str, str)

    def __init__(self, provider: ApiProvider, model: str, parent=None) -> None:
        super().__init__(parent)
        self._provider = provider
        self._model = model

    def run(self) -> None:
        from iris.infrastructure.api_model_meta import verify_model

        p = self._provider
        try:
            state, tools, detail = verify_model(
                p.base_url, p.api_key, self._model, auth_style=p.auth_style
            )
        except Exception as exc:  # noqa: BLE001 — 판정 불가는 미확정으로 남김
            state, tools, detail = "unverified", "unknown", str(exc)[:200]
        self.finished_verify.emit(p.id, self._model, state, tools, detail)


class ApiModelsVerifyWorker(QThread):
    """제공자의 모든 모델을 순차 실측 — 목록 정리용. 중간 취소 가능."""

    verified_one = pyqtSignal(str, str, str, str)  # provider_id, model, state, tool_support
    progress = pyqtSignal(int, int, int)  # done, total, usable
    finished_all = pyqtSignal(str, int, int)  # provider_id, usable, total

    def __init__(self, provider: ApiProvider, parent=None) -> None:
        super().__init__(parent)
        self._provider = provider

    def run(self) -> None:
        from iris.infrastructure.api_model_meta import verify_model

        p = self._provider
        models = list(p.models)
        usable = 0
        for i, model in enumerate(models, start=1):
            if self.isInterruptionRequested():
                break
            try:
                state, tools, _detail = verify_model(
                    p.base_url, p.api_key, model, auth_style=p.auth_style
                )
            except Exception:  # noqa: BLE001 — 판정 불가는 미확정
                state, tools = "unverified", "unknown"
            if state != "unavailable":
                usable += 1
            self.verified_one.emit(p.id, model, state, tools)
            self.progress.emit(i, len(models), usable)
        self.finished_all.emit(p.id, usable, len(models))


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
        auth_style: str = "bearer",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._api_key = api_key
        self._auth_style = auth_style
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
                auth_style=self._auth_style,
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
