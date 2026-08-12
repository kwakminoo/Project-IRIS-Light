"""백그라운드 Hermes API 워커."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from iris.infrastructure.hermes_client import HermesClient, host_label_for_hermes
from iris.system.hermes_gateway import (
    ensure_hermes_gateway_running,
    ensure_hermes_provider_config,
    is_hermes_gateway_running,
    restart_hermes_gateway,
    verify_iris_mcp_tools,
)
from iris.system.hermes_iris_control_sync import sync_iris_control


class HermesHealthWorker(QThread):
    """Hermes gateway 헬스 체크 — MCP/스킬 동기화 후 미기동 시 자동 기동."""

    finished_ok = pyqtSignal(bool)
    failed = pyqtSignal(str)
    notice = pyqtSignal(str)

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
            ensure_hermes_provider_config()
            # Iris Control MCP·스킬 → Hermes 디스크, 기동 시마다 MCP 재연결
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

                gateway_up = is_hermes_gateway_running(
                    self._base_url, api_key=self._api_key
                )
                if report.needs_gateway_reload:
                    self.notice.emit("MCP 연결 — Hermes gateway 완전 재기동…")
                    ok = restart_hermes_gateway(
                        self._base_url,
                        api_key=self._api_key,
                        command=self._command,
                        wait_sec=60.0,
                    )
                    if ok:
                        mcp_ok, mcp_detail = verify_iris_mcp_tools(
                            command=self._command
                        )
                        if mcp_ok:
                            self.notice.emit(f"Hermes MCP 재연결 완료 — {mcp_detail}")
                        else:
                            self.notice.emit(
                                f"Gateway는 떴지만 MCP 검증 실패: {mcp_detail}"
                            )
                            ok = False
                    else:
                        self.notice.emit("Hermes gateway 재기동 실패")
                    self.finished_ok.emit(ok)
                    return

                if gateway_up:
                    # 이미 떠 있어도 MCP가 죽은 채일 수 있음 → 검증 후 필요 시 재기동
                    mcp_ok, mcp_detail = verify_iris_mcp_tools(command=self._command)
                    if mcp_ok:
                        self.notice.emit(f"MCP 유지 확인 — {mcp_detail}")
                        self.finished_ok.emit(True)
                        return
                    self.notice.emit(
                        f"MCP 미연결({mcp_detail}) — gateway 재기동…"
                    )
                    ok = restart_hermes_gateway(
                        self._base_url,
                        api_key=self._api_key,
                        command=self._command,
                        wait_sec=60.0,
                    )
                    if ok:
                        mcp_ok2, mcp_detail2 = verify_iris_mcp_tools(
                            command=self._command
                        )
                        self.notice.emit(
                            f"Hermes MCP 재연결: {mcp_detail2}"
                            if mcp_ok2
                            else f"MCP 재검증 실패: {mcp_detail2}"
                        )
                        ok = mcp_ok2
                    self.finished_ok.emit(ok)
                    return
            except Exception as sync_exc:  # noqa: BLE001
                self.notice.emit(f"Iris↔Hermes control sync skip: {str(sync_exc)[:120]}")

            if is_hermes_gateway_running(self._base_url, api_key=self._api_key):
                self.finished_ok.emit(True)
                return
            self.notice.emit("Hermes gateway가 꺼져 있습니다. 시작합니다…")
            ok = ensure_hermes_gateway_running(
                self._base_url,
                api_key=self._api_key,
                command=self._command,
            )
            if ok:
                mcp_ok, mcp_detail = verify_iris_mcp_tools(command=self._command)
                self.notice.emit(
                    f"Hermes gateway 시작됨 — {mcp_detail}"
                    if mcp_ok
                    else f"Gateway 시작됐지만 MCP 실패: {mcp_detail}"
                )
                ok = mcp_ok
            else:
                self.notice.emit(
                    "Hermes gateway를 시작할 수 없습니다. hermes 설치와 API_SERVER_ENABLED를 확인하세요."
                )
            self.finished_ok.emit(ok)
        except Exception as e:
            self.failed.emit(str(e))


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
            lines.extend(report.messages[:6])
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
                lines.append("gateway 재기동 실패")
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
            if not is_hermes_gateway_running(self._base_url, api_key=self._api_key):
                self.tool_progress.emit("Hermes gateway 기동 중…")
                if not ensure_hermes_gateway_running(
                    self._base_url,
                    api_key=self._api_key,
                    command=self._command,
                ):
                    self.failed.emit(
                        "Hermes gateway를 시작할 수 없습니다. hermes 설치와 API_SERVER_ENABLED를 확인하세요."
                    )
                    return
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
