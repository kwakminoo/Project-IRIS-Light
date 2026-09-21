"""IRIS IDE 브리지 내비게이션 회귀 게이트 — 총괄표 #1 (+ #3 설치본 확인).

실제 Theia·브리지·QWebEngineView를 띄우고, Theia 내부 내비게이션처럼 **쿼리스트링을 잃은
뒤에도** 편집기 상태 전송(push)과 명령 폴링이 계속되는지 확인한다.
`_check_iris_ide_bridge.py`는 프런트엔드 없이 돌아 이 결함을 잡지 못한다 (false-green).

  1. 쿼리 있는 URL 로드 → sessionStorage에 포트·토큰 승계
  2. openFile → 프런트엔드가 실제 실행(bridge_fallback 아님) + languageId 있는 상태 push
  3. setEditorState {} → 설치본 브리지가 null / [] 로 정규화            (#3)
  4. 같은 URL을 **브리지 파라미터 없이** 재로드 (내부 내비게이션 재현)   (#1)
  5. openFile → 여전히 프런트엔드 경유로 동작                           (#1 게이트)

GUI(QWebEngineView)와 Theia 기동이 필요하므로 ~25초 걸린다. IRIS IDE 실행 중에는 돌리지 말 것
(런타임 상태파일을 공유한다).

    .venv\\Scripts\\python.exe -m iris.system._check_iris_ide_bridge_nav
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready


def _self_check() -> None:
    ensure_qt_webengine_ready()

    from PyQt6.QtCore import QEventLoop, QTimer, QUrl
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWidgets import QApplication

    from iris.infrastructure.iris_ide_client import IrisIdeClient
    from iris.system.iris_ide_runtime import shared_iris_ide_runtime

    # ponytail: QApplication([])은 QtWebEngine이 argv[0]을 못 찾아 abort한다 (0xC0000409).
    app = QApplication(sys.argv)
    assert app is not None
    view = QWebEngineView()
    view.resize(1100, 800)
    view.show()

    def log(*parts: object) -> None:
        print(*parts, flush=True)

    def pause(sec: float) -> None:
        loop = QEventLoop()
        QTimer.singleShot(int(sec * 1000), loop.quit)
        loop.exec()

    def call(fn: Callable[[], Any], timeout: float = 30.0) -> Any:
        """브리지 호출은 워커 스레드에서 — Qt 메인 스레드를 막으면 QtWebEngine의
        in-process 네트워크 서비스가 멈춰 페이지가 아예 응답하지 못한다."""
        box: dict[str, Any] = {}

        def run() -> None:
            try:
                box["r"] = fn()
            except Exception as exc:  # noqa: BLE001
                box["e"] = exc

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        deadline = time.monotonic() + timeout
        while worker.is_alive() and time.monotonic() < deadline:
            pause(0.05)
        if "e" in box:
            raise box["e"]
        assert "r" in box, "bridge call timed out"
        return box["r"]

    def js(code: str, timeout: float = 15.0) -> Any:
        loop = QEventLoop()
        box: dict[str, Any] = {}
        view.page().runJavaScript(code, lambda v: (box.__setitem__("v", v), loop.quit()))
        QTimer.singleShot(int(timeout * 1000), loop.quit)
        loop.exec()
        return box.get("v")

    def load(url: str, timeout: float = 180.0) -> bool:
        loop = QEventLoop()
        box: dict[str, Any] = {}

        def done(ok: bool) -> None:
            box["ok"] = ok
            loop.quit()

        view.loadFinished.connect(done)
        view.load(QUrl(url))
        QTimer.singleShot(int(timeout * 1000), loop.quit)
        loop.exec()
        view.loadFinished.disconnect(done)
        return bool(box.get("ok"))

    def wait_shell(timeout: float = 120.0) -> bool:
        for _ in range(int(timeout / 0.5)):
            if js("!!document.querySelector('#theia-app-shell, .theia-ApplicationShell')"):
                return True
            pause(0.5)
        return False

    ws = Path(tempfile.mkdtemp(prefix="iris-ide-nav-"))
    (ws / "a.py").write_text("print('a')\n", encoding="utf-8")
    (ws / "b.py").write_text("print('b')\n", encoding="utf-8")

    runtime = shared_iris_ide_runtime()
    ok, msg = runtime.start(str(ws))
    assert ok, msg
    token = runtime.bridge_token()
    client = IrisIdeClient(base_url=runtime.bridge_base_url(), token=token, timeout=20.0)
    base = runtime.base_url()
    try:
        assert load(f"{base}/?iris_bridge_port={runtime.bridge_port}&iris_bridge_token={token}")
        assert wait_shell(), "theia app shell not ready"
        pause(4.0)
        stored = js("String(sessionStorage.getItem('iris.ide.bridge.port'))")
        assert stored == str(runtime.bridge_port), f"신원 미저장: {stored}"

        out = call(lambda: client.open_file("a.py", line=1, column=1))
        assert out.get("via") != "bridge_fallback", f"폴러 정지: {out}"
        pause(1.5)
        ed = call(client.get_active_editor).get("editor")
        assert ed and "a.py" in str(ed.get("path")), f"경로 미갱신: {ed}"
        assert ed.get("languageId"), f"프런트엔드 push 아님(브리지 폴백 상태): {ed}"
        log("  1·2) 쿼리 있는 기동 — 폴러·push 생존 ok")

        call(lambda: client._request("setEditorState", {}))
        assert call(client.get_active_editor).get("editor") is None, "빈 상태가 {}로 남음"
        assert call(client.get_open_editors).get("editors") == [], "빈 상태가 [{}]로 남음"
        log("  3) 설치본 브리지 빈 편집기 정규화 ok")

        assert load(f"{base}/?iris_nav=1"), "reload failed"
        assert wait_shell(), "theia app shell not ready after reload"
        pause(5.0)
        probe = json.loads(
            js(
                "JSON.stringify({"
                " query: new URLSearchParams(location.search).get('iris_bridge_port'),"
                " stored: sessionStorage.getItem('iris.ide.bridge.port') })"
            )
        )
        assert probe["query"] is None, f"쿼리가 남아 시험이 무효: {probe}"
        assert probe["stored"] == str(runtime.bridge_port), f"승계 실패: {probe}"

        out2 = call(lambda: client.open_file("b.py", line=2, column=1))
        assert out2.get("via") != "bridge_fallback", f"쿼리 소실 후 폴러 정지 (#1 미해결): {out2}"
        pause(1.5)
        ed2 = call(client.get_active_editor).get("editor")
        assert ed2 and "b.py" in str(ed2.get("path")), f"쿼리 소실 후 경로 미갱신: {ed2}"
        assert ed2.get("languageId"), f"쿼리 소실 후 push 정지 (#1 미해결): {ed2}"
        log("  4·5) 쿼리스트링 소실 후에도 상태 전송·명령 폴링 생존 ok")

        # UI 스레드에서 직접 호출 — ide.open_file이 실제로 타는 경로.
        from iris.ui.control_bindings import _bridge_call_pumping

        out3 = _bridge_call_pumping(lambda: client.open_file("a.py", line=1, column=1))
        assert out3.get("via") != "bridge_fallback", f"UI 스레드 호출이 폴백: {out3}"
        log("  6) UI 스레드 호출도 프런트엔드 경유 ok")
    finally:
        runtime.stop()
    print("iris_ide bridge nav ok")


if __name__ == "__main__":
    _self_check()
