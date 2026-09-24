"""IRIS IDE 브리지 상태연동 자체점검 — 총괄표 #1·#2·#3.

- #1 브리지 신원: 쿼리 소실 후 sessionStorage 승계 (컴파일된 lib/browser 헬퍼를 node로 실행)
- #2 컨텍스트 예산: 내부 대기 예산 1.5초. 벽시계 전체 소요는 타임아웃 처리 때문에 예산을 조금 넘을 수 있고, 검사는 예산+0.5초다. 1.5초는 전체 호출 상한이 아니다.
- #3 빈 편집기 정규화: setEditorState({}) → editor null / editors []
- #4 오류 본문 보존: 브리지 400의 사유가 "HTTP Error 400"으로 뭉개지지 않는다
- #5 UI 스레드 미차단: 브리지 호출이 전부 _bridge_call_pumping을 거치고, 대기 중 Qt 이벤트가 돈다

`_check_iris_ide_bridge.py`와 달리 라이브 상태파일을 건드리지 않는다 (임시 경로만 사용).
"""

from __future__ import annotations

import http.server
import json
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

from iris.infrastructure.iris_ide_client import IrisIdeClient
from iris.system.iris_ide_runtime import node_executable, runtime_source_dir
from iris.system.win_subprocess import no_window_kwargs

TOKEN = "check-token"


def _post(port: int, command: str, payload: dict | None = None) -> dict:
    req = Request(
        f"http://127.0.0.1:{port}/{command}",
        data=json.dumps(payload or {}).encode("utf-8"),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {TOKEN}")
    with urlopen(req, timeout=5.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _check_empty_editor_state(tmp: Path) -> None:
    """#3 — 브리지가 식별자 없는 상태를 「편집기 없음」으로 정규화한다."""
    bridge = runtime_source_dir() / "bridge" / "standalone-bridge.js"
    assert bridge.is_file(), f"브리지 없음: {bridge}"
    state_file = tmp / "state.json"
    env = os.environ.copy()
    env["IRIS_IDE_BRIDGE_TOKEN"] = TOKEN
    env["IRIS_IDE_BRIDGE_PORT"] = "0"
    env["IRIS_IDE_STATE_FILE"] = str(state_file)
    env["IRIS_IDE_WORKSPACE"] = str(tmp)
    proc = subprocess.Popen(
        [node_executable(), str(bridge)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **no_window_kwargs(),
    )
    try:
        port = 0
        for _ in range(100):
            if state_file.is_file():
                port = int(json.loads(state_file.read_text("utf-8")).get("bridge_port") or 0)
                if port:
                    break
            time.sleep(0.1)
        assert port, "브리지 포트 확보 실패"

        _post(port, "setEditorState", {})
        assert _post(port, "getActiveEditor")["result"]["editor"] is None, "빈 상태가 {}로 남음"
        assert _post(port, "getOpenEditors")["result"]["editors"] == [], "빈 상태가 [{}]로 남음"

        _post(port, "setEditorState", {"path": "a.py", "uri": "file:///a.py", "line": 3})
        editor = _post(port, "getActiveEditor")["result"]["editor"]
        assert editor and editor["path"] == "a.py", f"정상 상태가 버려짐: {editor}"

        _post(port, "setEditorState", {"line": 1})
        assert _post(port, "getActiveEditor")["result"]["editor"] is None, "식별자 없는 부분 상태 통과"
        print("  #3 빈 편집기 정규화 ok")
    finally:
        proc.terminate()
        proc.wait(timeout=10)


class _HalfDeadHandler(http.server.BaseHTTPRequestHandler):
    """health만 응답하고 나머지는 영구 정지 — #2 최악 시나리오."""

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        if self.path != "/health":
            time.sleep(30)
            return
        raw = json.dumps({"ok": True, "result": {"product": "IRIS IDE"}}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a: object) -> None:
        pass


def _check_context_budget() -> None:
    """#2 — 일부 호출이 멈춰도 전체 소요가 예산을 넘지 않고, 도달 실패는 즉시 이탈한다."""
    from iris.system.ide_link import shared_ide_link
    from iris.ui import control_bindings as cb

    budget = cb._IDE_CONTEXT_BUDGET
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _HalfDeadHandler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    original = cb._iris_ide_client
    try:
        cb._iris_ide_client = lambda _w: IrisIdeClient(
            base_url=f"http://127.0.0.1:{port}", token=TOKEN, timeout=30.0
        )
        link = shared_ide_link()
        link.invalidate()
        link._last_editor_path = None
        started = time.monotonic()
        ctx = cb._iris_ide_context(None)
        hung = time.monotonic() - started
        ide = ctx["iris_ide"]
        assert "error" not in ide, f"도달 가능한데 전체 붕괴: {ide}"
        assert set(ide) == {"workspace", "active_editor", "cursor", "selection", "diagnostics"}, ide
        assert hung <= budget + 0.5, f"예산 초과: {hung:.2f}s > {budget}s"

        # 같은 1초 안의 재조회는 캐시 — 브리지 왕복이 없어야 한다.
        started = time.monotonic()
        assert cb._iris_ide_context(None) == ctx
        cached = time.monotonic() - started
        assert cached < 0.2, f"컨텍스트 캐시 미동작: {cached:.2f}s"

        # 브리지 미기동(연결 거부) — 현행과 동일하게 즉시 이탈해야 한다.
        srv.shutdown()
        srv.server_close()
        link.invalidate()
        started = time.monotonic()
        down = cb._iris_ide_context(None)
        refused = time.monotonic() - started
        assert "error" in down["iris_ide"], down
        assert refused <= budget + 0.5, f"미기동 이탈 지연: {refused:.2f}s"
        print(
            f"  #2 예산 ok (부분정지 {hung:.2f}s / 캐시 {cached:.3f}s / 미기동 {refused:.2f}s,"
            f" 내부 예산 {budget}s, 벽시계 허용 +0.5s)"
        )
    finally:
        cb._iris_ide_client = original
        shared_ide_link().close()


class _BadRequestHandler(http.server.BaseHTTPRequestHandler):
    """브리지처럼 사유를 본문 JSON에 담아 400을 낸다 — #4."""

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        raw = json.dumps({"ok": False, "error": "frontend command timeout"}).encode("utf-8")
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a: object) -> None:
        pass


def _check_error_body_preserved() -> None:
    """#4 — 400 응답의 사유가 클라이언트 예외 메시지까지 살아 온다."""
    from iris.infrastructure.iris_ide_client import IrisIdeClientError

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _BadRequestHandler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        client = IrisIdeClient(
            base_url=f"http://127.0.0.1:{srv.server_address[1]}", token=TOKEN, timeout=5.0
        )
        try:
            client.run_terminal_command("echo hi")
        except IrisIdeClientError as exc:
            msg = str(exc)
            kind = exc.code
        else:
            raise AssertionError("400인데 예외가 안 남")
        assert "frontend command timeout" in msg, f"사유가 뭉개짐: {msg}"
        assert kind == "execution", kind
        print("  #4 오류 본문 보존 ok")
    finally:
        srv.shutdown()
        srv.server_close()


def _check_no_blocking_bridge_calls() -> None:
    """#5 — 브리지 호출 래핑 누락 금지 + 대기 중 Qt 이벤트 루프가 실제로 돈다."""
    import re

    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    from iris.ui import control_bindings as cb

    src = Path(cb.__file__).read_text(encoding="utf-8")
    unwrapped = [
        ln.strip()
        for ln in src.splitlines()
        if re.search(r"\bclient\.\w+\(", ln) and "_bridge_call_pumping" not in ln and "lambda:" not in ln
    ]
    assert not unwrapped, f"UI 스레드를 막는 브리지 호출: {unwrapped}"

    app = QApplication.instance() or QApplication([])
    ticked: list[int] = []
    QTimer.singleShot(50, lambda: ticked.append(1))
    cb._bridge_call_pumping(lambda: time.sleep(0.4), timeout=5.0)
    assert ticked, "_bridge_call_pumping 대기 중 Qt 이벤트가 멈춤"
    assert app is not None
    print(f"  #5 브리지 호출 비차단 ok (래핑 {src.count('_bridge_call_pumping(lambda')}건)")


_IDENTITY_STUB = r"""
const path = process.argv[2];
let search = '?iris_bridge_port=4321&iris_bridge_token=tok-a&iris_control_port=8765&iris_control_token=ctl-a';
const bag = {};
global.window = {
    get location() { return { search }; },
    sessionStorage: {
        getItem: k => (k in bag ? bag[k] : null),
        setItem: (k, v) => { bag[k] = String(v); },
    },
};
const { resolveBridgeIdentity, resolveControlIdentity } = require(path);

const first = resolveBridgeIdentity();
if (first.port !== 4321 || first.token !== 'tok-a') throw new Error('query read failed');
const ctl = resolveControlIdentity();
if (ctl.port !== 8765 || ctl.token !== 'ctl-a') throw new Error('control query read failed');

search = '';  // Theia 내부 내비게이션으로 쿼리 소실
const after = resolveBridgeIdentity();
if (after.port !== 4321 || after.token !== 'tok-a') throw new Error('session fallback failed');
if (resolveControlIdentity().token !== 'ctl-a') throw new Error('control session fallback failed');

search = '?iris_bridge_port=9999&iris_bridge_token=tok-b&iris_control_port=9000&iris_control_token=ctl-b';
const rotated = resolveBridgeIdentity();
if (rotated.port !== 9999 || rotated.token !== 'tok-b') throw new Error('rotation not applied');
const ctlRotated = resolveControlIdentity();
if (ctlRotated.port !== 9000 || ctlRotated.token !== 'ctl-b') throw new Error('control rotation not applied');
search = '';
if (resolveBridgeIdentity().token !== 'tok-b') throw new Error('rotation not persisted');
if (resolveControlIdentity().port !== 9000 || resolveControlIdentity().token !== 'ctl-b') {
    throw new Error('control rotation not persisted');
}

console.log('ok');
"""


def _check_bridge_identity(tmp: Path) -> None:
    """#1 — 쿼리 소실 후에도 포트·토큰이 유지되고, 재기동 시 회전값으로 덮인다."""
    compiled = runtime_source_dir() / "lib" / "browser" / "iris-ide-bridge-identity.js"
    assert compiled.is_file(), f"컴파일 산출물 없음 (tsc 먼저): {compiled}"
    stub = tmp / "identity_stub.js"
    stub.write_text(_IDENTITY_STUB, encoding="utf-8")
    out = subprocess.run(
        [node_executable(), str(stub), str(compiled)],
        capture_output=True,
        text=True,
        timeout=60,
        **no_window_kwargs(),
    )
    assert out.returncode == 0 and "ok" in out.stdout, out.stderr or out.stdout
    print("  #1 브리지 신원 승계 ok")


def _self_check() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-ide-bridge-state-") as raw:
        tmp = Path(raw)
        _check_bridge_identity(tmp)
        _check_empty_editor_state(tmp)
    _check_context_budget()
    _check_error_body_preserved()
    _check_no_blocking_bridge_calls()
    print("iris_ide bridge state ok")


if __name__ == "__main__":
    _self_check()
