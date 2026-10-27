"""백그라운드 Hermes API 워커."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from iris.engine import (
    CancelToken,
    ChatTranscript,
    ContentDelta,
    EngineError,
    EngineFailed,
    EngineReady,
    EngineSource,
    ExternalGateway,
    StatelessTurn,
    ToolProgress,
    TurnCancelled,
    TurnFailed,
    TurnFinished,
    shared_engine,
)
from iris.ui.workers.chat_attempt import (
    ChatAttempt,
    decide_fallback,
    normalize_attempts,
)
from iris.infrastructure.hermes_client import (
    HermesClient,
    HermesInferenceTarget,
    host_label_for_hermes,
    resolve_hermes_inference,
)
from iris.system.hermes_gateway import (
    ensure_hermes_gateway_running,
    ensure_hermes_provider_config,
    is_hermes_gateway_running,
    restart_hermes_gateway,
    verify_iris_mcp_tools,
)
from iris.system.hermes_iris_control_sync import sync_iris_control


def _engine_source() -> EngineSource:
    """Same source the process singleton parsed. Do not start both modes."""
    return shared_engine().source


class HermesHealthWorker(QThread):
    """Engine ready check. ExternalGateway keeps the :8642 health path."""

    finished_ok = pyqtSignal(bool)
    failed = pyqtSignal(str)
    notice = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

    def run(self) -> None:
        try:
            source = _engine_source()
            if isinstance(source, ExternalGateway):
                self._run_external(source)
                return
            result = shared_engine().ensure_ready()
            if isinstance(result, EngineFailed):
                self.failed.emit(result.user_message)
                return
            if isinstance(result, EngineReady) and result.summary:
                self.notice.emit(result.summary)
            self.finished_ok.emit(True)
        except Exception as e:
            self.failed.emit(str(e))

    def _run_external(self, source: ExternalGateway) -> None:
        base_url = source.base_url
        api_key = source.api_key
        command = "hermes"
        ensure_hermes_provider_config()
        try:
            report = sync_iris_control(reconnect_gateway=True)
            self.notice.emit(report.summary_line())
            for msg in report.messages[:6]:
                if msg and msg not in report.summary_line():
                    self.notice.emit(msg)
            if report.mcp_fail_count:
                self.notice.emit(
                    f"MCP 점검 실패 {report.mcp_fail_count}개 — 설정·경로를 확인하세요."
                )

            if report.needs_gateway_reload:
                self.notice.emit("MCP 연결 — Hermes gateway 완전 재기동…")
                ok = restart_hermes_gateway(
                    base_url,
                    api_key=api_key,
                    command=command,
                    wait_sec=60.0,
                )
                if ok:
                    mcp_ok, mcp_detail = verify_iris_mcp_tools(command=command)
                    if mcp_ok:
                        self.notice.emit(f"Hermes MCP 재연결 완료 — {mcp_detail}")
                    else:
                        self.notice.emit(
                            f"Gateway는 떴지만 MCP 검증 실패: {mcp_detail}"
                        )
                        ok = False
                else:
                    from iris.system.hermes_gateway import (
                        get_last_gateway_diagnosis,
                        hermes_runtime_report,
                    )

                    report = hermes_runtime_report(command=command)
                    diag = get_last_gateway_diagnosis()
                    why = diag.user_message() if diag is not None else report
                    self.notice.emit(why[:800])
                self.finished_ok.emit(ok)
                return

            gateway_up = is_hermes_gateway_running(base_url, api_key=api_key)
            if gateway_up:
                mcp_ok, mcp_detail = verify_iris_mcp_tools(command=command)
                if mcp_ok:
                    self.notice.emit(f"MCP 유지 확인 — {mcp_detail}")
                    self.finished_ok.emit(True)
                    return
                self.notice.emit(f"MCP 미연결({mcp_detail}) — gateway 재기동…")
                ok = restart_hermes_gateway(
                    base_url,
                    api_key=api_key,
                    command=command,
                    wait_sec=60.0,
                )
                if ok:
                    mcp_ok2, mcp_detail2 = verify_iris_mcp_tools(command=command)
                    self.notice.emit(
                        f"Hermes MCP 재연결: {mcp_detail2}"
                        if mcp_ok2
                        else f"MCP 재검증 실패: {mcp_detail2}"
                    )
                    ok = mcp_ok2
                else:
                    from iris.system.hermes_gateway import (
                        get_last_gateway_diagnosis,
                        hermes_runtime_report,
                    )

                    report = hermes_runtime_report(command=command)
                    diag = get_last_gateway_diagnosis()
                    self.notice.emit(
                        (diag.user_message() if diag is not None else report)[:800]
                    )
                self.finished_ok.emit(ok)
                return
        except Exception as sync_exc:  # noqa: BLE001
            self.notice.emit(f"Iris↔Hermes control sync skip: {str(sync_exc)[:120]}")

        if is_hermes_gateway_running(base_url, api_key=api_key):
            self.finished_ok.emit(True)
            return
        self.notice.emit("Hermes gateway가 꺼져 있습니다. 시작합니다…")
        ok = ensure_hermes_gateway_running(
            base_url,
            api_key=api_key,
            command=command,
        )
        if ok:
            mcp_ok, mcp_detail = verify_iris_mcp_tools(command=command)
            self.notice.emit(
                f"Hermes gateway 시작됨 — {mcp_detail}"
                if mcp_ok
                else f"Gateway 시작됐지만 MCP 실패: {mcp_detail}"
            )
            ok = mcp_ok
        else:
            from iris.system.hermes_gateway import get_last_gateway_diagnosis

            diag = get_last_gateway_diagnosis()
            if diag is not None:
                self.notice.emit(diag.user_message()[:400])
            else:
                self.notice.emit(
                    "Hermes gateway를 시작할 수 없습니다. "
                    "hermes 설치·포트 8642·로그(%LOCALAPPDATA%\\hermes\\logs\\iris-gateway)를 확인하세요."
                )
        self.finished_ok.emit(ok)


class HermesControlSyncWorker(QThread):
    """설정창/수동 동기화 — UI 스레드에서 sync/restart 금지(데드락·프리즈)."""

    progress = pyqtSignal(str)
    finished_ok = pyqtSignal(bool, str)  # ok, summary

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
        lines: list[str] = []
        try:
            self.progress.emit("상태: MCP/스킬 동기화 중…")
            report = sync_iris_control(reconnect_gateway=True)
            lines.append(report.summary_line())
            shown = list(report.messages[:8])
            for msg in report.messages:
                if "missing" in msg and msg not in shown:
                    shown.append(msg)
            lines.extend(shown)
            for s in report.mcp_servers[:8]:
                mark = "OK" if s.get("ok") else "FAIL"
                if not s.get("enabled", True):
                    mark = "OFF"
                lines.append(f"  [{mark}] {s.get('name')}: {s.get('detail')}")
            if report.errors:
                lines.append("오류: " + "; ".join(report.errors[:2]))

            self.progress.emit("상태: Hermes gateway 재기동…")
            ok = restart_hermes_gateway(
                self._base_url,
                api_key=self._api_key,
                command=self._command,
                wait_sec=60.0,
            )
            if not ok:
                from iris.system.hermes_gateway import (
                    get_last_gateway_diagnosis,
                    hermes_runtime_report,
                )

                runtime = hermes_runtime_report(command=self._command)
                diag = get_last_gateway_diagnosis()
                why = diag.user_message() if diag is not None else runtime
                lines.insert(0, why)
                if diag is not None and runtime not in why:
                    lines.insert(1, runtime)
                self.finished_ok.emit(False, "\n".join(lines))
                return

            mcp_ok, mcp_detail = verify_iris_mcp_tools(command=self._command)
            lines.append(mcp_detail)
            self.finished_ok.emit(
                bool(report.ok and mcp_ok and report.mcp_fail_count == 0),
                "\n".join(lines),
            )
        except Exception as exc:  # noqa: BLE001
            self.finished_ok.emit(False, f"상태: 실패 — {exc}")


class HermesModelSyncWorker(QThread):
    """Iris model sync. ExternalGateway keeps HTTP. InternalSidecar skips :8642."""

    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str = "",
        command: str = "hermes",
        target: HermesInferenceTarget | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._model = model
        self._api_key = api_key
        self._command = command
        self._target = target

    def run(self) -> None:
        try:
            if not isinstance(_engine_source(), ExternalGateway):
                self.finished_ok.emit()
                return
            client = HermesClient(
                self._base_url,
                api_key=self._api_key,
                command=self._command,
            )
            if self._target is not None:
                client.set_inference_model(self._target.model, target=self._target)
            else:
                client.set_inference_model(self._model)
            self.finished_ok.emit()
        except Exception as e:
            self.failed.emit(str(e))


class HermesChatWorker(QThread):
    """Chat stream. InternalSidecar uses shared_engine. ExternalGateway uses HTTP."""

    connecting = pyqtSignal(str, str)  # model, host
    tool_progress = pyqtSignal(str)
    content_chunk = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)
    # (새 모델, 사유, 이미 흘려보낸 content 가 있었는지)
    switched = pyqtSignal(str, str, bool)

    def __init__(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        target: HermesInferenceTarget | None = None,
        attempts: list[ChatAttempt] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._model = model
        self._messages = messages
        self._target = target
        self._cancel = False
        self._cancel_token = CancelToken()
        if not attempts:
            attempts = [
                ChatAttempt(
                    model,
                    messages,
                    label=(target.label if target is not None else model),
                    target=target,
                )
            ]
        self._attempts = normalize_attempts(attempts, model=model, messages=messages)
        self._final_model = self._attempts[0].model

    @property
    def final_model(self) -> str:
        """실제로 답을 만들어낸 모델."""
        return self._final_model

    def request_cancel(self) -> None:
        self._cancel = True
        self._cancel_token.cancel()

    def _sleep_ms(self, delay_ms: int) -> None:
        waited = 0
        while waited < delay_ms and not self._cancel:
            step = min(100, delay_ms - waited)
            self.msleep(step)
            waited += step

    def _resolve_target(self, attempt: ChatAttempt) -> HermesInferenceTarget:
        target = attempt.target
        if isinstance(target, HermesInferenceTarget):
            return target
        if isinstance(self._target, HermesInferenceTarget):
            return self._target
        model = str(getattr(target, "model", "") or "") if target is not None else ""
        provider = str(getattr(target, "provider", "") or "") if target is not None else ""
        return HermesInferenceTarget(
            model=model or attempt.model,
            provider=provider,
            display=attempt.label,
        )

    def _ensure_gateway(self, source: ExternalGateway) -> str:
        """게이트웨이 기동 보장. 실패하면 사용자에게 보일 문구를 돌려준다."""
        if is_hermes_gateway_running(source.base_url, api_key=source.api_key):
            return ""
        self.tool_progress.emit("Hermes gateway 기동 중…")
        if ensure_hermes_gateway_running(
            source.base_url, api_key=source.api_key, command="hermes"
        ):
            return ""
        from iris.system.hermes_gateway import get_last_gateway_diagnosis

        diag = get_last_gateway_diagnosis()
        if diag is not None:
            return diag.user_message()[:400]
        return (
            "Hermes gateway를 시작할 수 없습니다. "
            r"설치·포트·%LOCALAPPDATA%\hermes\logs\iris-gateway 로그를 확인하세요."
        )

    def run(self) -> None:
        try:
            source = _engine_source()
            if isinstance(source, ExternalGateway):
                self._run_external(source)
                return
            self._run_internal()
        except Exception as e:
            self.failed.emit(str(e))

    def _run_internal(self) -> None:
        last_error = ""
        for index, attempt in enumerate(self._attempts):
            if self._cancel_token.cancelled():
                break
            self._final_model = attempt.model
            target = self._resolve_target(attempt)
            self.connecting.emit(target.label or attempt.label, "engine")
            content_parts: list[str] = []
            try:
                turn = StatelessTurn(
                    transcript=ChatTranscript.parse(attempt.messages),
                    model=target,
                    cancel=self._cancel_token,
                )
            except EngineError as exc:
                last_error = exc.user_message or exc.detail
                break
            finished = False
            fallback_error = last_error
            for event in shared_engine().run_turn(turn):
                if isinstance(event, ContentDelta):
                    if event.text:
                        content_parts.append(event.text)
                        self.content_chunk.emit(event.text)
                elif isinstance(event, ToolProgress):
                    if event.label:
                        self.tool_progress.emit(event.label)
                elif isinstance(event, TurnFinished):
                    self.finished_ok.emit("".join(content_parts) or event.text)
                    finished = True
                    break
                elif isinstance(event, TurnCancelled):
                    return
                elif isinstance(event, TurnFailed):
                    last_error = event.error.user_message or event.error.detail
                    fallback_error = event.error.detail or last_error
                    break
            if finished:
                return
            has_next = index + 1 < len(self._attempts)
            if self._cancel_token.cancelled() or not has_next:
                break
            step = decide_fallback(fallback_error, index)
            if step is None:
                break
            self._sleep_ms(step.delay_ms)
            if self._cancel_token.cancelled():
                break
            nxt = self._attempts[index + 1]
            self.switched.emit(
                nxt.model, nxt.reason_hint or step.reason, bool(content_parts)
            )
        if not self._cancel_token.cancelled():
            self.failed.emit(last_error or "모델 응답 실패")

    def _run_external(self, source: ExternalGateway) -> None:
        gateway_error = self._ensure_gateway(source)
        if gateway_error:
            self.failed.emit(gateway_error)
            return

        host = host_label_for_hermes(source.base_url)
        last_error = ""
        for index, attempt in enumerate(self._attempts):
            if self._cancel:
                break
            self._final_model = attempt.model
            target = attempt.target
            display = target.label if target is not None else attempt.label
            self.connecting.emit(display, host)

            content_parts: list[str] = []
            try:
                client = HermesClient(
                    source.base_url, api_key=source.api_key, command="hermes"
                )
                if target is not None:
                    stream_model = target.model
                    provider = str(getattr(target, "provider", "") or "").strip()
                else:
                    stream_model = attempt.model
                    provider = ""
                stream_kwargs = {"provider": provider} if provider else {}
                for ev in client.stream_chat(stream_model, attempt.messages, **stream_kwargs):
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
                return
            except Exception as e:  # noqa: BLE001
                last_error = str(e)

            has_next = index + 1 < len(self._attempts)
            if self._cancel or not has_next:
                break
            step = decide_fallback(last_error, index)
            if step is None:
                break
            self._sleep_ms(step.delay_ms)
            if self._cancel:
                break
            nxt = self._attempts[index + 1]
            self.switched.emit(
                nxt.model, nxt.reason_hint or step.reason, bool(content_parts)
            )

        if not self._cancel:
            self.failed.emit(last_error or "모델 응답 실패")


# re-export for callers that resolve targets in UI thread
__all__ = [
    "HermesHealthWorker",
    "HermesControlSyncWorker",
    "HermesModelSyncWorker",
    "HermesChatWorker",
    "ChatAttempt",
    "HermesInferenceTarget",
    "resolve_hermes_inference",
]
