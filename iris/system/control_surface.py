"""Iris Control Surface — 로컬 HTTP 제어면 (Hermes MCP 브리지 대상).

ponytail: 액션은 name→handler 레지스트리 하나. MCP는 별도 stdio가 이 HTTP를 호출.
천장: 단일 프로세스·127.0.0.1 only. 원격/멀티유저면 인증·권한 모델 필요.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterator
from urllib.parse import parse_qs, urlparse

from iris.system.execution_context import host_tool_cancelled

if TYPE_CHECKING:
    from iris.system.native_gateway import NativeGateway

HandlerFn = Callable[[dict[str, Any]], dict[str, Any]]

# 클라이언트가 응답 전에 연결을 끊으면 Windows에서 흔함 (Hermes MCP 타임아웃 등)
_CLIENT_GONE = (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, TimeoutError)

# ponytail: adb/kill sleep·IMAP을 Qt 메인에 올리면 Windows "응답 없음". HTTP 워커에서 실행.
# 천장: 핸들러가 UI 위젯을 직접 건드리면 안 됨 — control_bindings._call_on_ui 가 마샬함.
_OFF_UI_PREFIXES = ("emulator.", "browser.")
_OFF_UI_ACTIONS = frozenset(
    {
        "email.list_messages",
        "email.read_message",
        # 터미널 로그 폴링·브리지 왕복이 최대 90초 — UI 스레드면 Windows "응답 없음"
        "project.run",
        "shell.run",
        "process.manage",
        "chat.exec_python",
        "note.export_pdf",
        "extension.install_github",
        "ide.marketplace_search",
        "ide.marketplace_install",
        "ide.diagnostics",
        "ide.symbols",
        "ide.references",
        "ide.definition",
        "ide.edit",
        "ide.save",
        "ide.task",
        "ide.debug",
        "ide.plugin_status",
        "project.write_image_code",
        # 디스크 쓰기·브리지 왕복. Qt 메인에서 스트림하면 Windows "응답 없음"
        "project.write_file",
        "project.apply_patch",
        "attachment.copy_to",
        "attachment.move_to",
        "project.import_attachment",
        "local.read_file",
        "local.search_files",
        # rmtree·IDE unlock. Qt 메인에서 돌리면 Windows "응답 없음"
        "project.delete",
        # 요약·문단 번역 모델 호출. Qt 메인에서 돌리면 창이 멈춘다.
        "wiki.reprocess_note",
        # 전체 요약·쪽 이미지 순차 읽기. Qt 메인에서 돌리면 창이 멈춘다.
        "wiki.import_content",
        "wiki.import_pages",
        "wiki.write_user_note",
        # Iris-owned urllib search/extract — network I/O, keep off Qt main
        "web.run_search",
        "web.run_extract",
    }
)


def runs_off_ui_thread(action: str) -> bool:
    name = (action or "").strip()
    return name in _OFF_UI_ACTIONS or any(name.startswith(p) for p in _OFF_UI_PREFIXES)


def invoke_http_timeout(
    action: str,
    args: dict[str, Any] | None = None,
    *,
    confirm_required: bool = False,
) -> float | None:
    """/v1/invoke UI-invoker 대기 초. None이면 끝날 때까지 (다이얼로그·confirm).

    Off-UI 액션은 call_registered가 invoker를 안 쓰므로 이 값이 무시된다.
    """
    name = (action or "").strip()
    payload = args if isinstance(args, dict) else {}
    if name == "ide.marketplace_install":
        return 180.0
    if name in ("ide.debug", "ide.task", "ide.edit", "ide.save"):
        return 45.0
    if name in ("ide.pick_open_file", "ide.pick_open_folder"):
        return None
    if name == "ide.open_folder":
        return 175.0
    # confirm이 Qt 메인에서 HUD를 띄우면 15s UiThreadTimeout에 죽는다.
    if confirm_required and not runs_off_ui_thread(name):
        return None
    if name == "project.write_file":
        if bool(payload.get("open", True)) and bool(
            payload.get("typewriter", payload.get("stream", True))
        ):
            return 180.0
        if bool(payload.get("stream")):
            return 120.0
    return 15.0


def _is_client_gone(exc: BaseException) -> bool:
    if isinstance(exc, _CLIENT_GONE):
        return True
    if isinstance(exc, OSError):
        # WinError 10053/10054, errno EPIPE/ECONNRESET
        win = getattr(exc, "winerror", None)
        if win in (10053, 10054):
            return True
        if getattr(exc, "errno", None) in (32, 104):  # EPIPE, ECONNRESET
            return True
    return False


@dataclass(frozen=True)
class ActionSpec:
    name: str
    summary: str
    risk: str = "low"  # low | medium | high
    confirm_required: bool = False


def control_state_dir() -> Path:
    d = Path.home() / ".iris-light"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_control_token() -> str:
    env = (os.environ.get("IRIS_CONTROL_TOKEN") or "").strip()
    if env:
        return env
    path = control_state_dir() / "control_token"
    if path.is_file():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    token = secrets.token_urlsafe(24)
    path.write_text(token, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return token


def write_control_endpoint(*, host: str, port: int, token: str) -> None:
    root = control_state_dir()
    (root / "control_port").write_text(str(port), encoding="utf-8")
    (root / "control_host").write_text(host, encoding="utf-8")
    token_path = root / "control_token"
    if not (os.environ.get("IRIS_CONTROL_TOKEN") or "").strip():
        token_path.write_text(token, encoding="utf-8")


def clear_control_endpoint() -> None:
    root = control_state_dir()
    for name in ("control_port", "control_host"):
        p = root / name
        try:
            p.unlink(missing_ok=True)  # type: ignore[call-arg]
        except TypeError:
            if p.exists():
                p.unlink()
        except OSError:
            pass


def ok_result(action: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
    """성공. result 생략은 {} — 빈 객체는 페이로드 없음이지, 대상 없음·null이 아니다.

    대상 없음은 액션 result 안의 null(예: editor) 또는 빈 목록으로 액션이 적는다.
    status는 success. 호출은 동기 HTTP다. UI 스레드 액션은 invoker가 마샬하고,
    runs_off_ui_thread인 액션만 HTTP 워커에서 직접 돈다.
    """
    return {"ok": True, "action": action, "status": "success", "result": result or {}, "error": None}


def err_result(
    action: str,
    error: str,
    result: dict[str, Any] | None = None,
    *,
    status: str = "failed",
) -> dict[str, Any]:
    """실패. status=failed는 실행·입력 실패. status=timeout은 UI 스레드 대기 초과.

    status=timeout은 취소도 미실행도 보장하지 않는다. 응답 뒤 큐의 작업이 실행될 수 있다.
    같은 액션을 다시 호출하지 않는 것은 호출자 계약이다. 모든 호출자가 그렇게 하는지는 보장하지 않는다.
    다시 호출하면 project.write_file·project.run이 겹칠 수 있다.
    확인된 사실: MCP _http는 이 JSON(HTTP 400)을 재시도하지 않는다.
    액션 내부 TimeoutError는 레지스트리가 status=failed로 감싼다.
    연결 실패는 이 객체가 아니다. 클라이언트가 먼저 끊기면 본문을 쓰지 않는다.
    status=invalid는 깨진 JSON·비객체 본문이다. status=cancelled는 호스트 턴 취소로 실행을 거절한 경우다.
    """
    return {"ok": False, "action": action, "status": status, "result": result or {}, "error": error}


def parse_invoke_body(raw: bytes) -> tuple[dict[str, Any] | None, str | None]:
    """빈 바이트는 {}. 깨진 JSON·배열은 오류. {}는 인자 없음이지 파싱 실패가 아니다."""
    if not raw:
        return {}, None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "invalid JSON"
    if not isinstance(data, dict):
        return None, "JSON object required"
    return data, None


def call_registered(
    surface: ControlSurface, action: str, args: dict[str, Any], *, timeout: float | None
) -> dict[str, Any]:
    """레지스트리 호출.

    status=timeout은 UiThreadTimeout이다. 대기 포기일 뿐 큐를 취소하지 않는다.
    같은 액션을 다시 호출하지 않는 것은 호출자 계약이다. 코드가 모든 재시도를 막지는 않는다.
    MCP _http만 HTTP 400을 재시도하지 않는 것이 확인됐다.
    UiThreadTimeout만 status=timeout이다. 그 외 TimeoutError와 핸들러 예외는 status=failed다.
    브리지 대기 초과(BridgeCallTimeout)는 TimeoutError가 아니므로 이 분기에 들어가지 않는다.

    쓰기 잠금은 HTTP 스레드에서 잡고, UI로 넘긴 뒤에 푼다. UI 스레드가 같은 잠금을
    기다리면, 잠금을 쥔 요청이 UI를 기다리는 동안 교착한다.
    """
    from iris.runtime.session_write_lock import shared_write_lock, write_holder, write_lock_target

    target = write_lock_target(action, args)
    holder = write_holder(args)
    lock = shared_write_lock()
    wiki_held: list[str] = []
    if target is not None:
        kind, keys = target
        if kind == "project":
            lock.acquire_project(holder)
        else:
            for key in sorted(set(keys)):
                lock.acquire_wiki(holder, key)
                wiki_held.append(key)

    def _run() -> dict[str, Any]:
        if surface.booting and action not in ("ping", "get_state", "get_catalog"):
            return err_result(action or "invoke", "Iris is still booting")
        return surface.registry.invoke(action, args)

    try:
        try:
            if runs_off_ui_thread(action):
                return _run()
            return surface.invoker.run(_run, timeout=timeout)
        except UiThreadTimeout as exc:
            return err_result(action or "invoke", str(exc), status="timeout")
        except TimeoutError as exc:
            return err_result(action or "invoke", str(exc) or "timeout")
    finally:
        if target is not None:
            kind, _keys = target
            if kind == "project":
                lock.release_project(holder)
            else:
                for key in reversed(wiki_held):
                    lock.release_wiki(holder, key)


class UiThreadTimeout(TimeoutError):
    """UI 스레드 대기 초과. 큐에 들어간 호출은 취소되지 않는다."""

    def __init__(self) -> None:
        super().__init__("Iris UI thread timeout")


class ActionRegistry:
    """Control Surface 액션 인터페이스. 이름 → 핸들러.

    기여자는 ``register``로 액션을 올린다. HTTP 서버 구현은 이 클래스 밖이다.
    """

    def __init__(self) -> None:
        self._specs: dict[str, ActionSpec] = {}
        self._handlers: dict[str, HandlerFn] = {}
        self._human_confirm: Callable[[ActionSpec, dict[str, Any]], bool] | None = None

    def set_human_confirm(
        self, fn: Callable[[ActionSpec, dict[str, Any]], bool] | None
    ) -> None:
        self._human_confirm = fn

    def spec(self, name: str) -> ActionSpec | None:
        return self._specs.get(name)

    def ask_human(self, spec: ActionSpec, args: dict[str, Any]) -> bool:
        if self._human_confirm is None:
            return False
        return bool(self._human_confirm(spec, args))

    def register(
        self,
        name: str,
        handler: HandlerFn,
        *,
        summary: str,
        risk: str = "low",
        confirm_required: bool = False,
    ) -> None:
        """액션 이름 하나를 등록한다. 같은 이름이면 ``ValueError``."""
        if name in self._specs:
            raise ValueError(f"duplicate control action: {name}")
        self._specs[name] = ActionSpec(
            name=name,
            summary=summary,
            risk=risk,
            confirm_required=confirm_required,
        )
        self._handlers[name] = handler

    def catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "name": s.name,
                "summary": s.summary,
                "risk": s.risk,
                "confirm_required": s.confirm_required,
            }
            for s in sorted(self._specs.values(), key=lambda x: x.name)
        ]

    def invoke(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = dict(args or {})
        if host_tool_cancelled():
            return err_result(name, "agent turn cancelled", status="cancelled")
        spec = self._specs.get(name)
        if spec is None:
            return err_result(name, f"unknown action: {name}")
        if spec.confirm_required:
            from iris.system.execution_policy import check_action_approval

            decision = check_action_approval(spec, args, self._human_confirm)
            if not decision.allowed:
                deny = {
                    "confirm_required": True,
                    "risk": spec.risk,
                    "approval_required": True,
                }
                reason = str(decision.reason or "human confirm required")
                if reason == "approval_ui_unavailable":
                    deny["approval_ui_unavailable"] = True
                return err_result(name, reason, deny)
            if host_tool_cancelled():
                return err_result(name, "agent turn cancelled", status="cancelled")
        handler = self._handlers[name]
        try:
            out = handler(args)
        except Exception as exc:  # noqa: BLE001 — 제어면 경계
            return err_result(name, str(exc) or type(exc).__name__)
        if isinstance(out, dict) and "ok" in out and "action" in out:
            return out
        return ok_result(name, out if isinstance(out, dict) else {"value": out})


class MainThreadInvoker:
    """HTTP 워커 → Qt 메인 스레드 마샬.

    QObject 시그널은 control_bindings에서 연결한다.
    """

    def __init__(self) -> None:
        self._fn: Callable[[Callable[[], Any], float | None], Any] | None = None

    def bind(self, runner: Callable[[Callable[[], Any], float | None], Any]) -> None:
        self._fn = runner

    def run(self, fn: Callable[[], Any], timeout: float | None = 15.0) -> Any:
        if self._fn is None:
            raise RuntimeError("MainThreadInvoker not bound to Qt")
        return self._fn(fn, timeout)


class ControlSurface:
    """레지스트리 + 로컬 HTTP 서버."""

    def __init__(
        self,
        *,
        invoker: MainThreadInvoker,
        host: str = "127.0.0.1",
        port: int = 8765,
        token: str = "",
        gateway: NativeGateway | None = None,
    ) -> None:
        self.registry = ActionRegistry()
        self.invoker = invoker
        self.host = host
        self.port = int(port)
        self.token = token
        self.gateway = gateway
        self._gateway_streams = threading.BoundedSemaphore(16)
        self.booting = True
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.bound_port: int | None = None

    def start(self) -> int:
        if self.host != "127.0.0.1":
            raise OSError("Iris Control must bind to 127.0.0.1")
        if self._httpd is not None:
            return int(self.bound_port or self.port)
        self.token = self.token or resolve_control_token()

        surface = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
                return

            def _auth_ok(self) -> bool:
                auth = self.headers.get("Authorization", "")
                return secrets.compare_digest(
                    auth.encode("utf-8"), f"Bearer {surface.token}".encode("utf-8")
                )

            def _cors(self) -> None:
                # Theia(QWebEngine) → control 포트는 cross-origin — ACAO 없으면 askIris 실패
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header(
                    "Access-Control-Allow-Headers",
                    "Authorization, Content-Type",
                )

            def _json(self, code: int, body: dict[str, Any]) -> None:
                raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
                try:
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.send_header("Connection", "close")
                    self.send_header("Cache-Control", "no-store")
                    self._cors()
                    self.end_headers()
                    self.wfile.write(raw)
                except Exception as exc:  # noqa: BLE001
                    if _is_client_gone(exc):
                        return
                    raise

            def do_OPTIONS(self) -> None:  # noqa: N802
                try:
                    self.send_response(204)
                    self._cors()
                    self.send_header("Content-Length", "0")
                    self.send_header("Connection", "close")
                    self.end_headers()
                except Exception as exc:  # noqa: BLE001
                    if _is_client_gone(exc):
                        return
                    raise

            def _read_json(self, max_length: int | None = None) -> tuple[dict[str, Any] | None, str | None]:
                try:
                    length = int(self.headers.get("Content-Length") or "0")
                except ValueError:
                    return None, "invalid Content-Length"
                if length < 0 or (max_length is not None and length > max_length):
                    return None, "invalid request size"
                if length <= 0:
                    return {}, None
                try:
                    raw = self.rfile.read(length)
                except Exception as exc:  # noqa: BLE001
                    if _is_client_gone(exc):
                        return None, "client disconnected"
                    raise
                if len(raw) != length:
                    return None, "incomplete request body"
                return parse_invoke_body(raw)

            def _ndjson(self, events: Iterator[dict]) -> None:
                if not surface._gateway_streams.acquire(blocking=False):
                    self._json(429, {"error": "event stream capacity reached"})
                    return
                self.close_connection = True
                try:
                    self.connection.settimeout(10)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                    self.send_header("Connection", "close")
                    self.send_header("Cache-Control", "no-store")
                    self._cors()
                    self.end_headers()
                    for event in events:
                        self.wfile.write((json.dumps(event) + "\n").encode("utf-8"))
                        self.wfile.flush()
                except OSError as exc:
                    if not _is_client_gone(exc):
                        raise
                finally:
                    surface._gateway_streams.release()

            def do_GET(self) -> None:  # noqa: N802
                url = urlparse(self.path)
                path = url.path.rstrip("/") or "/"
                if surface.gateway is not None and path.startswith("/v1/agent/"):
                    auth = self.headers.get("Authorization", "")
                    control = self._auth_ok()
                    approval_run = surface.gateway.approval_run_id(path)
                    if approval_run:
                        self._json(*(surface.gateway.approval(approval_run) if control else (401, {"error": "unauthorized"})))
                        return
                    code, principal = surface.gateway.authorize(auth, control=control, scope="read")
                    if code != 200:
                        self._json(code, err_result("auth", "gateway access denied"))
                        return
                    if path == "/v1/agent/health":
                        readiness = (503, {"ready": False}) if surface.booting else surface.gateway.health()
                        self._json(*readiness)
                    elif path == "/v1/agent/sessions/search":
                        try:
                            queries = parse_qs(url.query, keep_blank_values=True, max_num_fields=8).get("q", [])
                        except ValueError:
                            queries = []
                        self._json(*surface.gateway.search_sessions(
                            queries[0] if len(queries) == 1 else "", principal=principal,
                        ))
                    elif path.startswith("/v1/agent/runs/") and path.endswith("/events"):
                        try:
                            after = int(parse_qs(url.query).get("after", ["0"])[0])
                            if after < 0:
                                raise ValueError
                        except ValueError:
                            self._json(400, {"error": "invalid event cursor"})
                            return
                        events = surface.gateway.events(path.split("/")[-2], after, principal=principal)
                        if events is None:
                            self._json(404, {"error": "run not found"})
                        else:
                            def authorized_events():
                                for event in events:
                                    if surface.gateway.authorize(auth, control=control, scope="read") != (200, principal):
                                        return
                                    yield event

                            self._ndjson(authorized_events())
                    else:
                        self._json(*surface.gateway.get(path, principal=principal))
                    return
                if not self._auth_ok():
                    self._json(401, err_result("auth", "unauthorized"))
                    return
                if path in ("/health", "/v1/ping"):
                    self._json(
                        200,
                        ok_result(
                            "ping",
                            {"alive": True, "booting": surface.booting, "port": surface.bound_port},
                        ),
                    )
                    return
                if path == "/v1/catalog":
                    # registry만 — UI 스레드 불필요 (Companion/타일 중 타임아웃 방지)
                    self._json(
                        200,
                        ok_result(
                            "get_catalog",
                            {"actions": surface.registry.catalog()},
                        ),
                    )
                    return
                if path == "/v1/state":
                    # 실패도 200 — 기존 소비자(urlopen)가 400을 연결 거절로 오인하지 않게
                    body = call_registered(surface, "get_state", {}, timeout=15.0)
                    self._json(200, body)
                    return
                self._json(404, err_result("http", f"not found: {path}"))

            def do_POST(self) -> None:  # noqa: N802
                path = urlparse(self.path).path.rstrip("/") or "/"
                if surface.gateway is not None and path.startswith("/v1/agent/"):
                    control = self._auth_ok()
                    auth = self.headers.get("Authorization", "")
                    token_management = path == "/v1/agent/tokens" or path.startswith("/v1/agent/tokens/")
                    approval_run = surface.gateway.approval_run_id(path)
                    if token_management or approval_run:
                        code, principal = (200 if control else 401), ""
                    else:
                        code, principal = surface.gateway.authorize(
                            auth, control=control,
                            scope="cancel" if path.endswith("/cancel") else "run",
                        )
                    if code != 200:
                        self._json(code, err_result("auth", "gateway access denied"))
                        return
                    if surface.booting:
                        self._json(503, {"error": "Iris is still booting"})
                        return
                    self.connection.settimeout(10)
                    payload, read_err = self._read_json(max_length=131072)
                    if read_err or payload is None:
                        self._json(400, {"error": read_err or "invalid JSON"})
                    elif token_management:
                        self._json(*surface.gateway.manage_token(path, payload))
                    elif approval_run:
                        self._json(*surface.gateway.approval(approval_run, payload))
                    else:
                        allow_mcp = (path == "/v1/agent/runs"
                                     and surface.gateway.authorize(auth, control=control, scope="mcp") == (200, principal))
                        self._json(*surface.gateway.post(path, payload, principal=principal, allow_mcp=allow_mcp))
                    return
                if not self._auth_ok():
                    self._json(401, err_result("auth", "unauthorized"))
                    return
                payload, read_err = self._read_json()
                if path == "/v1/invoke":
                    if read_err or payload is None:
                        self._json(400, err_result("invoke", read_err or "invalid JSON", status="invalid"))
                        return
                    action = str(payload.get("action") or "").strip()
                    args = payload.get("args")
                    if not isinstance(args, dict):
                        args = {k: v for k, v in payload.items() if k not in ("action", "args")}

                    spec = surface.registry.spec(action)
                    confirm_required = bool(spec.confirm_required) if spec is not None else False
                    timeout = invoke_http_timeout(
                        action, args, confirm_required=confirm_required
                    )

                    body = call_registered(surface, action, args, timeout=timeout)
                    self._json(200 if body.get("ok") else 400, body)
                    return
                self._json(404, err_result("http", f"not found: {path}"))

        class QuietHTTPServer(ThreadingHTTPServer):
            daemon_threads = True

            def handle_error(self, request: object, client_address: object) -> None:
                import sys

                exc = sys.exc_info()[1]
                if exc is not None and _is_client_gone(exc):
                    return
                super().handle_error(request, client_address)

        last_err: OSError | None = None
        httpd: ThreadingHTTPServer | None = None
        bound = self.port
        for candidate in range(self.port, self.port + 10):
            try:
                httpd = QuietHTTPServer((self.host, candidate), Handler)
                bound = int(httpd.server_address[1])
                break
            except OSError as exc:
                last_err = exc
                httpd = None
        if httpd is None:
            raise OSError(f"control surface bind failed on {self.host}:{self.port}+ : {last_err}")

        try:
            write_control_endpoint(host=self.host, port=bound, token=self.token)
        except OSError:
            httpd.server_close()
            raise
        self._httpd = httpd
        self.bound_port = bound

        def _serve() -> None:
            httpd.serve_forever(poll_interval=0.3)

        self._thread = threading.Thread(target=_serve, name="iris-control-http", daemon=True)
        self._thread.start()
        return bound

    def stop(self) -> None:
        if self.gateway is not None:
            self.gateway.close()
        httpd = self._httpd
        self._httpd = None
        if httpd is not None:
            try:
                httpd.shutdown()
            except Exception:
                pass
            try:
                httpd.server_close()
            except Exception:
                pass
            clear_control_endpoint()
        self.bound_port = None
        t = self._thread
        self._thread = None
        if t is not None and t.is_alive():
            t.join(timeout=2.0)


def _self_check() -> None:
    reg = ActionRegistry()
    reg.register("ping", lambda _a: {"alive": True}, summary="ping")
    assert len(reg.catalog()) == 1
    try:
        reg.register("ping", lambda _a: {}, summary="dup")
        raise AssertionError("duplicate should fail")
    except ValueError:
        pass
    out = reg.invoke("ping", {})
    assert out["ok"] is True
    high = ActionRegistry()
    high.register(
        "email.send",
        lambda a: {"sent": True},
        summary="send",
        risk="high",
        confirm_required=True,
    )
    denied = high.invoke("email.send", {})
    assert denied["ok"] is False
    denied_wire = high.invoke("email.send", {"confirm": True})
    assert denied_wire["ok"] is False
    high.set_human_confirm(lambda spec, args: False)
    denied_hud = high.invoke("email.send", {"confirm": True, "to": "a@b.c"})
    assert denied_hud["ok"] is False
    high.set_human_confirm(lambda spec, args: True)
    allowed = high.invoke("email.send", {"confirm": True, "to": "a@b.c"})
    assert allowed["ok"] is True
    # 긴 액션이 UI 스레드로 돌아가면 Windows "응답 없음"
    assert runs_off_ui_thread("project.run")
    assert runs_off_ui_thread("emulator.start")
    assert runs_off_ui_thread("note.export_pdf")
    assert runs_off_ui_thread("extension.install_github")
    assert runs_off_ui_thread("project.write_image_code")
    assert runs_off_ui_thread("project.write_file")
    assert runs_off_ui_thread("project.delete")
    empty, empty_err = parse_invoke_body(b"")
    assert empty == {} and empty_err is None
    bad, bad_err = parse_invoke_body(b"[1]")
    assert bad is None and bad_err == "JSON object required"
    broken, broken_err = parse_invoke_body(b"{")
    assert broken is None and broken_err == "invalid JSON"

    class _Boom:
        def run(self, fn: Callable[[], Any], timeout: float = 15.0) -> Any:
            raise UiThreadTimeout()

    class _Surface:
        booting = False
        registry = reg
        invoker = _Boom()

    timed = call_registered(_Surface(), "ping", {}, timeout=0.01)  # type: ignore[arg-type]
    assert timed["ok"] is False and timed["status"] == "timeout"
    assert timed["error"] == "Iris UI thread timeout"

    class _Disk:
        def run(self, fn: Callable[[], Any], timeout: float = 15.0) -> Any:
            raise TimeoutError("disk")

    _Surface.invoker = _Disk()
    disk = call_registered(_Surface(), "ping", {}, timeout=0.01)  # type: ignore[arg-type]
    assert disk["status"] == "failed" and disk["error"] == "disk"
    assert reg.invoke("missing", {})["status"] == "failed"
    print("control_surface self-check ok")


if __name__ == "__main__":
    _self_check()
