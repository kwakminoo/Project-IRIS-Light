"""연번 14 — 명령과 편집기 상태를 나누는 IdeLink. 라이브 상태파일은 쓰지 않는다."""

from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from iris.infrastructure.iris_ide_client import IrisIdeClientError
from iris.system.ide_link import IdeLink, editor_path, query_failure


class _Runtime:
    def __init__(self, port: int, token: str = "tok") -> None:
        self.bridge_port = port
        self._token = token

    def bridge_base_url(self) -> str:
        return f"http://127.0.0.1:{self.bridge_port}"

    def bridge_token(self) -> str:
        return self._token


def _server(handler: type[BaseHTTPRequestHandler]) -> tuple[ThreadingHTTPServer, threading.Thread]:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    srv.daemon_threads = True
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, thread


def _stop(srv: ThreadingHTTPServer) -> None:
    srv.shutdown()
    srv.server_close()


class _Files(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        body = json.loads(raw.decode("utf-8") or "{}")
        if self.path == "/openFile":
            if body.get("path") == "missing.py":
                payload = {"ok": False, "error": "not found"}
                code = 400
            elif body.get("path") == "slow.py":
                time.sleep(5)
                return
            elif body.get("path") == "fallback.py":
                payload = {"ok": True, "result": {"via": "bridge_fallback", "path": "fallback.py"}}
                code = 200
            else:
                payload = {
                    "ok": True,
                    "result": {"via": "theia", "path": body.get("path"), "line": body.get("line")},
                }
                code = 200
        elif self.path == "/getActiveEditor":
            payload = {"ok": True, "result": {"editor": {"path": "a.py", "uri": "file:///a.py"}}}
            code = 200
        elif self.path == "/getOpenEditors":
            payload = {"ok": True, "result": {"editors": [{"path": "a.py"}]}}
            code = 200
        else:
            payload = {"ok": True, "result": {}}
            code = 200
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a: object) -> None:
        pass


class _Empty(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        if self.path == "/getActiveEditor":
            payload = {"ok": True, "result": {"editor": None}}
        elif self.path == "/getOpenEditors":
            payload = {"ok": True, "result": {"editors": []}}
        else:
            payload = {"ok": True, "result": {}}
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a: object) -> None:
        pass


class _Junk(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        raw = b"not-json"
        self.send_response(200)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a: object) -> None:
        pass


def check_bad_json() -> None:
    from iris.infrastructure.iris_ide_client import IrisIdeClient

    srv, _thread = _server(_Junk)
    try:
        client = IrisIdeClient(base_url=f"http://127.0.0.1:{srv.server_address[1]}", timeout=2.0)
        try:
            client.health()
        except IrisIdeClientError as exc:
            assert str(exc) == "invalid JSON from bridge" and exc.code == "protocol", exc
        else:
            raise AssertionError("깨진 JSON이 성공으로 남음")
    finally:
        _stop(srv)


def check_commands() -> None:
    srv, _thread = _server(_Files)
    try:
        link = IdeLink(_Runtime(srv.server_address[1]))
        opened = link.open_file("hello.py", line=3, column=1)
        assert opened.get("via") == "theia" and opened.get("path") == "hello.py", opened
        try:
            link.open_file("missing.py")
        except IrisIdeClientError as exc:
            assert "not found" in str(exc) and exc.code == "execution", exc
        else:
            raise AssertionError("실패가 성공으로 남음")
        started = time.monotonic()
        try:
            link.open_file("slow.py", timeout=0.3)
        except IrisIdeClientError as exc:
            assert exc.code == "timeout", exc
            assert time.monotonic() - started < 1.5, "타임아웃이 늦음"
        else:
            raise AssertionError("타임아웃이 성공으로 남음")
        fallback = link.open_file("fallback.py")
        assert fallback.get("via") == "bridge_fallback"
        assert fallback.get("via") != "theia", "bridge_fallback을 실제 개방으로 보면 안 됨"
    finally:
        _stop(srv)


def check_state_and_subscription() -> None:
    srv, _thread = _server(_Files)
    try:
        link = IdeLink(_Runtime(srv.server_address[1]))
        seen: list[str] = []
        off = link.subscribe(lambda snap: seen.append(str(snap["iris_ide"]["active_editor"]["path"])))
        client = link.client()
        first = link.editor_state(client)
        assert first["iris_ide"]["active_editor"]["path"] == "a.py"
        link.editor_state(client)
        assert seen == ["a.py"], seen
        link.invalidate()
        link.editor_state(client)
        assert seen == ["a.py"], f"같은 편집기 재알림: {seen}"
        off()
        link._last_editor_path = None
        link.invalidate()
        link.editor_state(client)
        assert seen == ["a.py"], f"해제 후에도 호출: {seen}"
        link.close()
        assert link._listeners == [] and link._client is None
    finally:
        _stop(srv)

    empty_srv, _thread = _server(_Empty)
    try:
        link = IdeLink(_Runtime(empty_srv.server_address[1]))
        state = link.editor_state(link.client())
        assert state["iris_ide"]["active_editor"] is None
        editors = link.client().get_open_editors()
        assert editors.get("editors") == []
        link.close()
    finally:
        _stop(empty_srv)


class _EditorDown(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        if self.path == "/getActiveEditor":
            self.send_response(500)
            self.end_headers()
            return
        payload = {"ok": True, "result": {}}
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a: object) -> None:
        pass


def check_empty_is_not_query_failure() -> None:
    down, _thread = _server(_EditorDown)
    try:
        link = IdeLink(_Runtime(down.server_address[1]))
        state = link.editor_state(link.client())
        editor = state["iris_ide"]["active_editor"]
        assert isinstance(editor, dict) and editor.get("error") and editor.get("code") == "server", editor
        link.close()
    finally:
        _stop(down)


def check_listener_isolation() -> None:
    srv, _thread = _server(_Files)
    try:
        link = IdeLink(_Runtime(srv.server_address[1]))
        seen: list[str] = []
        notes: list[str] = []

        def boom(_snap: dict) -> None:
            raise RuntimeError("listener")

        class _Catch(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                notes.append(record.getMessage())

        handler = _Catch()
        log = logging.getLogger("iris.system.ide_link")
        log.addHandler(handler)
        log.setLevel(logging.WARNING)
        try:
            link.subscribe(boom)
            link.subscribe(lambda snap: seen.append(editor_path(snap["iris_ide"]["active_editor"]) or ""))
            link.editor_state(link.client())
        finally:
            log.removeHandler(handler)
        assert seen == ["a.py"], seen
        assert any("listener failed" in note for note in notes), notes
        link.close()
    finally:
        _stop(srv)


def check_error_object_is_not_an_editor() -> None:
    failed = {"error": "timed out"}
    assert query_failure(failed)
    assert editor_path(failed) is None
    assert editor_path(None) is None
    assert editor_path({"path": "a.py", "line": 1}) == "a.py"
    for field in (failed, {"error": "budget"}):
        assert not isinstance(field, list)
        assert editor_path(field) is None


class _Flicker(BaseHTTPRequestHandler):
    phase = {"n": 0}

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        if self.path == "/getActiveEditor":
            n = _Flicker.phase["n"]
            _Flicker.phase["n"] = n + 1
            if n == 1:
                self.send_response(500)
                self.end_headers()
                return
            editor = {"path": "a.py", "uri": "file:///a.py"}
        else:
            editor = None
        if self.path == "/getActiveEditor":
            payload = {"ok": True, "result": {"editor": editor}}
        else:
            payload = {"ok": True, "result": {}}
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a: object) -> None:
        pass


def check_failure_does_not_renotify() -> None:
    _Flicker.phase["n"] = 0
    srv, _thread = _server(_Flicker)
    try:
        link = IdeLink(_Runtime(srv.server_address[1]))
        seen: list[str | None] = []
        link.subscribe(lambda snap: seen.append(editor_path(snap["iris_ide"]["active_editor"])))
        link.editor_state(link.client())
        link.invalidate()
        failed = link.editor_state(link.client())
        assert query_failure(failed["iris_ide"]["active_editor"])
        link.invalidate()
        link.editor_state(link.client())
        assert seen == ["a.py"], seen
        link.close()
    finally:
        _stop(srv)


def check_client_error_codes() -> None:
    """HTTP 상태·본문 code로만 나눈다. 문구에 timeout이 있어도 code가 없으면 실행 실패."""
    from iris.infrastructure.iris_ide_client import IrisIdeClient

    class _Kinds(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            path = self.path
            if path == "/exec":
                raw, status = json.dumps({"ok": False, "error": "not found"}).encode(), 400
            elif path == "/timed":
                raw, status = json.dumps(
                    {"ok": False, "error": "frontend command timeout", "code": "timeout"}
                ).encode(), 400
            elif path == "/auth":
                raw, status = json.dumps({"ok": False, "error": "unauthorized"}).encode(), 401
            elif path == "/forbid":
                raw, status = json.dumps({"ok": False, "error": "forbidden"}).encode(), 403
            elif path == "/down":
                raw, status = b"nope", 500
            elif path == "/gateway":
                raw, status = b"", 504
            elif path == "/over":
                raw, status = json.dumps(
                    {"ok": False, "error": "frontend command timeout", "code": "execution"}
                ).encode(), 504
            elif path == "/junk":
                raw, status = b"not-json", 200
            elif path == "/odd":
                raw, status = b"[]", 200
            else:
                raw, status = json.dumps({"ok": False, "error": "bridge error"}).encode(), 200
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *a: object) -> None:
            pass

    srv, _thread = _server(_Kinds)
    try:
        client = IrisIdeClient(base_url=f"http://127.0.0.1:{srv.server_address[1]}", token="tok", timeout=2.0)
        cases = (
            ("exec", "execution", "not found"),
            ("timed", "timeout", "frontend command timeout"),
            ("auth", "auth", "unauthorized"),
            ("forbid", "auth", "forbidden"),
            ("down", "server", ""),
            ("gateway", "timeout", ""),
            ("over", "execution", "frontend command timeout"),
            ("junk", "protocol", "invalid JSON"),
            ("odd", "protocol", "unexpected bridge response"),
            ("plain", "execution", "bridge error"),
        )
        for command, kind, snippet in cases:
            try:
                client._request(command)
            except IrisIdeClientError as exc:
                assert type(exc) is IrisIdeClientError and exc.code == kind, (command, exc.code, exc)
                if snippet:
                    assert snippet in str(exc), (command, exc)
            else:
                raise AssertionError(command)
        import socket

        reset = socket.socket()
        reset.bind(("127.0.0.1", 0))
        reset.listen(1)
        reset_port = reset.getsockname()[1]

        def _drop() -> None:
            conn, _addr = reset.accept()
            conn.close()
            reset.close()

        threading.Thread(target=_drop, daemon=True).start()
        dead = IrisIdeClient(
            base_url=f"http://127.0.0.1:{reset_port}", token="tok", timeout=2.0
        )
        try:
            dead.health()
        except IrisIdeClientError as exc:
            assert exc.code == "connection", exc
            bridge_text = str(exc)
        else:
            raise AssertionError("closed port")
        from iris.mcp.iris_control_stdio import _tool_result
        from iris.system.control_surface import err_result

        bridge_fail = err_result("ide.open_file", bridge_text)
        assert "transport" not in bridge_fail
        assert _tool_result(bridge_fail)["isError"] is False
        stuffed = dict(bridge_fail)
        stuffed["code"] = "connection"
        assert _tool_result(stuffed)["isError"] is False
    finally:
        _stop(srv)


def check_reconnect_and_callers() -> None:
    runtime = _Runtime(9, token="a")
    link = IdeLink(runtime)
    first = link.client()
    assert first.token == "a"
    runtime._token = "b"
    again = link.client()
    assert again is not first and again.token == "b"
    ident = link.page_identity()
    assert ident.port == 9 and ident.token == "b"
    link.close()
    assert link._client is None

    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    window = (root / "ui" / "window" / "main_window.py").read_text(encoding="utf-8")
    assert "bridge_token()" not in window
    worker = (root / "ui" / "workers" / "boot_checks_worker.py").read_text(encoding="utf-8")
    assert "bridge_token" not in worker


def main() -> None:
    check_commands()
    check_bad_json()
    check_state_and_subscription()
    check_empty_is_not_query_failure()
    check_error_object_is_not_an_editor()
    check_failure_does_not_renotify()
    check_listener_isolation()
    check_client_error_codes()
    check_reconnect_and_callers()
    print("ide link ok")


if __name__ == "__main__":
    main()
