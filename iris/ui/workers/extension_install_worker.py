"""채팅 GitHub MCP/Skill 설치 — 설정에 반영. Sidecar가 다음 턴에 home을 읽는다."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from iris.system.github_extension_install import ExtensionRequest, install_from_request


_SIDECAR_RUNTIME_MSG = (
    "설정은 저장됐습니다. Iris Agent(sidecar) 다음 턴부터 home 설정을 읽습니다."
)


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
        command: str = "iris-agent",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._request = request
        self._secrets = dict(secrets or {})
        self._directory = directory
        # reload_gateway kept for call-site compat; product never restarts :8642.
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
            if result.mcp_added:
                data["runtime"] = _SIDECAR_RUNTIME_MSG
            self.finished_ok.emit(data)
        except Exception as exc:  # noqa: BLE001
            self.finished_err.emit(str(exc)[:400])
