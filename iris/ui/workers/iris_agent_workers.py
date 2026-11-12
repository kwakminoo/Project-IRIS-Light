"""백그라운드 Iris Agent 워커."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from iris.engine import (
    AppUiOfferEvent,
    CancelToken,
    ChatTranscript,
    ContentDelta,
    EngineError,
    EngineFailed,
    EngineReady,
    EngineSource,
    ReasoningDelta,
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
    route_target_for_attempt,
)
from iris.infrastructure.iris_agent_client import (
    IrisAgentInferenceTarget,
    resolve_hermes_inference,
    resolve_iris_agent_inference,
)
from iris.infrastructure.speak_capability import current_speak_surface
from iris.system.iris_agent_gateway import (
    restart_hermes_gateway,
    verify_iris_mcp_tools,
)
from iris.system.iris_agent_control_sync import sync_iris_control

from iris.infrastructure.agent_runtime import (
    AGENT_LOOP_FAILED_PREFIX,
    AGENT_LOOP_PROPAGATE_BASE,
    AgentLoopStandinResult,
    attach_agent_loop_worker,
    ensure_agent_loop_handle,
    ensure_agent_loop_no_console,
    format_agent_loop_failure,
    replace_agent_loop_worker,
    reset_agent_loop,
    run_agent_loop_standin,
)
from iris.infrastructure.agent_tool_registry import speak_invoke_agent_tool
from iris.ui.workers.agent_ui_slot import safe_agent_ui_slot

# Phase 5 Prove 1 — worker → UI bridge is these signals only (no sync UI calls).
IRIS_AGENT_LOOP_UI_SIGNALS = frozenset({"finished_ok", "failed"})

_log = logging.getLogger(__name__)
_WATCH_LOG = Path.home() / ".iris-light" / "logs" / "turn_end_watch.log"


def _engine_source() -> EngineSource:
    """Same source the process singleton parsed. Product is InternalSidecar only."""
    return shared_engine().source


def _watch_trace(msg: str) -> None:
    try:
        _WATCH_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _WATCH_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"pid={os.getpid()} worker {msg}\n")
    except Exception:
        pass


def prove1_ui_abort_if_uncaught() -> None:
    """Intentional raise for Prove 1. Must never be a live MainWindow slot."""
    raise RuntimeError(
        "phase5-prove1: would abort Iris if uncaught on the UI thread"
    )


class IrisAgentHealthWorker(QThread):
    """Engine ready check via InternalSidecar."""

    finished_ok = pyqtSignal(bool)
    failed = pyqtSignal(str)
    notice = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

    def run(self) -> None:
        try:
            source = _engine_source()
            result = shared_engine().ensure_ready()
            if isinstance(result, EngineFailed):
                self.failed.emit(result.user_message)
                return
            if isinstance(result, EngineReady) and result.summary:
                self.notice.emit(result.summary)
            try:
                report = sync_iris_control(
                    home=source.home,
                    reconnect_gateway=False,
                )
                self.notice.emit(report.summary_line())
            except Exception as sync_exc:  # noqa: BLE001
                self.notice.emit(
                    f"Iris↔engine control sync skip: {str(sync_exc)[:120]}"
                )
            self.finished_ok.emit(True)
        except Exception as e:
            self.failed.emit(str(e))


class IrisAgentControlSyncWorker(QThread):
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

            self.progress.emit("상태: Iris Agent gateway 재기동…")
            ok = restart_hermes_gateway(
                self._base_url,
                api_key=self._api_key,
                command=self._command,
                wait_sec=60.0,
            )
            if not ok:
                from iris.system.iris_agent_gateway import (
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


class IrisAgentModelSyncWorker(QThread):
    """Iris model sync. Sidecar product path has no HTTP :8642 write."""

    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str = "",
        command: str = "hermes",
        target: IrisAgentInferenceTarget | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._model = model
        self._api_key = api_key
        self._command = command
        self._target = target

    def run(self) -> None:
        self.finished_ok.emit()


class IrisAgentChatWorker(QThread):
    """Chat stream via InternalSidecar / shared_engine."""
    connecting = pyqtSignal(str, str)  # model, host
    tool_progress = pyqtSignal(str)
    app_ui = pyqtSignal(str, str, str)  # title, html_path, resource_uri
    reasoning = pyqtSignal(str)
    content_chunk = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)
    # (새 모델, 사유, 이미 흘려보낸 content 가 있었는지)
    switched = pyqtSignal(str, str, bool)
    cooled = pyqtSignal(object, float)
    usage = pyqtSignal(int, int)

    def __init__(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        target: IrisAgentInferenceTarget | None = None,
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

    def _resolve_target(self, attempt: ChatAttempt) -> IrisAgentInferenceTarget:
        target = attempt.target
        if isinstance(target, IrisAgentInferenceTarget):
            return target
        if isinstance(self._target, IrisAgentInferenceTarget):
            return self._target
        model = str(getattr(target, "model", "") or "") if target is not None else ""
        provider = str(getattr(target, "provider", "") or "") if target is not None else ""
        return IrisAgentInferenceTarget(
            model=model or attempt.model,
            provider=provider,
            display=attempt.label,
        )

    @staticmethod
    def engine_tool_names() -> tuple[str, ...]:
        from iris.engine.types import IRIS_ENGINE_TOOLS
        from iris.infrastructure.speak_capability import default_speak_tools

        names = default_speak_tools().engine_names()
        assert names == IRIS_ENGINE_TOOLS
        return names

    @staticmethod
    def invoke_native_tool(
        name: str, args: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Speak/native registry invoke (Phase 2.3+). No MCP stdio / :8765."""
        return speak_invoke_agent_tool(name, args or {})

    def _wire_native_speak_tools(self) -> None:
        """Optional pre-turn native probes. Off by default — can block chat forever."""
        # Chat hot path must reach the engine even if invoke_native_tool hangs.
        flag = os.environ.get("IRIS_WIRE_NATIVE_SPEAK_TOOLS", "").strip().lower()
        if flag not in ("1", "true", "yes", "on"):
            return
        _ = self.engine_tool_names()
        # SpeakTools name wiki.list_notes; invoke via legacy iris.wiki.* alias.
        listed = self.invoke_native_tool("iris.wiki.list_notes", {"limit": 1})
        if not listed.get("ok"):
            self.tool_progress.emit(
                f"native wiki.list_notes skip: {listed.get('error') or listed}"
            )
        searched = self.invoke_native_tool(
            "iris.wiki.search", {"query": "iris", "limit": 1}
        )
        if not searched.get("ok"):
            self.tool_progress.emit(
                f"native wiki.search skip: {searched.get('error') or searched}"
            )
        mail = self.invoke_native_tool("iris.mail.list_accounts", {})
        if not mail.get("ok"):
            self.tool_progress.emit(
                f"native mail.list_accounts skip: {mail.get('error') or mail}"
            )
        cal = self.invoke_native_tool("iris.calendar.list_events", {})
        if not cal.get("ok"):
            self.tool_progress.emit(
                f"native calendar.list_events skip: {cal.get('error') or cal}"
            )

    def run(self) -> None:
        try:
            self._wire_native_speak_tools()
            source = _engine_source()
            _watch_trace(f"chat source={type(source).__name__}")
            self._run_internal()
        except Exception as e:
            _watch_trace(f"chat exc={e!r}")
            self.failed.emit(str(e))

    def _run_internal(self) -> None:
        last_error = ""
        shared = shared_engine()
        fork = getattr(shared, "fork", None)
        engine = fork() if callable(fork) else shared
        bind_tools = getattr(engine, "bind_tool_handler", None)
        if callable(bind_tools):
            bind_tools(self.invoke_native_tool)
        try:
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
                        speak_surface=current_speak_surface(),
                    )
                except EngineError as exc:
                    last_error = exc.user_message or exc.detail
                    break
                finished = False
                fallback_error = last_error
                for event in engine.run_turn(turn):
                    if isinstance(event, ContentDelta):
                        if event.text:
                            content_parts.append(event.text)
                            self.content_chunk.emit(event.text)
                    elif isinstance(event, ToolProgress):
                        if event.label:
                            self.tool_progress.emit(event.label)
                    elif isinstance(event, AppUiOfferEvent):
                        html = event.html_path or ""
                        uri = event.resource_uri or ""
                        if html or uri.lower().startswith("ui://"):
                            self.app_ui.emit(event.title or "앱", html, uri)
                    elif isinstance(event, ReasoningDelta):
                        if event.text:
                            self.reasoning.emit(event.text)
                    elif isinstance(event, TurnFinished):
                        text = "".join(content_parts) or event.text
                        _watch_trace(f"finished_ok text_len={len(text or '')}")
                        self.finished_ok.emit(text)
                        _watch_trace(f"finished_ok returned text_len={len(text or '')}")
                        finished = True
                        break
                    elif isinstance(event, TurnCancelled):
                        _watch_trace("cancelled")
                        return
                    elif isinstance(event, TurnFailed):
                        last_error = event.error.user_message or event.error.detail
                        fallback_error = event.error.detail or last_error
                        _watch_trace(f"turn_failed detail={fallback_error[:160]!r}")
                        break
                if finished:
                    return
                if self._cancel_token.cancelled():
                    break
                step = decide_fallback(fallback_error, index)
                if step is None:
                    break
                if step.cool_until_monotonic is not None:
                    self.cooled.emit(
                        route_target_for_attempt(attempt, "agent"),
                        step.cool_until_monotonic,
                    )
                if index + 1 >= len(self._attempts):
                    break
                self._sleep_ms(step.delay_ms)
                if self._cancel_token.cancelled():
                    break
                nxt = self._attempts[index + 1]
                self.switched.emit(
                    nxt.model, nxt.reason_hint or step.reason, bool(content_parts)
                )
            if not self._cancel_token.cancelled():
                self._emit_tool_choice_demotion(last_error)
                _watch_trace(f"failed.emit detail={(last_error or '모델 응답 실패')[:160]!r}")
                self.failed.emit(last_error or "모델 응답 실패")
        finally:
            if engine is not shared:
                engine.shutdown()

    def _emit_tool_choice_demotion(self, error: str, *, base_url: str = "") -> None:
        """Provider tool_choice 400 → that backend stays auto; one activity line; chat lives."""
        try:
            from iris.system.iris_agent_tool_choice import note_tool_choice_400

            line = note_tool_choice_400(
                error or "",
                provider=str(self._final_model or ""),
                base_url=base_url,
            )
            if line:
                self.tool_progress.emit(line)
        except Exception:  # noqa: BLE001
            pass

class IrisAgentLoopStandinWorker(QThread):
    """Phase 5 Prove 0?? ??in-process loop stand-in off the UI thread.

    Contract (Prove 1):
    - Worker must not create/touch QWidget or call sync UI (processEvents, show, ??.
    - Results cross to UI only via ``finished_ok`` / ``failed`` (see
      ``IRIS_AGENT_LOOP_UI_SIGNALS``). UI slots should use ``safe_agent_ui_slot``.
    - Exceptions in ``run`` are emitted as ``failed``; they must not escape into
      MainWindow slots as uncaught.

    Contract (Prove 2):
    - ``ensure_agent_loop_no_console`` at worker entry (CREATE_NO_WINDOW reuse).
    - ``Exception`` ??``failed`` with ``format_agent_loop_failure`` payload.
      Process stay-alive; kill is not a recovery path.
    - ``AGENT_LOOP_PROPAGATE_BASE`` (SystemExit, KeyboardInterrupt) re-raise ??
      do not swallow those as agent_failed.

    Contract (Prove 3):
    - Owned by ``AgentLoopHandle`` via ``attach_agent_loop_worker`` /
      ``replace_agent_loop_worker``. ``reset_agent_loop`` may quit/wait this
      worker while the UI host object stays the same.
    Stub-only until Merge; does not call :8642.
    """

    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        prompt: str = "prove0",
        force_fail: bool = False,
        standin_force_fail: bool = False,
        settle_ms: int = 0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._prompt = prompt
        self._force_fail = force_fail
        self._standin_force_fail = standin_force_fail
        self._settle_ms = max(0, int(settle_ms))

    def run(self) -> None:
        ensure_agent_loop_no_console()
        try:
            if self._settle_ms:
                # Keep this worker busy so Prove 1 can show the UI thread still ticks.
                self.msleep(self._settle_ms)
            if self._force_fail:
                raise RuntimeError("phase5-prove1 forced worker failure")
            result: AgentLoopStandinResult = run_agent_loop_standin(
                prompt=self._prompt,
                force_fail=self._standin_force_fail,
            )
            if not result.ok:
                detail = next(
                    (
                        m
                        for m in result.messages
                        if m.startswith(AGENT_LOOP_FAILED_PREFIX)
                    ),
                    "agent loop stand-in returned ok=False",
                )
                self.failed.emit(detail)
                return
            self.finished_ok.emit(result)
        except AGENT_LOOP_PROPAGATE_BASE:
            raise
        except Exception as e:  # noqa: BLE001 ??worker boundary; emit failed
            self.failed.emit(format_agent_loop_failure(e))


# Compat aliases for pre-rename imports (Wave B). Canonical names are IrisAgent*.
HermesHealthWorker = IrisAgentHealthWorker
HermesChatWorker = IrisAgentChatWorker
HermesControlSyncWorker = IrisAgentControlSyncWorker
HermesModelSyncWorker = IrisAgentModelSyncWorker

# re-export for callers that resolve targets in UI thread
__all__ = [
    "IrisAgentHealthWorker",
    "IrisAgentControlSyncWorker",
    "IrisAgentModelSyncWorker",
    "IrisAgentChatWorker",
    "HermesHealthWorker",
    "HermesControlSyncWorker",
    "HermesModelSyncWorker",
    "HermesChatWorker",
    "IrisAgentLoopStandinWorker",
    "IRIS_AGENT_LOOP_UI_SIGNALS",
    "safe_agent_ui_slot",
    "prove1_ui_abort_if_uncaught",
    "ChatAttempt",
    "IrisAgentInferenceTarget",
    "resolve_iris_agent_inference",
    "resolve_hermes_inference",
    "format_agent_loop_failure",
    "AGENT_LOOP_PROPAGATE_BASE",
    "AGENT_LOOP_FAILED_PREFIX",
    "ensure_agent_loop_no_console",
    "ensure_agent_loop_handle",
    "attach_agent_loop_worker",
    "reset_agent_loop",
    "replace_agent_loop_worker",
]
