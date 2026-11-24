"""설치 프로토콜 — 깨진 Hermes 런타임 자동 감지·복구.

실행:
  .venv\\Scripts\\python.exe -m unittest tests.test_setup_hermes_runtime_repair -v
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from iris.engine.types import EngineHome, EngineReady, InternalSidecar
from iris.system import iris_agent_gateway as gw
from iris.system import iris_agent_install as hi
from iris.system.setup_protocol import SetupProtocol


class SetupHermesRuntimeRepairTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.home = self.root / "hermes"
        self.home.mkdir()
        self._home_patch = patch(
            "iris.system.setup_protocol.iris_agent_home", lambda: self.home
        )
        self._home_patch.start()
        self._gw_home = patch.object(gw, "iris_agent_home", lambda: self.home)
        self._gw_home.start()

    def tearDown(self) -> None:
        self._gw_home.stop()
        self._home_patch.stop()
        self._td.cleanup()

    def test_step_iris_agent_install_detects_broken_runtime(self) -> None:
        proto = SetupProtocol(dry_run=False, simulate=False)
        with (
            patch(
                "iris.system.setup_protocol.probe_iris_agent_runtime",
                return_value=(False, "uv trampoline failed… entity not found"),
            ),
            patch(
                "iris.system.setup_protocol.iris_agent_executable",
                return_value=str(self.root / "hermes.exe"),
            ),
        ):
            result = proto._step_iris_agent_install()
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

    def test_gateway_step_uses_engine_ensure_ready(self) -> None:
        """ProductReady path: step does Engine.ensure_ready, not :8642 spawn/repair."""
        proto = SetupProtocol(dry_run=False, simulate=False)
        streams: list[str] = []
        proto.bind_stream(lambda t, _p, _r: streams.append(t or ""))
        engine = MagicMock()
        engine.ensure_ready.return_value = EngineReady(
            InternalSidecar(home=EngineHome(self.home)),
            "engine is ready",
        )
        with (
            patch("iris.engine.shared_engine", return_value=engine),
            patch(
                "iris.system.setup_protocol.sync_iris_control",
                return_value=MagicMock(summary_line=lambda: "sync ok"),
            ),
            patch.object(proto, "_install_iris_agent") as install,
        ):
            result = proto._step_iris_agent_engine()

        self.assertEqual(result.status, "done", result)
        engine.ensure_ready.assert_called_once()
        install.assert_not_called()
        self.assertTrue(any("엔진" in s for s in streams), streams)

    def test_gateway_step_force_restart_resets_engine(self) -> None:
        proto = SetupProtocol(dry_run=False, simulate=False)
        engine = MagicMock()
        engine.ensure_ready.return_value = EngineReady(
            InternalSidecar(home=EngineHome(self.home)),
            "engine is ready",
        )
        with (
            patch("iris.engine.shared_engine", return_value=engine),
            patch("iris.engine.runtime.reset_shared_engine") as reset,
            patch(
                "iris.system.setup_protocol.sync_iris_control",
                return_value=MagicMock(summary_line=lambda: "sync ok"),
            ),
        ):
            result = proto._step_iris_agent_engine(force_restart=True)

        self.assertEqual(result.status, "done", result)
        reset.assert_called_once()
        engine.ensure_ready.assert_called_once()


if __name__ == "__main__":
    unittest.main()
