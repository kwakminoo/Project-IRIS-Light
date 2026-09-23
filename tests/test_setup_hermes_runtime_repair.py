"""설치 프로토콜 — 깨진 Hermes 런타임 자동 감지·복구.

실행:
  .venv\\Scripts\\python.exe -m unittest tests.test_setup_hermes_runtime_repair -v
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iris.system import hermes_gateway as gw
from iris.system import hermes_install as hi
from iris.system.setup_protocol import SetupProtocol


class SetupHermesRuntimeRepairTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.home = self.root / "hermes"
        self.home.mkdir()
        self._home_patch = patch(
            "iris.system.setup_protocol.hermes_home", lambda: self.home
        )
        self._home_patch.start()
        self._gw_home = patch.object(gw, "hermes_home", lambda: self.home)
        self._gw_home.start()

    def tearDown(self) -> None:
        self._gw_home.stop()
        self._home_patch.stop()
        self._td.cleanup()

    def test_step_hermes_install_detects_broken_runtime(self) -> None:
        proto = SetupProtocol(dry_run=False, simulate=False)
        with (
            patch(
                "iris.system.setup_protocol.probe_hermes_runtime",
                return_value=(False, "uv trampoline failed… entity not found"),
            ),
            patch(
                "iris.system.setup_protocol.hermes_executable",
                return_value=str(self.root / "hermes.exe"),
            ),
        ):
            result = proto._step_hermes_install()
        self.assertEqual(result.status, "needs_user")
        self.assertTrue(result.can_install)
        self.assertIn("깨져", result.message)

    def test_wipe_hermes_agent_keeps_dotenv(self) -> None:
        agent = self.home / "hermes-agent"
        (agent / "venv").mkdir(parents=True)
        (agent / "venv" / "marker.txt").write_text("x", encoding="utf-8")
        env_path = self.home / ".env"
        env_path.write_text("API_SERVER_KEY=keep-me\n", encoding="utf-8")
        proto = SetupProtocol(dry_run=False, simulate=False)
        with (
            patch.object(hi.gw, "stop_hermes_gateway", return_value=True),
            patch.object(hi, "_kill_hermes_tree_holders"),
        ):
            msg = proto._wipe_hermes_agent_runtime()
        self.assertTrue("치움" in msg or "삭제" in msg or "정리" in msg, msg)
        self.assertFalse(agent.exists())
        self.assertTrue(env_path.is_file())
        self.assertIn("keep-me", env_path.read_text(encoding="utf-8"))

    def test_gateway_step_auto_repairs_missing_hermes_cli(self) -> None:
        proto = SetupProtocol(dry_run=False, simulate=False)
        streams: list[str] = []
        proto.bind_stream(lambda t, _p, _r: streams.append(t or ""))
        crash = gw.GatewayDiagnosis(
            code=gw.CODE_PROCESS_CRASH,
            message="gateway 프로세스가 즉시 종료되었습니다 (exit 1).",
            detail=(
                "ModuleNotFoundError: No module named 'hermes_cli'\n"
                "pre_restart_health=timeout:"
            ),
        )
        calls = {"ensure": 0, "install": 0}
        gw._LAST_DIAGNOSIS = crash

        def _ensure(*_a, **_k):
            calls["ensure"] += 1
            if calls["ensure"] == 1:
                gw._LAST_DIAGNOSIS = crash
                return False
            gw._LAST_DIAGNOSIS = gw.GatewayDiagnosis(
                code=gw.CODE_OK, ok=True, message="ok"
            )
            return True

        def _install():
            calls["install"] += 1
            proto._hermes_runtime_repaired = True
            return proto._record_step("hermes_install", "done", "repaired")

        with (
            patch(
                "iris.system.hermes_gateway.is_hermes_gateway_running",
                return_value=False,
            ),
            patch(
                "iris.system.hermes_gateway.ensure_hermes_gateway_running",
                side_effect=_ensure,
            ),
            patch(
                "iris.system.hermes_gateway.restart_hermes_gateway",
                return_value=True,
            ),
            patch(
                "iris.system.hermes_gateway.get_last_gateway_diagnosis",
                side_effect=lambda: gw._LAST_DIAGNOSIS,
            ),
            patch.object(proto, "_install_hermes", side_effect=_install),
            patch(
                "iris.system.setup_protocol.verify_iris_mcp_tools",
                return_value=(True, "mcp ok"),
            ),
            patch(
                "iris.system.setup_protocol.resolve_hermes_api_key",
                return_value="test-key",
            ),
        ):
            result = proto._step_hermes_gateway()

        self.assertEqual(result.status, "done", result)
        self.assertEqual(calls["install"], 1)
        self.assertTrue(any("재설치" in s for s in streams), streams)

    def test_gateway_step_auto_repairs_trampoline_once(self) -> None:
        proto = SetupProtocol(dry_run=False, simulate=False)
        streams: list[str] = []
        proto.bind_stream(lambda t, _p, _r: streams.append(t or ""))
        crash = gw.GatewayDiagnosis(
            code=gw.CODE_PROCESS_CRASH,
            message="gateway 프로세스가 즉시 종료되었습니다 (exit 1).",
            detail=(
                "error: uv trampoline failed to spawn Python child process\n"
                "  Caused by: entity not found (os error 2)"
            ),
        )
        calls = {"ensure": 0, "install": 0}
        gw._LAST_DIAGNOSIS = crash

        def _ensure(*_a, **_k):
            calls["ensure"] += 1
            if calls["ensure"] == 1:
                gw._LAST_DIAGNOSIS = crash
                return False
            gw._LAST_DIAGNOSIS = gw.GatewayDiagnosis(
                code=gw.CODE_OK, ok=True, message="ok"
            )
            return True

        def _install():
            calls["install"] += 1
            proto._hermes_runtime_repaired = True
            return proto._record_step("hermes_install", "done", "repaired")

        with (
            patch(
                "iris.system.hermes_gateway.is_hermes_gateway_running",
                return_value=False,
            ),
            patch(
                "iris.system.hermes_gateway.ensure_hermes_gateway_running",
                side_effect=_ensure,
            ),
            patch(
                "iris.system.hermes_gateway.restart_hermes_gateway",
                return_value=True,
            ),
            patch(
                "iris.system.hermes_gateway.get_last_gateway_diagnosis",
                side_effect=lambda: gw._LAST_DIAGNOSIS,
            ),
            patch.object(proto, "_install_hermes", side_effect=_install),
            patch(
                "iris.system.setup_protocol.verify_iris_mcp_tools",
                return_value=(True, "mcp ok"),
            ),
            patch(
                "iris.system.setup_protocol.resolve_hermes_api_key",
                return_value="test-key",
            ),
        ):
            result = proto._step_hermes_gateway()

        self.assertEqual(result.status, "done", result)
        self.assertEqual(calls["install"], 1)
        self.assertGreaterEqual(calls["ensure"], 1)
        self.assertTrue(
            any("재설치" in s or "trampoline" in s.lower() for s in streams),
            streams,
        )


if __name__ == "__main__":
    unittest.main()
