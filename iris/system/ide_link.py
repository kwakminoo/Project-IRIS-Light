"""IDE 연동 경계. 명령과 편집기 상태 알림을 나누고, 토큰·타임아웃·재연결은 여기만 안다.

창 이벤트는 `page_identity()`로 페이지에 넣을 값만 받고, 브리지 URL·토큰 필드를 읽지 않는다.
편집기 상태는 pull(`editor_state`)이고, 경로가 바뀔 때만 구독자에게 알린다. 전역 버스는 없다.
`close()`가 클라이언트·캐시·구독을 함께 버린다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from iris.infrastructure.iris_ide_client import IrisIdeClient

LOGGER = logging.getLogger(__name__)
EditorListener = Callable[[dict[str, Any]], None]
_BUDGET = 1.5


def query_failure(value: Any) -> bool:
    """조회 실패 객체. 경로가 있는 편집기 정보와 구분한다."""
    return isinstance(value, dict) and bool(value.get("error")) and not (
        value.get("path") or value.get("uri")
    )


def editor_path(editor: Any) -> str | None:
    """정상 편집기의 경로. 없음·조회 실패는 None. error 객체의 키를 필수로 읽지 않는다."""
    if not isinstance(editor, dict) or query_failure(editor):
        return None
    path = str(editor.get("path") or editor.get("uri") or "").strip()
    return path or None


@dataclass(frozen=True)
class PageIdentity:
    """Theia 첫 로드에 붙는 브리지 신원. 컨트롤 신원은 여기 없다."""

    port: int
    token: str


class IdeLink:
    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime
        self._client: IrisIdeClient | None = None
        self._client_key: tuple[str, str] = ("", "")
        self._listeners: list[EditorListener] = []
        self._last_editor_path: str | None = None
        self._cache_at = 0.0
        self._cache: dict[str, Any] = {}

    def client(self, *, timeout: float = 30.0) -> IrisIdeClient:
        """URL 또는 토큰이 바뀌면 새 클라이언트. 창은 이 객체의 필드를 읽지 않는다."""
        url = self._runtime.bridge_base_url()
        token = self._runtime.bridge_token()
        key = (url, token)
        if self._client is None or key != self._client_key or self._client.timeout != timeout:
            self._client = IrisIdeClient(base_url=url, token=token, timeout=timeout)
            self._client_key = key
        return self._client

    def page_identity(self) -> PageIdentity:
        port = int(self._runtime.bridge_port or 0)
        return PageIdentity(port=port, token=self._runtime.bridge_token())

    def open_file(
        self, path: str, *, line: int = 1, column: int = 1, timeout: float = 30.0
    ) -> dict[str, Any]:
        """명령. 반환은 브리지 result. 예외는 IrisIdeClientError(타임아웃 포함)."""
        return self.client(timeout=timeout).open_file(path, line=line, column=column)

    def editor_state(self, client: IrisIdeClient | None, *, now: float | None = None) -> dict[str, Any]:
        """상태 조회. 명령이 아니다. 미기동·부분 정지는 예산 안에서 끊는다."""
        import time

        clock = time.monotonic() if now is None else now
        if client is None:
            return {}
        if clock - self._cache_at < 1.0 and self._cache:
            return dict(self._cache)
        out = self._editor_state_uncached(client)
        self._cache_at = time.monotonic()
        self._cache = out
        self._notify(out)
        return dict(out)

    def subscribe(self, listener: EditorListener) -> Callable[[], None]:
        """활성 편집기 경로가 바뀔 때만 호출. 반환값은 해제."""
        self._listeners.append(listener)

        def off() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return off

    def invalidate(self) -> None:
        self._cache_at = 0.0
        self._cache = {}

    def close(self) -> None:
        """세션 종료. 클라이언트·상태 캐시·구독을 함께 버린다."""
        self._client = None
        self._client_key = ("", "")
        self._listeners.clear()
        self._last_editor_path = None
        self.invalidate()

    def _notify(self, snapshot: dict[str, Any]) -> None:
        ide = snapshot.get("iris_ide") if isinstance(snapshot, dict) else None
        editor = ide.get("active_editor") if isinstance(ide, dict) else None
        if query_failure(editor):
            return
        path = editor_path(editor) or ""
        if path == (self._last_editor_path or ""):
            return
        self._last_editor_path = path or None
        for listener in list(self._listeners):
            try:
                listener(dict(snapshot))
            except Exception:
                LOGGER.warning("ide editor listener failed", exc_info=True)
                continue

    def _editor_state_uncached(self, client: IrisIdeClient) -> dict[str, Any]:
        import time

        fast = IrisIdeClient(base_url=client.base_url, token=client.token, timeout=_BUDGET)
        deadline = time.monotonic() + _BUDGET
        try:
            fast.health()
        except Exception as exc:  # noqa: BLE001
            return {"iris_ide": _query_error(exc)}

        def part(call: Callable[[], Any]) -> Any:
            """성공한 빈 값(None, "")은 그대로. 예외·예산 소진은 error 객체."""
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return {"error": "budget", "code": "timeout"}
            fast.timeout = remaining
            try:
                return call()
            except Exception as exc:  # noqa: BLE001
                return _query_error(exc)

        return {
            "iris_ide": {
                "workspace": part(lambda: fast.get_workspace().get("root") or ""),
                "active_editor": part(lambda: fast.get_active_editor().get("editor")),
                "cursor": part(fast.get_cursor_position),
                "selection": part(lambda: fast.get_selection().get("selection")),
                "diagnostics": part(lambda: fast.get_diagnostics().get("diagnostics") or []),
            }
        }


def _query_error(exc: BaseException) -> dict[str, str]:
    """error 문구는 그대로 두고, 예외에 code가 있으면 옆에 붙인다."""
    out = {"error": str(exc)}
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code:
        out["code"] = code
    return out


def shared_ide_link() -> IdeLink:
    from iris.system.iris_ide_runtime import shared_iris_ide_runtime

    mgr = shared_iris_ide_runtime()
    link = getattr(mgr, "_ide_link", None)
    if link is None:
        link = IdeLink(mgr)
        mgr._ide_link = link
    return link
