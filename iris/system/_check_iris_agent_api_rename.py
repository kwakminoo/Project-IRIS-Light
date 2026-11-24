"""Unit A — Hermes product API symbols renamed to Iris Agent (no shims)."""

from __future__ import annotations

import inspect

from iris.infrastructure import iris_agent_client as client
from iris.infrastructure import iris_agent_credentials as cred
from iris.system import iris_agent_gateway as gw
from iris.system import iris_agent_install as install


_OLD_CRED = (
    "hermes_home",
    "is_weak_hermes_api_key",
    "load_hermes_dotenv",
    "resolve_hermes_api_key",
)
_NEW_CRED = (
    "iris_agent_home",
    "is_weak_iris_agent_api_key",
    "load_iris_agent_dotenv",
    "resolve_iris_agent_api_key",
)

_OLD_INSTALL = (
    "hermes_python_range",
    "hermes_install_lock",
    "install_hermes_with_system_python",
)
_NEW_INSTALL = (
    "iris_agent_python_range",
    "iris_agent_install_lock",
    "install_iris_agent_with_system_python",
)

_OLD_GW = (
    "hermes_executable",
    "_windows_hermes_candidates",
    "probe_hermes_runtime",
    "hermes_runtime_report",
    "ensure_hermes_gateway_running",
    "ensure_hermes_provider_config",
    "is_hermes_gateway_running",
)
_NEW_GW = (
    "iris_agent_executable",
    "_windows_iris_agent_candidates",
    "probe_iris_agent_runtime",
    "iris_agent_runtime_report",
    "ensure_iris_agent_gateway_running",
    "ensure_iris_agent_provider_config",
    "is_iris_agent_gateway_running",
)


def _assert_new_present(mod, names: tuple[str, ...]) -> None:
    for name in names:
        assert hasattr(mod, name), f"{mod.__name__} missing {name}"
        assert callable(getattr(mod, name)), f"{mod.__name__}.{name} not callable"


def _assert_old_absent(mod, names: tuple[str, ...]) -> None:
    for name in names:
        assert not hasattr(mod, name), f"{mod.__name__} still has legacy {name}"


def _check_credentials() -> None:
    _assert_new_present(cred, _NEW_CRED)
    _assert_old_absent(cred, _OLD_CRED)
    # One public home name — re-export, not a local wrapper.
    from iris.infrastructure.agent_runtime import iris_agent_home as runtime_home

    assert cred.iris_agent_home is runtime_home


def _check_install() -> None:
    _assert_new_present(install, _NEW_INSTALL)
    _assert_old_absent(install, _OLD_INSTALL)


def _check_gateway() -> None:
    _assert_new_present(gw, _NEW_GW)
    _assert_old_absent(gw, _OLD_GW)
    sig = inspect.signature(gw.iris_agent_executable)
    default = sig.parameters["command"].default
    assert default == "iris-agent", default
    doc = gw.iris_agent_executable.__doc__ or ""
    assert "iris-agent" in doc
    cands = inspect.getsource(gw._windows_iris_agent_candidates)
    # Order of Path literals in the return list (skip docstring).
    body = cands.split("return", 1)[-1]
    iris_pos = body.find("iris-agent.exe")
    hermes_pos = body.find("hermes.exe")
    assert iris_pos >= 0 and hermes_pos >= 0
    assert iris_pos < hermes_pos, "iris-agent.exe must precede hermes.exe"


def _check_client_provider() -> None:
    assert hasattr(client, "infer_iris_agent_provider")
    assert not hasattr(client, "infer_hermes_provider")
    assert callable(client.infer_iris_agent_provider)


def main() -> None:
    _check_credentials()
    _check_install()
    _check_gateway()
    _check_client_provider()
    print("iris_agent_api_rename ok")


if __name__ == "__main__":
    main()
