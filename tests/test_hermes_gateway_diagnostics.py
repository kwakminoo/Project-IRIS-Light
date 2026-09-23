"""Hermes gateway 설치 진단 — 타 PC 실패 모드(G1~G10) 재현 검증.

실제 Hermes 기동 없이 mock/임시 파일로 판정 로직만 검증한다.
실행:
  .venv\\Scripts\\python.exe -m unittest tests.test_hermes_gateway_diagnostics -v
  .venv\\Scripts\\python.exe -m iris.system._check_hermes_gateway_diagnostics
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from iris.infrastructure.hermes_client import HealthProbeResult, parse_health_payload
from iris.system import hermes_gateway as gw


class GatewayDiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.home = self.root / "hermes"
        self.home.mkdir()
        gw._LAST_DIAGNOSIS = None
        gw._LAST_CHILD = None
        gw._LAST_LOG_PATHS = None
        self._home_patch = patch.object(gw, "hermes_home", lambda: self.home)
        self._home_patch.start()

    def tearDown(self) -> None:
        self._home_patch.stop()
        self._td.cleanup()

    def test_g2_polluted_virtual_env_stripped(self) -> None:
        """G2: Iris VIRTUAL_ENV/PYTHONPATH 가 Hermes 자식 env 로 새지 않음."""
        iris_venv = self.root / ".venv-iris"
        iris_venv.mkdir()
        os.environ["VIRTUAL_ENV"] = str(iris_venv)
        os.environ["PYTHONPATH"] = str(self.root / "src")
        os.environ["PYTHONHOME"] = str(self.root / "pyhome")
        with (
            patch.object(gw, "_hermes_venv_python", return_value=None),
            patch.object(gw, "_hermes_venv_dir", return_value=self.root / "missing-venv"),
        ):
            env = gw._gateway_child_env()
        self.assertNotEqual(env.get("VIRTUAL_ENV"), str(iris_venv))
        self.assertNotIn("PYTHONPATH", env)
        self.assertNotIn("PYTHONHOME", env)
        self.assertEqual(env.get("HERMES_HOME"), str(self.home))
        self.assertEqual(env.get("API_SERVER_ENABLED"), "true")

    def test_g2_hermes_venv_overrides_iris(self) -> None:
        hermes_venv = self.root / "hermes-agent" / "venv"
        scripts = hermes_venv / "Scripts"
        scripts.mkdir(parents=True)
        (scripts / "python.exe").write_text("", encoding="utf-8")
        os.environ["VIRTUAL_ENV"] = str(self.root / ".venv-iris")
        os.environ["PYTHONPATH"] = "polluted"
        with patch.object(gw, "_hermes_agent_dir", return_value=self.root / "hermes-agent"):
            env = gw._gateway_child_env()
        self.assertEqual(env["VIRTUAL_ENV"], str(hermes_venv))
        self.assertNotIn("PYTHONPATH", env)

    def test_g3_stale_pid_and_lock_cleared(self) -> None:
        pid_path = self.home / "gateway.pid"
        lock_path = self.home / "gateway.lock"
        pid_path.write_text(json.dumps({"pid": 999999}), encoding="utf-8")
        lock_path.write_text(json.dumps({"pid": 999998}), encoding="utf-8")
        with patch.object(gw, "_pid_exists", return_value=False):
            cleared = gw._clear_stale_gateway_lock()
        self.assertIn("gateway.pid", cleared)
        self.assertIn("gateway.lock", cleared)
        self.assertFalse(pid_path.exists())
        self.assertFalse(lock_path.exists())

    def test_g3_live_hermes_lock_preserved(self) -> None:
        lock_path = self.home / "gateway.lock"
        lock_path.write_text(json.dumps({"pid": 4242}), encoding="utf-8")
        with (
            patch.object(gw, "_pid_exists", return_value=True),
            patch.object(gw, "_pid_looks_like_hermes", return_value=True),
        ):
            cleared = gw._clear_stale_gateway_lock()
        self.assertNotIn("gateway.lock", cleared)
        self.assertTrue(lock_path.exists())

    def test_g3_pid_reuse_non_hermes_cleared(self) -> None:
        lock_path = self.home / "gateway.lock"
        lock_path.write_text(json.dumps({"pid": 111}), encoding="utf-8")
        with (
            patch.object(gw, "_pid_exists", return_value=True),
            patch.object(gw, "_pid_looks_like_hermes", return_value=False),
        ):
            cleared = gw._clear_stale_gateway_lock()
        self.assertIn("gateway.lock", cleared)
        self.assertFalse(lock_path.exists())

    def test_g6_port_conflict_diagnosis(self) -> None:
        foreign = HealthProbeResult(
            ok=True,
            code="ok",
            url="http://127.0.0.1:8642/health",
            body_summary='{"status":"ok"}',
            looks_like_hermes=False,
        )
        with (
            patch.object(gw, "probe_gateway_health", return_value=foreign),
            patch.object(gw, "_port_listeners", return_value=[(5555, "nginx.exe")]),
            patch.object(gw, "_pid_looks_like_hermes", return_value=False),
        ):
            diag = gw._diagnose_port_conflict("http://127.0.0.1:8642/v1")
        self.assertIsNotNone(diag)
        assert diag is not None
        self.assertEqual(diag.code, gw.CODE_PORT_CONFLICT)
        self.assertEqual(diag.port_owner_pid, 5555)
        self.assertIn("nginx", diag.port_owner_name)

    def test_g1_process_crash_during_wait(self) -> None:
        err = self.home / "logs" / "iris-gateway" / "crash.err.log"
        err.parent.mkdir(parents=True, exist_ok=True)
        err.write_text("ImportError: pydantic_core\n", encoding="utf-8")
        child = MagicMock()
        child.poll.return_value = 1
        gw._LAST_CHILD = child
        gw._LAST_LOG_PATHS = (err.with_suffix(".out.log"), err)
        refused = HealthProbeResult(ok=False, code="connection_refused", detail="refused")
        with patch.object(gw, "probe_gateway_health", return_value=refused):
            ok = gw._wait_until_healthy("http://127.0.0.1:8642/v1", wait_sec=2.0)
        self.assertFalse(ok)
        diag = gw.get_last_gateway_diagnosis()
        self.assertIsNotNone(diag)
        assert diag is not None
        self.assertEqual(diag.code, gw.CODE_PROCESS_CRASH)
        self.assertEqual(diag.exit_code, 1)
        self.assertIn("pydantic", diag.detail or "")

    def test_g4_timeout_records_snapshot(self) -> None:
        child = MagicMock()
        child.poll.return_value = None
        gw._LAST_CHILD = child
        slow = HealthProbeResult(ok=False, code="timeout", detail="timeout")
        with patch.object(gw, "probe_gateway_health", return_value=slow):
            ok = gw._wait_until_healthy("http://127.0.0.1:8642/v1", wait_sec=1.0)
        self.assertFalse(ok)
        diag = gw.get_last_gateway_diagnosis()
        self.assertIsNotNone(diag)
        assert diag is not None
        self.assertIn(
            diag.code,
            (gw.CODE_TIMEOUT, gw.CODE_SECURITY_BLOCK, gw.CODE_HEALTH_REFUSED),
        )

    def test_g7_health_status_variants(self) -> None:
        self.assertTrue(parse_health_payload({"status": "ok", "platform": "hermes-agent"})[0])
        self.assertTrue(parse_health_payload({"status": "healthy"})[0])
        self.assertTrue(parse_health_payload({"ok": True})[0])
        self.assertFalse(parse_health_payload({"status": "down"})[0])
        alive, looks, _ = parse_health_payload(
            {"status": "ok", "platform": "hermes-agent", "version": "0.20.5"}
        )
        self.assertTrue(alive and looks)

    def test_g9_exe_missing(self) -> None:
        with patch.object(gw, "_build_gateway_cmd", return_value=None):
            ok = gw.start_hermes_gateway()
        self.assertFalse(ok)
        diag = gw.get_last_gateway_diagnosis()
        self.assertIsNotNone(diag)
        assert diag is not None
        self.assertEqual(diag.code, gw.CODE_EXE_MISSING)

    def test_g5_api_server_disabled(self) -> None:
        with (
            patch.object(
                gw, "_build_gateway_cmd", return_value=["python", "-m", "hermes"]
            ),
            patch.object(
                gw,
                "_gateway_child_env",
                return_value={"API_SERVER_ENABLED": "false", "HERMES_HOME": "x"},
            ),
            patch.object(
                gw,
                "probe_gateway_health",
                return_value=HealthProbeResult(ok=False, code="connection_refused"),
            ),
            patch.object(gw, "_diagnose_port_conflict", return_value=None),
            patch.object(gw, "_clear_stale_gateway_lock", return_value=[]),
            patch.object(gw, "_windows_gateway_procs_alive", return_value=False),
            patch.object(gw, "_gateway_lock_path", return_value=Path("no-lock-file")),
        ):
            ok = gw.ensure_hermes_gateway_running(
                "http://127.0.0.1:8642/v1", wait_sec=1.0
            )
        self.assertFalse(ok)
        diag = gw.get_last_gateway_diagnosis()
        self.assertIsNotNone(diag)
        assert diag is not None
        self.assertEqual(diag.code, gw.CODE_ENV_POLLUTION)

    def test_g10_user_message_no_secret_values(self) -> None:
        diag = gw.GatewayDiagnosis(
            code=gw.CODE_TIMEOUT,
            message="gateway /health 응답 대기 시간이 초과되었습니다.",
            action="(참고: API 키 문제는 /health와 무관합니다 — 채팅 단계에서 진단됩니다.)",
            has_api_key=False,
        )
        text = diag.user_message()
        self.assertIn("API 키", text)
        self.assertNotIn("sk-", text)
        self.assertNotIn("sk-", diag.copy_text())

    def test_diagnosis_persisted(self) -> None:
        gw._set_diagnosis(
            gw.GatewayDiagnosis(
                code=gw.CODE_PORT_CONFLICT,
                message="포트 충돌",
                action="종료 후 재시도",
                port_owner_pid=1,
                port_owner_name="x.exe",
            )
        )
        path = gw.gateway_diagnosis_path()
        self.assertTrue(path.is_file())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["code"], gw.CODE_PORT_CONFLICT)

    def test_ensure_short_circuits_when_healthy(self) -> None:
        healthy = HealthProbeResult(
            ok=True,
            code="ok",
            url="http://127.0.0.1:8642/health",
            looks_like_hermes=True,
            body_summary='{"status":"ok"}',
        )
        with patch.object(gw, "probe_gateway_health", return_value=healthy):
            self.assertTrue(
                gw.ensure_hermes_gateway_running("http://127.0.0.1:8642/v1")
            )
        diag = gw.get_last_gateway_diagnosis()
        self.assertIsNotNone(diag)
        assert diag is not None
        self.assertTrue(diag.ok)


if __name__ == "__main__":
    unittest.main()
