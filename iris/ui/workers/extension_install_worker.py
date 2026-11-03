"""채팅 GitHub MCP/Skill 설치 — Hermes 설정에 반영한 뒤 gateway를 다시 붙인다."""

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
                data["runtime"] = self._reload_gateway()
            elif result.mcp_added:
                data["runtime"] = (
                    "설정은 저장되어 다음 Hermes 기동 때 로드됩니다."
                )
            self.finished_ok.emit(data)
        except Exception as exc:  # noqa: BLE001
            self.finished_err.emit(str(exc)[:400])

    def _reload_gateway(self) -> str:
        try:
            from iris.system.hermes_gateway import restart_hermes_gateway

            ok = restart_hermes_gateway(
                self._base_url,
                api_key=self._api_key,
                command=self._command,
                wait_sec=60.0,
            )
        except Exception as exc:  # noqa: BLE001
            return f"설정은 저장됐지만 gateway 재시작에 실패했습니다: {exc}"[:300]
        if ok:
            return "Iris Agent gateway를 재시작했습니다. 이제 이 MCP 도구를 사용할 수 있습니다."
        return "설정은 저장됐지만 gateway 재시작에 실패했습니다. Hermes를 다시 켜면 적용됩니다."
