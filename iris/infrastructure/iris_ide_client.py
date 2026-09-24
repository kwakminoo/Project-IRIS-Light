"""IRIS IDE Bridge HTTP client — localhost only."""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LOGGER = logging.getLogger(__name__)


class IrisIdeClientError(RuntimeError):
    """code: execution | auth | server | connection | timeout | protocol.

    우선순위: 본문 code → HTTP 상태 → 응답 없음.
    본문 code가 알려진 값이면 상태보다 먼저다. 408·504도 본문 code가 있으면 그 code다.
    상태가 남을 때 408·504는 timeout, 401·403·407은 auth, 그 외 5xx는 server.
    connection은 HTTP 응답이 없는 전송 실패만. protocol은 깨진 JSON·비객체 본문.
    오류 문구로 code를 정하지 않는다. str()은 기존 문구 그대로.
    """

    def __init__(self, message: str, *, code: str = "execution") -> None:
        super().__init__(message)
        self.code = code


_CODES = frozenset({"execution", "auth", "server", "connection", "timeout", "protocol"})


def _body_code(body: object) -> str | None:
    if isinstance(body, dict) and body.get("code") in _CODES:
        return str(body["code"])
    return None


def _http_code(status: int, body: object) -> str:
    """상태와 본문 code만 본다. 오류 문구는 다시 읽지 않는다."""
    marked = _body_code(body)
    if marked:
        return marked
    if status in (408, 504):
        return "timeout"
    if status in (401, 403, 407):
        return "auth"
    if status >= 500:
        return "server"
    if not isinstance(body, dict):
        return "protocol"
    return "execution"


class IrisIdeClient:
    def __init__(self, *, base_url: str, token: str = "", timeout: float = 30.0) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.token = (token or "").strip()
        self.timeout = float(timeout)
        if not self.base_url.startswith("http://127.0.0.1"):
            raise IrisIdeClientError("bridge must bind to 127.0.0.1 only")

    def _request(self, command: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/{command.lstrip('/')}"
        body = json.dumps(payload or {}).encode("utf-8")
        req = Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json; charset=utf-8")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        t0 = time.monotonic()
        LOGGER.debug("iris_ide bridge -> %s (timeout=%.1fs)", command, self.timeout)
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except HTTPError as exc:
            # 브리지는 실패 사유를 본문 JSON에만 담는다 — 버리면 "HTTP Error 400"만 남아 진단이 끊긴다.
            try:
                body = json.loads(exc.read().decode("utf-8"))
            except (ValueError, OSError, UnicodeDecodeError):
                body = None
            detail = str(body.get("error") or "") if isinstance(body, dict) else ""
            message = f"{command}: {detail}" if detail else str(exc)
            raise IrisIdeClientError(message, code=_http_code(exc.code, body)) from exc
        except (URLError, TimeoutError, OSError) as exc:
            LOGGER.warning(
                "iris_ide bridge %s failed after %.2fs: %s", command, time.monotonic() - t0, exc
            )
            reason = getattr(exc, "reason", None)
            timed = isinstance(exc, TimeoutError) or isinstance(reason, TimeoutError)
            raise IrisIdeClientError(str(exc), code="timeout" if timed else "connection") from exc
        elapsed = time.monotonic() - t0
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            LOGGER.warning("iris_ide bridge %s returned invalid JSON after %.2fs", command, elapsed)
            raise IrisIdeClientError("invalid JSON from bridge", code="protocol") from exc
        if not isinstance(data, dict):
            raise IrisIdeClientError("unexpected bridge response", code="protocol")
        if not data.get("ok"):
            LOGGER.warning(
                "iris_ide bridge %s returned error after %.2fs: %s",
                command,
                elapsed,
                data.get("error"),
            )
            raise IrisIdeClientError(
                str(data.get("error") or "bridge error"),
                code=_body_code(data) or "execution",
            )
        LOGGER.debug("iris_ide bridge <- %s ok in %.2fs", command, elapsed)
        result = data.get("result")
        return result if isinstance(result, dict) else {"value": result}

    def health(self) -> dict[str, Any]:
        return self._request("health")

    def get_workspace(self) -> dict[str, Any]:
        return self._request("getWorkspace")

    def get_active_editor(self) -> dict[str, Any]:
        return self._request("getActiveEditor")

    def get_open_editors(self) -> dict[str, Any]:
        return self._request("getOpenEditors")

    def get_cursor_position(self) -> dict[str, Any]:
        return self._request("getCursorPosition")

    def get_selection(self) -> dict[str, Any]:
        return self._request("getSelection")

    def get_diagnostics(self) -> dict[str, Any]:
        return self._request("getDiagnostics")

    def open_file(self, path: str, *, line: int = 1, column: int = 1) -> dict[str, Any]:
        return self._request("openFile", {"path": path, "line": line, "column": column})

    def save_file(self, path: str = "") -> dict[str, Any]:
        return self._request("saveFile", {"path": path})

    def save_all(self) -> dict[str, Any]:
        return self._request("saveAll")

    def create_file(self, path: str, content: str = "") -> dict[str, Any]:
        return self._request("createFile", {"path": path, "content": content})

    def delete_file(self, path: str) -> dict[str, Any]:
        return self._request("deleteFile", {"path": path})

    def rename_file(self, path: str, new_path: str) -> dict[str, Any]:
        return self._request("renameFile", {"from": path, "to": new_path})

    def replace_selection(self, text: str, *, path: str = "") -> dict[str, Any]:
        return self._request("replaceSelection", {"text": text, "path": path})

    def apply_text_edit(self, text: str, *, path: str = "") -> dict[str, Any]:
        return self._request("applyTextEdit", {"text": text, "path": path})

    def insert_text(self, text: str, *, path: str = "") -> dict[str, Any]:
        return self._request("insertText", {"text": text, "path": path})

    def replace_range(
        self,
        text: str,
        *,
        path: str = "",
        start: int = 0,
        end: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"text": text, "path": path, "start": start}
        if end is not None:
            payload["end"] = end
        return self._request("replaceRange", payload)

    def format_document(self, path: str = "") -> dict[str, Any]:
        return self._request("formatDocument", {"path": path})

    def goto_file(self, path: str, *, line: int = 1, column: int = 1) -> dict[str, Any]:
        return self._request("gotoFile", {"path": path, "line": line, "column": column})

    def goto_line(self, line: int) -> dict[str, Any]:
        return self._request("gotoLine", {"line": line})

    def goto_symbol(self, symbol: str) -> dict[str, Any]:
        return self._request("gotoSymbol", {"symbol": symbol})

    def find_references(self, path: str = "") -> dict[str, Any]:
        return self._request("findReferences", {"path": path})

    def create_terminal(self, name: str = "IRIS") -> dict[str, Any]:
        return self._request("createTerminal", {"name": name})

    def run_terminal_command(
        self, command: str, *, cwd: str = "", argv: list[str] | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"command": command, "cwd": cwd}
        if argv:
            payload["argv"] = [str(a) for a in argv]
        return self._request("runTerminalCommand", payload)

    def get_terminal_state(self) -> dict[str, Any]:
        return self._request("getTerminalState")

    def run_task(self, name: str = "") -> dict[str, Any]:
        return self._request("runTask", {"name": name})

    def get_task_state(self) -> dict[str, Any]:
        return self._request("getTaskState")

    def start_debug(self, config: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("startDebug", config or {})

    def stop_debug(self) -> dict[str, Any]:
        return self._request("stopDebug")

    def continue_debug(self) -> dict[str, Any]:
        return self._request("continueDebug")

    def get_git_status(self) -> dict[str, Any]:
        return self._request("getGitStatus")

    def get_git_diff(self, path: str = "") -> dict[str, Any]:
        return self._request("getGitDiff", {"path": path})


def _self_check() -> None:
    from iris.system.iris_ide_runtime import is_iris_ide_demo

    if not is_iris_ide_demo():
        print("iris_ide_client skip (set IRIS_IDE_DEMO=1 for live bridge test)")
        return
    client = IrisIdeClient(base_url="http://127.0.0.1:3001", token="demo-token")
    h = client.health()
    assert h.get("product")
    print("iris_ide_client ok", h.get("product"))


if __name__ == "__main__":
    _self_check()
