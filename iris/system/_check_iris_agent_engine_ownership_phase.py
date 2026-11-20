"""Engine ownership Phase 1 — Iris owns install contract without full tree rewrite.

Asserts:
  - vendor PIN / UPSTREAM exist and match agent_runtime loaders
  - checkout write name is iris-agent (no forced live rename)
  - product never starts :8642 gateway for chat
  - product probe accepts iris_agent_cli / iris_cli only (no hermes_cli)
  - public install name is install_iris_agent_*; hermes_* remains alias

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_iris_agent_engine_ownership_phase
"""

from __future__ import annotations

import inspect
from pathlib import Path

from iris.engine import _home as eng_home
from iris.infrastructure import agent_runtime as runtime
from iris.system import iris_agent_install as install
from iris.system import _check_no_product_gateway_ops as no_gw


_ROOT = Path(__file__).resolve().parents[2]
_VENDOR = _ROOT / "vendor" / "iris-agent-runtime"


def _check_vendor_pin_upstream_consistent() -> None:
    pin_file = _VENDOR / "PIN"
    up_file = _VENDOR / "UPSTREAM"
    assert pin_file.is_file(), "vendor/iris-agent-runtime/PIN missing"
    assert up_file.is_file(), "vendor/iris-agent-runtime/UPSTREAM missing"
    assert runtime.vendor_runtime_root() == _VENDOR
    assert runtime.pin_matches_vendor_pin()
    assert runtime.upstream_url_matches_vendor()
    file_sha = pin_file.read_text(encoding="utf-8").strip().split()[0]
    assert runtime.load_pinned_sha() == file_sha
    file_url = up_file.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    assert runtime.load_upstream_url() == file_url
    assert file_url.startswith("https://")


def _check_checkout_write_name_iris_agent() -> None:
    assert runtime.IRIS_AGENT_CHECKOUT_NAME == "iris-agent"
    assert runtime.LEGACY_AGENT_CHECKOUT_NAME == "hermes-agent"
    write = runtime.iris_agent_checkout_write_dir
    src = inspect.getsource(write)
    assert "IRIS_AGENT_CHECKOUT_NAME" in src
    assert "iris-agent" == runtime.IRIS_AGENT_CHECKOUT_NAME


def _check_no_product_gateway() -> None:
    no_gw.main()


def _check_probe_dual_accept() -> None:
    names = runtime.AGENT_CLI_PROBE_NAMES
    assert "hermes_cli" not in names
    assert "iris_agent_cli" in names
    assert "iris_cli" in names
    snippet = runtime.agent_cli_probe_code("aiohttp", "mcp")
    assert "hermes_cli" not in snippet
    assert "iris_agent_cli" in snippet
    assert "iris_cli" in snippet
    probe = eng_home._PROBE_IMPORT
    assert "hermes_cli" not in probe
    assert "iris_agent_cli" in probe or "iris_cli" in probe
    venv_src = inspect.getsource(install._probe_venv)
    assert "agent_cli_probe_code" in venv_src or (
        "iris_agent_cli" in venv_src or "iris_cli" in venv_src
    )


def _check_install_public_name() -> None:
    assert hasattr(install, "install_iris_agent_with_system_python")
    assert hasattr(install, "install_agent_with_system_python")
    assert (
        install.install_agent_with_system_python
        is install.install_iris_agent_with_system_python
    )
    # Prefer Iris name at EngineHome install_into.
    home_src = Path(eng_home.__file__).read_text(encoding="utf-8")
    assert "install_iris_agent_with_system_python" in home_src


def _check_package_identity_overlay() -> None:
    from iris.system import _check_iris_agent_package_identity as pkg_id

    pkg_id.main()


def _check_cli_shim_overlay() -> None:
    from iris.system import _check_iris_agent_cli_shim as cli_shim

    cli_shim.main()


def _check_cli_rename_overlay() -> None:
    from iris.system import _check_iris_agent_cli_rename as cli_rename

    cli_rename.main()


def main() -> None:
    _check_vendor_pin_upstream_consistent()
    _check_checkout_write_name_iris_agent()
    _check_no_product_gateway()
    _check_probe_dual_accept()
    _check_install_public_name()
    _check_package_identity_overlay()
    _check_cli_shim_overlay()
    _check_cli_rename_overlay()
    print(
        "iris_agent_engine_ownership_phase ok",
        runtime.load_pinned_sha()[:7],
        runtime.IRIS_AGENT_CHECKOUT_NAME,
    )


if __name__ == "__main__":
    main()
