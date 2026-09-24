"""IDE "실행해줘" 무한 로딩 회귀 방지.

버그 재현 조건 (수정 전):
  1. project_run()의 iris_ide 브릿지 분기에서 t0가 그 아래(비-브릿지 경로)에서만
     정의돼 있어, 브릿지 실행이 성공하든 실패하든 항상 UnboundLocalError로
     끝나 결과가 항상 실패로 보고됐다.
  2. 브릿지 HTTP 호출(client.run_terminal_command)을 Qt 메인 스레드에서 그대로
     blocking 호출해, 브릿지가 응답하지 않거나 명령이 오래 걸리면 앱 전체가
     멈춘 채 로딩이 끝나지 않았다.

이 테스트는 실제 PyQt6 윈도우 없이, project.run 핸들러를 등록하는
_register_actions()에 최소한의 가짜 window를 넣어 iris_ide 브릿지 분기를
직접 실행한다.
"""

from __future__ import annotations

import threading
import time
import types
import unittest
from pathlib import Path

from iris.system.control_surface import ActionRegistry
from iris.ui import control_bindings


class _FakeSession:
    def __init__(self, root: str) -> None:
        self.active = True
        self.mode = "workspace"
        self.workspace_root = root
        self.ide_id = "iris_ide"
        self.hwnd = None
        self.pid = None


class _FakeLiveActivity:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def append_instant_line(self, line: str) -> None:
        self.lines.append(line)


class _FakeBridgeClient:
    """iris.infrastructure.iris_ide_client.IrisIdeClient 대역."""

    def __init__(self, run_terminal_command) -> None:
        self.timeout = 30.0
        self.base_url = "http://127.0.0.1:0"
        self.token = "test-token"
        self._run = run_terminal_command

    def run_terminal_command(self, command: str, *, cwd: str = "") -> dict:
        return self._run(command, cwd=cwd, client=self)


class _FakeSurface:
    def __init__(self) -> None:
        self.registry = ActionRegistry()


def _make_window(tmp_root: str, run_terminal_command):
    win = types.SimpleNamespace()
    win._get_bound_ide_session = lambda refresh=True: _FakeSession(tmp_root)
    win._iris_ide_bridge_client = lambda: _FakeBridgeClient(run_terminal_command)
    win._live_activity = _FakeLiveActivity()
    win._db = None
    return win


def _invoke_project_run(tmp_root: str, run_terminal_command, **extra_args):
    surface = _FakeSurface()
    window = _make_window(tmp_root, run_terminal_command)
    control_bindings._register_actions(window, surface)  # type: ignore[arg-type]
    args = {"project_root": tmp_root, "command": "print(1)", "reveal_terminal": True}
    args.update(extra_args)
    return surface.registry.invoke("project.run", args)


class ProjectRunBridgeNoHangTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_successful_run_reports_ok_and_output(self) -> None:
        """정상 실행되는 경우: t0 UnboundLocalError 없이 성공 결과가 반환돼야 한다."""

        def run_terminal_command(command, *, cwd, client):
            # project.run이 시작 때 로그를 지우므로, 브리지 응답 시점에 다시 쓴다.
            log = Path(cwd) / ".iris" / "last_run.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text("hello from bridge\n", encoding="utf-8")
            return {
                "command": command,
                "queued": True,
                "via": "theia_terminal",
                "cwd": cwd,
            }

        result = _invoke_project_run(self.root, run_terminal_command)
        self.assertTrue(result.get("ok"), result)
        payload = result.get("result") or {}
        self.assertEqual(payload.get("via"), "theia_terminal")
        self.assertEqual(payload.get("ide_terminal"), "ok")
        self.assertFalse(payload.get("timed_out"))
        self.assertFalse(payload.get("running"))

    def test_bridge_exception_returns_clean_error_not_unboundlocalerror(self) -> None:
        """IDE 실행 중 오류 발생: 예전엔 t0 UnboundLocalError로 원인이 가려졌다."""

        def run_terminal_command(command, *, cwd, client):
            raise ConnectionRefusedError("bridge not reachable")

        result = _invoke_project_run(self.root, run_terminal_command)
        self.assertFalse(result.get("ok"))
        self.assertIn("bridge not reachable", str(result.get("error")))
        self.assertNotIn("t0", str(result.get("error")))
        self.assertNotIn("UnboundLocalError", str(result.get("error")))

    def test_bridge_disconnected_fails_fast(self) -> None:
        """IDE와 연결되지 않은 경우: 클라이언트 생성 자체가 실패해도 즉시 에러."""

        surface = _FakeSurface()
        window = _make_window(self.root, lambda *a, **k: {})

        def _no_client():
            raise RuntimeError("iris ide runtime not started")

        window._iris_ide_bridge_client = _no_client
        control_bindings._register_actions(window, surface)  # type: ignore[arg-type]
        t0 = time.monotonic()
        result = surface.registry.invoke(
            "project.run",
            {"project_root": self.root, "command": "print(1)", "reveal_terminal": True},
        )
        elapsed = time.monotonic() - t0
        self.assertFalse(result.get("ok"))
        self.assertLess(elapsed, 2.0, "disconnected bridge must fail fast, not hang")

    def test_hung_bridge_call_times_out_instead_of_blocking_forever(self) -> None:
        """IDE 실행 중 브릿지가 응답하지 않는 경우: 무한 로딩 대신 유한 시간 내 타임아웃.

        run_terminal_command가 절대 반환되지 않는 상황(응답 없는 브릿지/멈춘 프로세스)을
        흉내낸다. 수정 전에는 이 호출이 Qt 메인 스레드를 그대로 막아 무한 로딩이 됐다.
        """
        started = threading.Event()
        release = threading.Event()  # 테스트 종료 후 스레드가 계속 남아있지 않도록

        def run_terminal_command(command, *, cwd, client):
            started.set()
            release.wait(60.0)  # 응답 없는 브릿지 흉내 — 테스트가 끝날 때까지 반환하지 않음
            return {"output": "too late"}

        t0 = time.monotonic()
        result = _invoke_project_run(
            self.root,
            run_terminal_command,
            timeout_sec=1,  # bridge_timeout = max(5, min(1+10, 300)) = 11s → wait cap ~13s
        )
        elapsed = time.monotonic() - t0
        self.assertTrue(started.wait(1.0), "worker thread never started")
        self.assertFalse(result.get("ok"))
        err = str(result.get("error") or "")
        self.assertTrue(
            "did not respond" in err or "bridge call timeout" in err,
            err,
        )
        # bridge_call_pumping timeout=18s + 여유
        self.assertLess(elapsed, 22.0, "project.run must not hang past its own timeout budget")
        release.set()  # 백그라운드 스레드 정리


class ProjectRunOffUiHelperTests(unittest.TestCase):
    def test_fast_function_returns_promptly(self) -> None:
        result, exc, timed_out = control_bindings._run_off_ui_with_timeout(
            lambda: 42, timeout_sec=5.0
        )
        self.assertEqual(result, 42)
        self.assertIsNone(exc)
        self.assertFalse(timed_out)

    def test_exception_is_captured_not_raised(self) -> None:
        def _boom():
            raise ValueError("nope")

        result, exc, timed_out = control_bindings._run_off_ui_with_timeout(
            _boom, timeout_sec=5.0
        )
        self.assertIsNone(result)
        self.assertIsInstance(exc, ValueError)
        self.assertFalse(timed_out)

    def test_never_returning_function_times_out_bounded(self) -> None:
        release = threading.Event()

        def _hang():
            release.wait(5.0)
            return "late"

        t0 = time.monotonic()
        result, exc, timed_out = control_bindings._run_off_ui_with_timeout(
            _hang, timeout_sec=0.2, poll_interval=0.01
        )
        elapsed = time.monotonic() - t0
        self.assertTrue(timed_out)
        self.assertIsNone(result)
        self.assertIsNone(exc)
        self.assertLess(elapsed, 1.0)
        release.set()

    def test_pump_is_called_while_waiting(self) -> None:
        release = threading.Event()
        pump_calls = []

        def _hang():
            release.wait(5.0)

        control_bindings._run_off_ui_with_timeout(
            _hang, timeout_sec=0.15, pump=lambda: pump_calls.append(1), poll_interval=0.01
        )
        release.set()
        self.assertGreater(len(pump_calls), 0, "Qt event loop must keep pumping while waiting")


if __name__ == "__main__":
    unittest.main()
