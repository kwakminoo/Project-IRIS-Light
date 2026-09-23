"""Hermes gateway 진단(G1~G10) 자검 — pytest 없이 바로 실행.

.venv\\Scripts\\python.exe -m iris.system._check_hermes_gateway_diagnostics
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from iris.infrastructure.hermes_client import HealthProbeResult, parse_health_payload
from iris.system import hermes_gateway as gw


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

        # --- G2 env isolation ---
        os.environ["VIRTUAL_ENV"] = str(root / ".venv-iris")
        os.environ["PYTHONPATH"] = str(root)
        with (
            patch.object(gw, "hermes_home", return_value=home),
            patch.object(gw, "_hermes_venv_python", return_value=None),
            patch.object(gw, "_hermes_venv_dir", return_value=root / "no-venv"),
        ):
            cleaned = gw._gateway_child_env()
        assert "PYTHONPATH" not in cleaned
        assert cleaned.get("VIRTUAL_ENV") != str(root / ".venv-iris")
        assert cleaned.get("HERMES_HOME") == str(home)

        # --- G3 stale lock ---
        with patch.object(gw, "hermes_home", return_value=home):
            (home / "gateway.pid").write_text(
                json.dumps({"pid": 999991}), encoding="utf-8"
            )
            (home / "gateway.lock").write_text(
                json.dumps({"pid": 999992}), encoding="utf-8"
            )
            with patch.object(gw, "_pid_exists", return_value=False):
                cleared = gw._clear_stale_gateway_lock()
            assert "gateway.pid" in cleared and "gateway.lock" in cleared

        # --- G9 exe missing ---
        with patch.object(gw, "_build_gateway_cmd", return_value=None):
            assert gw.start_hermes_gateway() is False
        assert gw.get_last_gateway_diagnosis().code == gw.CODE_EXE_MISSING

        # --- G1 crash ---
        err = home / "logs" / "iris-gateway" / "t.err.log"
        err.parent.mkdir(parents=True, exist_ok=True)
        err.write_text("boom\n", encoding="utf-8")
        child = MagicMock()
        child.poll.return_value = 2
        gw._LAST_CHILD = child
        gw._LAST_LOG_PATHS = (err.with_suffix(".out.log"), err)
        with (
            patch.object(gw, "hermes_home", return_value=home),
            patch.object(
                gw,
                "probe_gateway_health",
                return_value=HealthProbeResult(ok=False, code="connection_refused"),
            ),
        ):
            assert gw._wait_until_healthy("http://127.0.0.1:8642/v1", wait_sec=1.5) is False
        assert gw.get_last_gateway_diagnosis().code == gw.CODE_PROCESS_CRASH

        # --- G6 port conflict ---
        with (
            patch.object(
                gw,
                "probe_gateway_health",
                return_value=HealthProbeResult(
                    ok=False, code="bad_body", looks_like_hermes=False
                ),
            ),
            patch.object(gw, "_port_listeners", return_value=[(77, "other.exe")]),
            patch.object(gw, "_pid_looks_like_hermes", return_value=False),
        ):
            diag = gw._diagnose_port_conflict("http://127.0.0.1:8642/v1")
        assert diag is not None and diag.code == gw.CODE_PORT_CONFLICT

        # --- diagnosis file ---
        with patch.object(gw, "hermes_home", return_value=home):
            gw._set_diagnosis(
                gw.GatewayDiagnosis(code=gw.CODE_TIMEOUT, message="timeout demo")
            )
            assert gw.gateway_diagnosis_path().is_file()

        # --- trampoline / runtime probe ---
        assert gw.is_hermes_trampoline_failure(
            "error: uv trampoline failed to spawn Python child process\n"
            "Caused by: entity not found (os error 2)"
        )
        assert not gw.is_hermes_trampoline_failure("connection refused")

        # --- user message has code, no secret ---
        msg = gw.GatewayDiagnosis(
            code=gw.CODE_TIMEOUT,
            message="대기 초과",
            action="재시도",
            stderr_log=str(err),
        ).user_message()
        assert "[TIMEOUT]" in msg
        assert "sk-" not in msg

    print("hermes_gateway diagnostics check ok (G1-G10 harness)")


if __name__ == "__main__":
    _main()
