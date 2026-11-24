"""Unit 3 — Product surface no longer treats :8642 ExternalGateway as product."""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

from iris.config.settings import Settings, load_settings
from iris.system.setup_protocol import CORE_STEP_IDS, CORE_STEP_LABELS


_ROOT = Path(__file__).resolve().parents[2]
_NO_DOTENV = Path("__iris_gateway_retired_no_dotenv__")


def _check_setup_step_renamed() -> None:
    assert "hermes_gateway" not in CORE_STEP_IDS
    assert "iris_agent_engine" in CORE_STEP_IDS
    assert "hermes_gateway" not in CORE_STEP_LABELS
    assert CORE_STEP_LABELS["iris_agent_engine"]


def _check_domain_sidecar_only() -> None:
    text = (_ROOT / "docs" / "domain.md").read_text(encoding="utf-8")
    assert "InternalSidecar" in text
    # Product diagram must not advertise ExternalGateway as a runtime option.
    assert "(옵션 ExternalGateway)" not in text
    assert "ExternalGateway (옵션)" not in text


def _check_settings_enabled_without_8642() -> None:
    assert Settings().agent_base_url == ""
    env = {
        "IRIS_AGENT_ENABLED": "1",
        "IRIS_AGENT_COMMAND": "hermes",
    }
    # Clear any shell IRIS_AGENT_BASE_URL so empty default wins.
    clear_keys = {
        k: ""
        for k in list(os.environ)
        if k.startswith("IRIS_AGENT_BASE_URL")
    }
    with mock.patch.dict(os.environ, {**clear_keys, **env, "IRIS_AGENT_BASE_URL": ""}, clear=False):
        settings = load_settings(env_path=_NO_DOTENV)
    assert settings.agent_enabled is True
    assert ":8642" not in (settings.agent_base_url or "")
    assert settings.agent_base_url == ""


def _check_setup_detect_no_gateway_probe() -> None:
    """Product detect must not health-probe :8642 for agent_running."""
    path = _ROOT / "iris" / "system" / "setup_protocol.py"
    text = path.read_text(encoding="utf-8")
    assert "is_iris_agent_gateway_running" not in text, path.name
    # Detect paths fill agent_running via engine filesystem check.
    assert "_engine_agent_present" in text
    assert '"agent_running"' in text
    assert '"hermes_running"' not in text
    assert '"agent_exe"' in text
    assert '"hermes_exe"' not in text


def main() -> None:
    _check_setup_step_renamed()
    _check_domain_sidecar_only()
    _check_settings_enabled_without_8642()
    _check_setup_detect_no_gateway_probe()
    print("gateway_retired_product_surface ok")


if __name__ == "__main__":
    main()
