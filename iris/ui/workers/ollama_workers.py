"""백그라운드 Ollama 워커."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6.QtCore import QThread, pyqtSignal

from iris.infrastructure.ollama_usage import poll_ollama_cloud_signed_in

from iris.infrastructure.ollama_client import OllamaClient, OllamaModelInfo, host_label_for_model
from iris.runtime.stream_usage import TokenUsage
from iris.ui.workers.chat_attempt import (
    ChatAttempt,
    decide_fallback,
    normalize_attempts,
    route_target_for_attempt,
)
from iris.system.ollama_server import ensure_ollama_running, is_ollama_running

# ponytail: 클라우드 프로브가 네트워크에 묶여 인트로/상태줄을 영원히 잡지 않게.
_MODEL_LIST_TIMEOUT_S = 18.0


class OllamaModelListWorker(QThread):
    """모델 목록 조회 — 서버 미기동 시 자동 기동."""

    finished_ok = pyqtSignal(object)  # list[OllamaModelInfo]
    failed = pyqtSignal(str)
    notice = pyqtSignal(str)  # 서버 기동 등 상태 메시지

    def __init__(
        self,
        base_url: str,
        parent=None,
        *,
        probe_cloud: bool = True,
        timeout_s: float = _MODEL_LIST_TIMEOUT_S,
    ) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._probe_cloud = probe_cloud
        self._timeout_s = float(timeout_s)

    def run(self) -> None:
        # ponytail: StartupHealthWorker와 같이 daemon+join — urlopen hang에 전역 묶임 금지.
        box: dict[str, object] = {"models": None, "err": None, "done": False}

        def work() -> None:
            try:
                if not is_ollama_running(self._base_url):
                    self.notice.emit("Ollama 서버가 꺼져 있습니다. 서버를 시작합니다…")
                    if ensure_ollama_running(self._base_url):
                        self.notice.emit("Ollama 서버 시작됨.")
                    else:
                        box["err"] = (
                            "Ollama 서버를 시작할 수 없습니다. "
                            "Ollama가 설치되어 있는지 확인하세요."
                        )
                        return
                client = OllamaClient(self._base_url)
                box["models"] = client.list_chat_models(probe_cloud=self._probe_cloud)
            except Exception as e:
                box["err"] = str(e)
            finally:
                box["done"] = True

        t = threading.Thread(target=work, name="iris-ollama-model-list", daemon=True)
        t.start()
        t.join(timeout=self._timeout_s)
        if box["done"]:
            err = box["err"]
            if err:
                self.failed.emit(str(err))
                return
            models = box["models"]
            self.finished_ok.emit(models if isinstance(models, list) else [])
            return
        # 타임아웃 — 클라우드 프로브였으면 로컬만 짧게 재시도
        if self._probe_cloud:
            try:
                self.notice.emit("클라우드 모델 확인 시간 초과 — 로컬 목록만 사용")
                client = OllamaClient(self._base_url)
                self.finished_ok.emit(client.list_chat_models(probe_cloud=False))
                return
            except Exception as e:
                self.failed.emit(f"모델 목록 시간 초과: {e}")
                return
        self.failed.emit("모델 목록 조회 시간 초과")


class OllamaLoginWatchWorker(QThread):
    """로그인 클릭 뒤 데몬 /api/me 가 켜질 때까지 백그라운드에서 기다린다."""

    signed_in = pyqtSignal()

    def __init__(
        self,
        parent=None,
        *,
        timeout_sec: float = 180.0,
        interval_sec: float = 2.0,
    ) -> None:
        super().__init__(parent)
        self._timeout_sec = float(timeout_sec)
        self._interval_sec = float(interval_sec)

    def run(self) -> None:
        ok = poll_ollama_cloud_signed_in(
            timeout_sec=self._timeout_sec,
            interval_sec=self._interval_sec,
            stop=self.isInterruptionRequested,
        )
        if ok and not self.isInterruptionRequested():
            self.signed_in.emit()


def start_ollama_login_watch(parent, on_signed_in) -> OllamaLoginWatchWorker:
    """같은 parent의 이전 감시를 끊고 새로 시작한다."""
    stop_ollama_login_watch(parent)
    worker = OllamaLoginWatchWorker(parent)
    worker.signed_in.connect(on_signed_in)
    parent._ollama_login_watch = worker
    worker.start()
    return worker


def stop_ollama_login_watch(parent) -> None:
    worker = getattr(parent, "_ollama_login_watch", None)
    if worker is not None:
        try:
            worker.signed_in.disconnect()
        except (TypeError, RuntimeError):
            pass
        if worker.isRunning():
            worker.requestInterruption()
    parent._ollama_login_watch = None


class OllamaModelsVerifyWorker(QThread):
    """로컬+클라우드 모델을 실측해 사용 불가 모델을 가린다. API 「모델 정리」와 같은 역할."""

    verified_one = pyqtSignal(str, str, str)  # model, state, tool_support
    progress = pyqtSignal(int, int, int)  # done, total, usable
    finished_all = pyqtSignal(object, int, int, bool)  # models, usable, total, complete

    def __init__(self, base_url: str, parent=None) -> None:
        super().__init__(parent)
        self._base_url = base_url

    def run(self) -> None:
        # ponytail: 클라우드 카탈로그가 크면 순차 25초×N은 너무 김. 6병렬.
        # 천장: 동시 6건. 더 필요하면 워커 수만 올린다.
        client = OllamaClient(self._base_url)
        try:
            models = client.list_chat_models(probe_cloud=False)
        except Exception:
            self.finished_all.emit([], 0, 0, False)
            return
        usable = 0
        done = 0
        total = len(models)
        if not models:
            self.finished_all.emit([], 0, 0, True)
            return
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {}
            for model in models:
                if self.isInterruptionRequested():
                    break
                futures[pool.submit(client.classify_model, model.name)] = model.name
            for fut in as_completed(futures):
                name = futures[fut]
                try:
                    state, tool = fut.result()
                except Exception:
                    state, tool = "unverified", "unknown"
                if state != "unavailable":
                    usable += 1
                done += 1
                self.verified_one.emit(name, state, tool)
                self.progress.emit(done, total, usable)
        self.finished_all.emit(models, usable, total, done == total)


class OllamaChatWorker(QThread):
    """채팅 스트림 — thinking / content 분리 시그널.

    후보를 여러 개 받으면 앞의 것이 실패했을 때 다음 후보로 넘어간다
    (`iris.runtime.model_failover` 의 분류·백오프를 그대로 쓴다).
    """

    connecting = pyqtSignal(str, str)  # model, host
    thinking_started = pyqtSignal()
    thinking_chunk = pyqtSignal(str)
    thinking_done = pyqtSignal()
    content_chunk = pyqtSignal(str)
    finished_ok = pyqtSignal(str)  # full assistant content
    failed = pyqtSignal(str)
    # 모델을 갈아탔다 — (새 모델, 사유, 이미 흘려보낸 content 가 있었는지)
    switched = pyqtSignal(str, str, bool)
    cooled = pyqtSignal(object, float)
    usage = pyqtSignal(int, int)

    def __init__(
        self,
        base_url: str,
        model: str,
        messages: list[dict[str, str]],
        *,
        think: bool = True,
        attempts: list[ChatAttempt] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._model = model
        self._messages = messages
        self._think = think
        self._cancel = False
        self._attempts = normalize_attempts(attempts, model=model, messages=messages)
        self._final_model = self._attempts[0].model

    @property
    def final_model(self) -> str:
        """실제로 답을 만들어낸 모델. 전환이 없었으면 처음 것 그대로."""
        return self._final_model

    def request_cancel(self) -> None:
        self._cancel = True

    def _sleep_ms(self, delay_ms: int) -> None:
        """백오프 대기 — 취소가 들어오면 즉시 깬다."""
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
            self._final_model = attempt.model
            host = host_label_for_model(attempt.model, self._base_url)
            self.connecting.emit(attempt.model, host)

            content_parts: list[str] = []
            thinking_open = False
            done_reason = ""
            try:
                client = OllamaClient(self._base_url)
                for ev in client.stream_chat(attempt.model, attempt.messages, think=self._think):
                    if self._cancel:
                        break
                    token_usage = ev.get("usage")
                    if isinstance(token_usage, TokenUsage):
                        self.usage.emit(token_usage.tokens_in, token_usage.tokens_out)
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
                        done_reason = str(ev.get("done_reason") or "")
                        break
                if thinking_open:
                    self.thinking_done.emit()
                if done_reason.casefold() == "length":
                    raise RuntimeError(
                        "Ollama 응답이 모델 컨텍스트 한도에서 종료되었습니다. "
                        "새 채팅에서 요청을 나누거나 더 큰 컨텍스트 모델을 선택하세요."
                    )
                self.finished_ok.emit("".join(content_parts))
                return
            except Exception as e:  # noqa: BLE001
                if thinking_open:
                    self.thinking_done.emit()
                last_error = str(e)

            if self._cancel:
                break

            step = decide_fallback(last_error, index)
            if step is None:
                # 원인을 모르는 실패로 모델을 바꾸면 사용자만 헷갈린다.
                break
            if step.cool_until_monotonic is not None:
                self.cooled.emit(
                    route_target_for_attempt(attempt, "ollama"),
                    step.cool_until_monotonic,
                )
            if index + 1 >= len(self._attempts):
                break

            self._sleep_ms(step.delay_ms)
            if self._cancel:
                break
            nxt = self._attempts[index + 1]
            reason = nxt.reason_hint or step.reason
            # 이미 화면에 글자가 나갔으면 창은 그걸 지우고 다시 받아야 한다.
            self.switched.emit(nxt.model, reason, bool(content_parts))

        if not self._cancel:
            self.failed.emit(last_error or "모델 응답 실패")


__all__ = [
    "ChatAttempt",
    "OllamaChatWorker",
    "OllamaLoginWatchWorker",
    "OllamaModelListWorker",
    "start_ollama_login_watch",
    "stop_ollama_login_watch",
]
