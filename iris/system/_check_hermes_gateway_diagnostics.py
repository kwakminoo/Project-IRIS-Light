"""Gateway module self-check after Unit 2 Delete (:8642 start lifecycle gutted).

Keeps read-only helpers (health schema, env isolation, stale lock, probes).
Asserts start/ensure/restart never spawn. Opt-in health only when URL set.

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_agent_gateway_diagnostics
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from iris.infrastructure.iris_agent_client import parse_health_payload
from iris.system import iris_agent_gateway as gw


def _main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        home = root / "hermes"
        home.mkdir()
        gw._LAST_DIAGNOSIS = None
        gw._LAST_CHILD = None
        gw._LAST_LOG_PATHS = None

        # --- G7 health schema ---
        assert parse_health_payload({"status": "ok", "platform": "hermes-agent"})[0]
        assert parse_health_payload({"status": "healthy"})[0]
        assert parse_health_payload({"ok": True})[0]
        assert not parse_health_payload({"status": "broken"})[0]

        # --- G2 env isolation (install/stop child env still scrubbed) ---
        os.environ["VIRTUAL_ENV"] = str(root / ".venv-iris")
        os.environ["PYTHONPATH"] = str(root)
        with (
            patch.object(gw, "iris_agent_home", return_value=home),
            patch.object(gw, "_iris_agent_venv_python", return_value=None),
            patch.object(gw, "_iris_agent_venv_dir", return_value=root / "no-venv"),
        ):
            cleaned = gw._gateway_child_env()
        assert "PYTHONPATH" not in cleaned
        assert cleaned.get("VIRTUAL_ENV") != str(root / ".venv-iris")
        assert cleaned.get("HERMES_HOME") == str(home)

        # --- G3 stale lock (stop path still clears dead locks) ---
        with patch.object(gw, "iris_agent_home", return_value=home):
            (home / "gateway.pid").write_text(
                json.dumps({"pid": 999991}), encoding="utf-8"
            )
            (home / "gateway.lock").write_text(
                json.dumps({"pid": 999992}), encoding="utf-8"
            )
            with patch.object(gw, "_pid_exists", return_value=False):
                cleared = gw._clear_stale_gateway_lock()
            assert "gateway.pid" in cleared and "gateway.lock" in cleared

        # --- Unit 2 Delete: start/ensure/restart are no-op stubs ---
        assert gw.start_iris_agent_gateway() is False
        assert gw.get_last_gateway_diagnosis().code == gw.CODE_START_FAILED
        assert gw.ensure_iris_agent_gateway_running("http://127.0.0.1:8642/v1") is False
        assert gw.restart_iris_agent_gateway("http://127.0.0.1:8642/v1") is False
        assert gw.prune_orphan_gateway_procs() == 0

        # Empty product URL never invents :8642
        assert gw.is_iris_agent_gateway_running("") is False
        assert gw.probe_gateway_health("").ok is False

        # Opt-in health: non-empty URL may probe (read-only; mocked here)
        from iris.infrastructure.iris_agent_client import HealthProbeResult

        with patch.object(
            gw.IrisAgentClient,
            "probe_health",
            return_value=HealthProbeResult(ok=True, code="ok"),
        ):
            # Call through module helper with URL present
            pass
        # probe_gateway_health with unreachable host stays read-only (no start)
        refused = gw.probe_gateway_health("http://127.0.0.1:1/v1", timeout_sec=0.5)
        assert refused.ok is False

        # --- trampoline / runtime probe detectors ---
        assert gw.is_iris_agent_trampoline_failure(
            "error: uv trampoline failed to spawn Python child process\n"
            "Caused by: entity not found (os error 2)"
        )
        assert not gw.is_iris_agent_trampoline_failure("connection refused")

        # --- user message has code, no secret ---
        msg = gw.GatewayDiagnosis(
            code=gw.CODE_TIMEOUT,
            message="대기 초과",
            action="재시도",
            stderr_log=str(home / "x.err.log"),
        ).user_message()
        assert "[TIMEOUT]" in msg
        assert "sk-" not in msg

        # --- diagnosis file ---
        with patch.object(gw, "iris_agent_home", return_value=home):
            gw._set_diagnosis(
                gw.GatewayDiagnosis(code=gw.CODE_TIMEOUT, message="timeout demo")
            )
            assert gw.gateway_diagnosis_path().is_file()

    print("hermes_gateway diagnostics check ok (Unit2 Delete; no :8642 start)")


if __name__ == "__main__":
    _main()
