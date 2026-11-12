"""Unit 1 / Wave C — Iris Agent policy owns product settings / env names.

Canonical fields: ``agent_enabled``, ``agent_command``, ``agent_base_url``,
``agent_api_key``. ``hermes_*`` remain read/write property aliases.
Env prefers ``IRIS_AGENT_*`` with ``IRIS_HERMES_*`` as alias readers.
Control HTTP may dual-key ``hermes_enabled`` + ``agent_enabled`` for MCP clients.

Run:
  .venv\\Scripts\\python.exe -m iris.config._check_iris_agent_policy_settings
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from unittest import mock

from iris.config.settings import Settings, load_settings
from iris.engine.types import InternalSidecar, parse_engine_source

# Avoid repo .env clobbering alias preference asserts.
_NO_DOTENV = Path("__iris_agent_policy_settings_no_dotenv__")

_CANONICAL = (
    "agent_enabled",
    "agent_command",
    "agent_base_url",
    "agent_api_key",
)
_ALIAS = (
    "hermes_enabled",
    "hermes_command",
    "hermes_base_url",
    "hermes_api_key",
)


def check_canonical_field_is_agent_enabled() -> None:
    names = {f.name for f in dataclasses.fields(Settings)}
    for name in _CANONICAL:
        assert name in names, f"Settings must own {name} as a dataclass field"
    for name in _ALIAS:
        assert name not in names, f"{name} must be alias, not a dataclass field"
    s = Settings()
    assert s.agent_enabled is True
    assert s.hermes_enabled is True
    s.hermes_enabled = False
    assert s.agent_enabled is False
    s.agent_enabled = True
    assert s.hermes_enabled is True


def check_canonical_agent_shell_fields_and_aliases() -> None:
    names = {f.name for f in dataclasses.fields(Settings)}
    for name in ("agent_command", "agent_base_url", "agent_api_key"):
        assert name in names, f"Settings must own {name} as a dataclass field"
    for name in ("hermes_command", "hermes_base_url", "hermes_api_key"):
        assert name not in names, f"{name} must be alias, not a dataclass field"
    s = Settings()
    assert s.agent_command == "hermes"
    assert s.hermes_command == "hermes"
    s.hermes_command = "iris-agent"
    assert s.agent_command == "iris-agent"
    s.agent_command = "hermes"
    assert s.hermes_command == "hermes"

    s.hermes_base_url = "http://127.0.0.1:1/v1"
    assert s.agent_base_url == "http://127.0.0.1:1/v1"
    s.agent_base_url = "http://127.0.0.1:8642/v1"
    assert s.hermes_base_url == "http://127.0.0.1:8642/v1"

    s.hermes_api_key = "legacy"
    assert s.agent_api_key == "legacy"
    s.agent_api_key = "canonical"
    assert s.hermes_api_key == "canonical"


def _passthrough_api_key(api_key: str = "") -> str:
    return (api_key or "").strip()


def check_load_prefers_iris_agent_env() -> None:
    base = {
        "IRIS_AGENT_ENABLED": "0",
        "IRIS_HERMES_ENABLED": "1",
        "IRIS_AGENT_BASE_URL": "http://127.0.0.1:9999/v1",
        "IRIS_HERMES_BASE_URL": "http://127.0.0.1:8642/v1",
        "IRIS_AGENT_API_KEY": "agent-key",
        "IRIS_HERMES_API_KEY": "hermes-key",
        "IRIS_AGENT_COMMAND": "iris-agent",
        "IRIS_HERMES_COMMAND": "hermes",
    }
    with mock.patch.dict(os.environ, base, clear=False), mock.patch(
        "iris.infrastructure.iris_agent_credentials.resolve_hermes_api_key",
        side_effect=_passthrough_api_key,
    ):
        s = load_settings(env_path=_NO_DOTENV)
    assert s.agent_enabled is False
    assert s.hermes_enabled is False
    assert "9999" in s.agent_base_url
    assert "9999" in s.hermes_base_url
    assert s.agent_api_key == "agent-key"
    assert s.hermes_api_key == "agent-key"
    assert s.agent_command == "iris-agent"
    assert s.hermes_command == "iris-agent"


def check_hermes_env_alias_still_loads() -> None:
    keys = (
        "IRIS_AGENT_ENABLED",
        "IRIS_AGENT_BASE_URL",
        "IRIS_AGENT_API_KEY",
        "IRIS_AGENT_COMMAND",
        "IRIS_HERMES_ENABLED",
        "IRIS_HERMES_BASE_URL",
        "IRIS_HERMES_API_KEY",
        "IRIS_HERMES_COMMAND",
    )
    cleaned = {k: "" for k in keys}
    # Wipe both families, then set only Hermes aliases.
    with mock.patch.dict(
        os.environ,
        {
            **cleaned,
            "IRIS_HERMES_ENABLED": "0",
            "IRIS_HERMES_BASE_URL": "http://127.0.0.1:7777/v1",
            "IRIS_HERMES_API_KEY": "legacy-key",
            "IRIS_HERMES_COMMAND": "legacy-hermes",
        },
        clear=False,
    ), mock.patch(
        "iris.infrastructure.iris_agent_credentials.resolve_hermes_api_key",
        side_effect=_passthrough_api_key,
    ):
        for k in (
            "IRIS_AGENT_ENABLED",
            "IRIS_AGENT_BASE_URL",
            "IRIS_AGENT_API_KEY",
            "IRIS_AGENT_COMMAND",
        ):
            os.environ.pop(k, None)
        s = load_settings(env_path=_NO_DOTENV)
    assert s.agent_enabled is False
    assert s.hermes_enabled is False
    assert "7777" in s.agent_base_url
    assert "7777" in s.hermes_base_url
    assert s.agent_api_key == "legacy-key"
    assert s.hermes_api_key == "legacy-key"
    assert s.agent_command == "legacy-hermes"
    assert s.hermes_command == "legacy-hermes"


def check_default_engine_source_is_sidecar() -> None:
    source = parse_engine_source(Settings())
    assert isinstance(source, InternalSidecar), type(source)


if __name__ == "__main__":
    check_canonical_field_is_agent_enabled()
    check_canonical_agent_shell_fields_and_aliases()
    check_load_prefers_iris_agent_env()
    check_hermes_env_alias_still_loads()
    check_default_engine_source_is_sidecar()
    print("iris_agent_policy_settings ok")
