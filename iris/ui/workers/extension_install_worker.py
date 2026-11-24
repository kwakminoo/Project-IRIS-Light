"""채팅 GitHub MCP/Skill 설치 — Hermes 설정에 반영. gateway 재기동 없음."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from iris.system.github_extension_install import ExtensionRequest, install_from_request


class ExtensionInstallWorker(QThread):
    finished_ok = pyqtSignal(dict)
    finished_err = pyqtSignal(str)

    def __init__(
        self,
        request: ExtensionRequest,
        *,
        secrets: dict[str, str] | None = None,
        directory: str | None = None,
        reload_gateway: bool = False,
        base_url: str = "",
        api_key: str = "",
        command: str = "hermes",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._request = request
        self._secrets = dict(secrets or {})
        self._directory = directory
        self._reload = reload_gateway
        # Compat (settings still pass gateway fields); unused for :8642 spawn.
        self._base_url = base_url
        self._api_key = api_key
        self._command = command

    def run(self) -> None:
        try:
            result = install_from_request(
                self._request,
                secrets=self._secrets,
                directory=self._directory,
            )
            data = result.to_dict()
            if result.mcp_added and self._reload:
                data["runtime"] = self._reload_runtime()
            elif result.mcp_added:
                data["runtime"] = (
                    "설정은 저장되어 다음 Iris Agent 기동 때 로드됩니다."
                )
            self.finished_ok.emit(data)
        except Exception as exc:  # noqa: BLE001
            self.finished_err.emit(str(exc)[:400])

    def _reload_runtime(self) -> str:
        """Optional engine recycle after disk install. Never spawns :8642."""
        try:
            from iris.engine import EngineFailed, shared_engine
            from iris.engine.runtime import reset_shared_engine

            reset_shared_engine()
            result = shared_engine().ensure_ready()
        except Exception as exc:  # noqa: BLE001
            return (
                f"설정은 저장됐지만 엔진 준비에 실패했습니다: {exc}"
            )[:300]
        if isinstance(result, EngineFailed):
            detail = result.error.detail or result.user_message
            return (
                f"설정은 저장됐지만 엔진 준비에 실패했습니다: {detail}"
            )[:300]
        return "설정은 저장됐고 엔진을 다시 준비했습니다. (HTTP gateway 재시작은 사용하지 않음)"
