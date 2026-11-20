"""Unit 1 / Wave C / PR-B3 — Iris Agent policy owns product settings / env names.

Canonical fields: ``agent_enabled``, ``agent_command``, ``agent_base_url``,
``agent_api_key``. Settings ``hermes_*`` property aliases are deleted.
Product env reads ``IRIS_AGENT_*`` only (no ``IRIS_HERMES_*`` alias).
Control HTTP uses ``agent_enabled`` only (no ``hermes_enabled`` dual-key).

Run:
  .venv/Scripts/python.exe -m iris.config._check_iris_agent_policy_settings
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
_GONE_ALIASES = (
    "hermes_enabled",
    "hermes_command",
    "hermes_base_url",
    "hermes_api_key",
)
_AGENT_KEYS = (
    "IRIS_AGENT_ENABLED",
    "IRIS_AGENT_BASE_URL",
    "IRIS_AGENT_API_KEY",
    "IRIS_AGENT_COMMAND",
)
_HERMES_KEYS = (
    "IRIS_HERMES_ENABLED",
    "IRIS_HERMES_BASE_URL",
    "IRIS_HERMES_API_KEY",
    "IRIS_HERMES_COMMAND",
)


def check_canonical_field_is_agent_enabled() -> None:
    names = {f.name for f in dataclasses.fields(Settings)}
    for name in _CANONICAL:
        assert name in names, f"Settings must own {name} as a dataclass field"
    for name in _GONE_ALIASES:
        assert name not in names, f"{name} must not be a dataclass field"
        assert not hasattr(Settings, name), f"Settings.{name} alias must be deleted"
    s = Settings()
    assert s.agent_enabled is True


def check_canonical_agent_shell_fields() -> None:
    s = Settings()
    assert s.agent_command == "iris-agent"
    # Product default: empty = InternalSidecar (no invented :8642 endpoint).
    assert s.agent_base_url == ""
    # Legacy override still accepted (not product default).
    s.agent_command = "hermes"
    assert s.agent_command == "hermes"
    s.agent_command = "iris-agent"
    assert s.agent_command == "iris-agent"

    s.agent_base_url = "http://127.0.0.1:1/v1"
    assert s.agent_base_url == "http://127.0.0.1:1/v1"
    # Opt-in assignment still accepted (non-default).
    s.agent_base_url = "http://127.0.0.1:8642/v1"
    assert "8642" in s.agent_base_url
    s.agent_base_url = ""

    s.agent_api_key = "canonical"
    assert s.agent_api_key == "canonical"


def check_load_default_base_url_empty() -> None:
    keys = _AGENT_KEYS + _HERMES_KEYS
    cleaned = {k: "" for k in keys}
    with mock.patch.dict(os.environ, cleaned, clear=False), mock.patch(
        "iris.infrastructure.iris_agent_credentials.resolve_agent_api_key",
        side_effect=_passthrough_api_key,
    ):
        for k in keys:
            os.environ.pop(k, None)
        s = load_settings(env_path=_NO_DOTENV)
    assert s.agent_base_url == ""
    assert "8642" not in s.agent_base_url
    assert s.agent_command == "iris-agent"


def _passthrough_api_key(api_key: str = "") -> str:
    return (api_key or "").strip()


def check_load_prefers_iris_agent_env() -> None:
    # HERMES distractors must not win when AGENT is set.
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
        "iris.infrastructure.iris_agent_credentials.resolve_agent_api_key",
        side_effect=_passthrough_api_key,
    ):
        s = load_settings(env_path=_NO_DOTENV)
    assert s.agent_enabled is False
    assert "9999" in s.agent_base_url
    assert s.agent_api_key == "agent-key"
    assert s.agent_command == "iris-agent"


def check_agent_env_alias_no_longer_loads() -> None:
    """Hard-cut: HERMES-only env must not populate agent_* (rename to AGENT)."""
    cleaned = {k: "" for k in _AGENT_KEYS + _HERMES_KEYS}
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
        "iris.infrastructure.iris_agent_credentials.resolve_agent_api_key",
        side_effect=_passthrough_api_key,
    ):
        for k in _AGENT_KEYS:
            os.environ.pop(k, None)
        s = load_settings(env_path=_NO_DOTENV)
    assert s.agent_enabled is True  # default — HERMES ENABLED ignored
    assert s.agent_base_url == ""
    assert "7777" not in s.agent_base_url
    assert s.agent_api_key == ""
    assert s.agent_command == "iris-agent"


def check_legacy_agent_8642_maps_empty() -> None:
    """HERMES-only :8642 is ignored (not read) → empty product chat URL."""
    cleaned = {k: "" for k in _AGENT_KEYS + _HERMES_KEYS}
    with mock.patch.dict(
        os.environ,
        {
            **cleaned,
            "IRIS_HERMES_BASE_URL": "http://127.0.0.1:8642/v1",
        },
        clear=False,
    ):
        for k in _AGENT_KEYS:
            os.environ.pop(k, None)
        s = load_settings(env_path=_NO_DOTENV)
    assert s.agent_base_url == ""
    assert "8642" not in s.agent_base_url


def check_iris_agent_8642_env_force_stripped() -> None:
    """Force strip: IRIS_AGENT_BASE_URL containing :8642 → empty (sidecar-only)."""
    cleaned = {k: "" for k in _AGENT_KEYS + _HERMES_KEYS}
    with mock.patch.dict(
        os.environ,
        {
            **cleaned,
            "IRIS_AGENT_BASE_URL": "http://127.0.0.1:8642/v1",
            "IRIS_HERMES_BASE_URL": "http://127.0.0.1:8642/v1",
        },
        clear=False,
    ):
        s = load_settings(env_path=_NO_DOTENV)
    assert s.agent_base_url == ""
    assert "8642" not in s.agent_base_url


def check_default_engine_source_is_sidecar() -> None:
    source = parse_engine_source(Settings())
    assert isinstance(source, InternalSidecar), type(source)


def check_agent_executable_default_is_iris_agent() -> None:
    import inspect

    from iris.system import iris_agent_gateway as gw

    assert hasattr(gw, "agent_executable")
    default = inspect.signature(gw.agent_executable).parameters["command"].default
    assert default == "iris-agent", default
    # Migrate callers then delete — no long-lived hermes_executable alias.
    assert not hasattr(gw, "hermes_executable")


def check_setup_writes_iris_agent_env() -> None:
    """E1: setup product path upserts IRIS_AGENT_API_KEY (not only HERMES)."""
    import ast

    root = Path(__file__).resolve().parents[2]
    src_path = root / "iris" / "system" / "setup_protocol.py"
    text = src_path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(src_path))
    step = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_step_agent_env":
            step = node
            break
    assert step is not None, "_step_agent_env missing"
    step_src = ast.get_source_segment(text, step) or ""
    assert "IRIS_AGENT_API_KEY" in step_src, (
        "_step_agent_env must write IRIS_AGENT_API_KEY"
    )
    # Product write must not target HERMES-only key as the upsert payload.
    assert '_upsert_dotenv(_iris_env_path(), {"IRIS_HERMES_API_KEY"' not in step_src
    assert 'os.environ["IRIS_HERMES_API_KEY"]' not in step_src
    assert "IRIS_HERMES_API_KEY" not in step_src
    # Prefer agent key when reading live env for seed/redact.
    redact = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "redact_secrets":
            redact = node
            break
    assert redact is not None
    redact_src = ast.get_source_segment(text, redact) or ""
    assert "IRIS_AGENT_API_KEY" in redact_src


if __name__ == "__main__":
    check_canonical_field_is_agent_enabled()
    check_canonical_agent_shell_fields()
    check_load_default_base_url_empty()
    check_load_prefers_iris_agent_env()
    check_agent_env_alias_no_longer_loads()
    check_legacy_agent_8642_maps_empty()
    check_iris_agent_8642_env_force_stripped()
    check_default_engine_source_is_sidecar()
    check_agent_executable_default_is_iris_agent()
    check_setup_writes_iris_agent_env()
    print("iris_agent_policy_settings ok")
