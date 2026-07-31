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
from typing import Any, Callable
from urllib.parse import urlparse

HandlerFn = Callable[[dict[str, Any]], dict[str, Any]]

# 클라이언트가 응답 전에 연결을 끊으면 Windows에서 흔함 (Hermes MCP 타임아웃 등)
_CLIENT_GONE = (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, TimeoutError)


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
    return {"ok": True, "action": action, "result": result or {}, "error": None}


def err_result(action: str, error: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": False, "action": action, "result": result or {}, "error": error}


class ActionRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ActionSpec] = {}
        self._handlers: dict[str, HandlerFn] = {}

    def register(
        self,
        name: str,
        handler: HandlerFn,
        *,
        summary: str,
        risk: str = "low",
        confirm_required: bool = False,
    ) -> None:
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
        spec = self._specs.get(name)
        if spec is None:
            return err_result(name, f"unknown action: {name}")
        if spec.confirm_required and not bool(args.get("confirm")):
            return err_result(
                name,
                "confirm=true required for this action",
                {"confirm_required": True, "risk": spec.risk},
            )
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
        self._fn: Callable[[Callable[[], Any], float], Any] | None = None

    def bind(self, runner: Callable[[Callable[[], Any], float], Any]) -> None:
        self._fn = runner

    def run(self, fn: Callable[[], Any], timeout: float = 15.0) -> Any:
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
    ) -> None:
        self.registry = ActionRegistry()
        self.invoker = invoker
        self.host = host
        self.port = int(port)
        self.token = token or resolve_control_token()
        self.booting = True
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.bound_port: int | None = None

    def start(self) -> int:
        if self._httpd is not None:
            return int(self.bound_port or self.port)

        surface = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
                return

            def _auth_ok(self) -> bool:
                auth = self.headers.get("Authorization", "")
                if auth == f"Bearer {surface.token}":
                    return True
                q = urlparse(self.path).query
                return f"token={surface.token}" in q.split("&") if q else False

            def _json(self, code: int, body: dict[str, Any]) -> None:
                raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
                try:
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(raw)
                except Exception as exc:  # noqa: BLE001
                    if _is_client_gone(exc):
                        return
                    raise

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length") or "0")
                if length <= 0:
                    return {}
                try:
                    raw = self.rfile.read(length)
                except Exception as exc:  # noqa: BLE001
                    if _is_client_gone(exc):
                        return {}
                    raise
                try:
                    data = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    return {}
                return data if isinstance(data, dict) else {}

            def do_GET(self) -> None:  # noqa: N802
                if not self._auth_ok():
                    self._json(401, err_result("auth", "unauthorized"))
                    return
                path = urlparse(self.path).path.rstrip("/") or "/"
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
                    body = surface.invoker.run(
                        lambda: ok_result("get_catalog", {"actions": surface.registry.catalog()})
                    )
                    self._json(200, body)
                    return
                if path == "/v1/state":
                    body = surface.invoker.run(
                        lambda: surface.registry.invoke("get_state", {})
                    )
                    self._json(200, body)
                    return
                self._json(404, err_result("http", f"not found: {path}"))

            def do_POST(self) -> None:  # noqa: N802
                if not self._auth_ok():
                    self._json(401, err_result("auth", "unauthorized"))
                    return
                path = urlparse(self.path).path.rstrip("/") or "/"
                payload = self._read_json()
                if path == "/v1/invoke":
                    action = str(payload.get("action") or "").strip()
                    args = payload.get("args")
                    if not isinstance(args, dict):
                        args = {k: v for k, v in payload.items() if k not in ("action", "args")}

                    def _run() -> dict[str, Any]:
                        if surface.booting and action not in (
                            "ping",
                            "get_state",
                            "get_catalog",
                        ):
                            return err_result(action or "invoke", "Iris is still booting")
                        if action in ("ping", "get_catalog", "get_state"):
                            return surface.registry.invoke(action, args)
                        return surface.registry.invoke(action, args)

                    # ponytail: stream write / project.run 은 메인스레드에서 길어질 수 있음
                    timeout = 15.0
                    if action == "project.run":
                        timeout = float(args.get("timeout_sec") or 60) + 30.0
                    elif action == "project.write_file":
                        # open+typewriter 기본 — 타이핑 대기
                        if bool(args.get("open", True)) and bool(
                            args.get("typewriter", args.get("stream", True))
                        ):
                            timeout = 180.0
                        elif bool(args.get("stream")):
                            timeout = 120.0
                    body = surface.invoker.run(_run, timeout=timeout)
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
                bound = candidate
                break
            except OSError as exc:
                last_err = exc
                httpd = None
        if httpd is None:
            raise OSError(f"control surface bind failed on {self.host}:{self.port}+ : {last_err}")

        self._httpd = httpd
        self.bound_port = bound
        write_control_endpoint(host=self.host, port=bound, token=self.token)

        def _serve() -> None:
            assert self._httpd is not None
            self._httpd.serve_forever(poll_interval=0.3)

        self._thread = threading.Thread(target=_serve, name="iris-control-http", daemon=True)
        self._thread.start()
        return bound

    def stop(self) -> None:
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
    allowed = high.invoke("email.send", {"confirm": True})
    assert allowed["ok"] is True
    print("control_surface self-check ok")


if __name__ == "__main__":
    _self_check()
