"""Iris Agent policy owns canonical product settings and environment names."""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from unittest import mock

from iris.config.settings import Settings, load_settings
from iris.engine.types import InternalSidecar, parse_engine_source

_NO_DOTENV = Path("__iris_agent_policy_settings_no_dotenv__")
_FIELDS = ("agent_enabled", "agent_command", "agent_base_url", "agent_api_key")


def main() -> None:
    names = {field.name for field in dataclasses.fields(Settings)}
    assert set(_FIELDS) <= names
    settings = Settings()
    assert all(not hasattr(settings, name.replace("agent_", "hermes_")) for name in _FIELDS)

    env = {
        "IRIS_AGENT_ENABLED": "0",
        "IRIS_AGENT_BASE_URL": "http://127.0.0.1:9999/v1",
        "IRIS_AGENT_API_KEY": "agent-key",
        "IRIS_AGENT_COMMAND": "iris-agent",
    }
    with mock.patch.dict(os.environ, env, clear=False), mock.patch(
        "iris.infrastructure.iris_agent_credentials.resolve_iris_agent_api_key",
        side_effect=lambda api_key="": (api_key or "").strip(),
    ):
        settings = load_settings(env_path=_NO_DOTENV)
    assert settings.agent_enabled is False
    assert "9999" in settings.agent_base_url
    assert settings.agent_api_key == "agent-key"
    assert settings.agent_command == "iris-agent"
    assert isinstance(parse_engine_source(settings), InternalSidecar)
    print("iris_agent_policy_settings ok")


if __name__ == "__main__":
    main()
