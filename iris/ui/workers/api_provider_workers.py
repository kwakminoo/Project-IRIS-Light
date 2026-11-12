"""커스텀 API probe / OpenAI 호환 채팅 워커."""

from __future__ import annotations

from urllib.parse import urlparse

from PyQt6.QtCore import QThread, pyqtSignal

from iris.infrastructure import openai_compat_client as oai
from iris.runtime.stream_usage import TokenUsage
from iris.storage.api_providers import ApiProvider
from iris.ui.workers.chat_attempt import (
    ApiCall,
    ChatAttempt,
    decide_fallback,
    normalize_attempts,
    route_target_for_attempt,
)


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
    """직접 호출 채팅 스트림 — Ollama/Iris Agent 워커와 동일 시그널 계약."""

    connecting = pyqtSignal(str, str)  # model, host
    thinking_started = pyqtSignal()
    thinking_chunk = pyqtSignal(str)
    thinking_done = pyqtSignal()
    content_chunk = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    # (새 모델, 사유, 이미 흘려보낸 content 가 있었는지)
    switched = pyqtSignal(str, str, bool)
    cooled = pyqtSignal(object, float)
    usage = pyqtSignal(int, int)

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        *,
        display_model: str = "",
        auth_style: str = "bearer",
        attempts: list[ChatAttempt] | None = None,
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
        if not attempts:
            attempts = [
                ChatAttempt(
                    display_model or model,
                    messages,
                    label=display_model or model,
                    target=ApiCall(
                        base_url=base_url,
                        api_key=api_key,
                        model=model,
                        auth_style=auth_style,
                    ),
                )
            ]
        self._attempts = normalize_attempts(attempts, model=model, messages=messages)
        self._final_model = self._attempts[0].model

    @property
    def final_model(self) -> str:
        return self._final_model

    def request_cancel(self) -> None:
        self._cancel = True

    def _sleep_ms(self, delay_ms: int) -> None:
        waited = 0
        while waited < delay_ms and not self._cancel:
            step = min(100, delay_ms - waited)
            self.msleep(step)
            waited += step

    def run(self) -> None:
        last_error = ""
        for index, attempt in enumerate(self._attempts):
            if self._cancel:
                break
            call = attempt.target
            if call is None:
                last_error = f"{attempt.model}: 호출 정보 없음"
                continue
            self._final_model = attempt.model
            self.connecting.emit(attempt.label, _host_label(call.base_url))

            parts: list[str] = []
            try:
                for ev in oai.stream_chat(
                    call.base_url,
                    call.api_key,
                    call.model,
                    attempt.messages,
                    auth_style=call.auth_style,
                ):
                    if self._cancel:
                        break
                    token_usage = ev.get("usage")
                    if isinstance(token_usage, TokenUsage):
                        self.usage.emit(token_usage.tokens_in, token_usage.tokens_out)
                    ch = ev.get("content")
                    if isinstance(ch, str) and ch:
                        parts.append(ch)
                        self.content_chunk.emit(ch)
                    if ev.get("done"):
                        break
                self.finished_ok.emit("".join(parts))
                return
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)

            if self._cancel:
                break
            step = decide_fallback(last_error, index)
            if step is None:
                break
            if step.cool_until_monotonic is not None:
                self.cooled.emit(
                    route_target_for_attempt(attempt, "api"),
                    step.cool_until_monotonic,
                )
            if index + 1 >= len(self._attempts):
                break
            self._sleep_ms(step.delay_ms)
            if self._cancel:
                break
            nxt = self._attempts[index + 1]
            self.switched.emit(nxt.model, nxt.reason_hint or step.reason, bool(parts))

        if not self._cancel:
            self.failed.emit(last_error or "모델 응답 실패")
