"""ACO-P6: product default must not require :8642 gateway spawn."""

from __future__ import annotations

import inspect
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def check_supervisor_default_no_gateway() -> None:
    from iris.infrastructure import agent_runtime as ar

    sig = inspect.signature(ar.ensure_iris_agent_runtime)
    assert sig.parameters["start_gateway"].default is False


def check_sidecar_only_engine_source() -> None:
    from iris.engine.types import InternalSidecar, parse_engine_source

    class _S:
        pass

    src = parse_engine_source(_S())
    assert isinstance(src, InternalSidecar)


def check_product_no_gateway_spawn_module() -> None:
    # existing contract module
    import iris.system._check_product_no_gateway_spawn as m

    assert hasattr(m, "__file__")


def check_apply_env_to_hermes_script_retired() -> None:
    """FRC-07: legacy LOCALAPPDATA hermes .env merge script must stay gone."""
    path = _ROOT / "scripts" / "apply_env_to_hermes.ps1"
    assert not path.exists(), path


if __name__ == "__main__":
    check_supervisor_default_no_gateway()
    check_sidecar_only_engine_source()
    check_product_no_gateway_spawn_module()
    check_apply_env_to_hermes_script_retired()
    print("gateway legacy isolated ok")
