"""Phase 4b / §10.1 gate 4: Iris Agent supervisor ensure 자검."""

from __future__ import annotations

import inspect
from pathlib import Path

from iris.infrastructure import agent_runtime as ar
from iris.infrastructure.agent_runtime import (
    IrisAgentRuntimeEnsureResult,
    ensure_iris_agent_home,
    ensure_iris_agent_runtime,
)
from iris.ui.workers import hermes_workers as hw


_ROOT = Path(__file__).resolve().parents[2]


def _check_public_ensure_symbol() -> None:
    assert callable(ensure_iris_agent_runtime)
    assert callable(ensure_iris_agent_home)
    src = inspect.getsource(ensure_iris_agent_runtime)
    assert "ensure_iris_agent_home" in src
    assert "ensure_hermes_gateway_running" in src
    assert "ensure_hermes_provider_config" in src
    # Lifetime policy documented on the supervisor module.
    mod = inspect.getsource(ar)
    assert "keep-background" in mod or "keep background" in mod.lower()
    assert issubclass(IrisAgentRuntimeEnsureResult, object)
    fields = {f.name for f in IrisAgentRuntimeEnsureResult.__dataclass_fields__.values()}
    assert {"ok", "home", "gateway_ok", "messages"} <= fields


def _check_three_entry_points_call_supervisor() -> None:
    health_src = inspect.getsource(hw.HermesHealthWorker.run)
    assert "ensure_iris_agent_runtime" in health_src
    # Final gateway bring-up must go through supervisor, not a bare gateway start.
    assert "ensure_hermes_gateway_running" not in health_src

    warm_cli = (_ROOT / "iris" / "hermes_login_warm_cli.py").read_text(encoding="utf-8")
    assert "ensure_iris_agent_runtime" in warm_cli
    assert "ensure_hermes_gateway_running" not in warm_cli

    setup = (_ROOT / "iris" / "system" / "setup_protocol.py").read_text(encoding="utf-8")
    # Warm-core + step gateway start paths.
    assert "ensure_iris_agent_runtime" in setup
    warm_fn = inspect.getsource(
        __import__(
            "iris.system.setup_protocol", fromlist=["_warm_core_services"]
        )._warm_core_services
    )
    assert "ensure_iris_agent_runtime" in warm_fn
    assert "ensure_hermes_gateway_running" not in warm_fn

    from iris.system.setup_protocol import SetupProtocol

    step_src = inspect.getsource(SetupProtocol._step_hermes_gateway)
    assert "ensure_iris_agent_runtime" in step_src
    # Non-restart start must not bypass supervisor.
    assert (
        "return ensure_hermes_gateway_running" not in step_src
        and "ensure_hermes_gateway_running(" not in step_src
    )


def _check_alias_optional() -> None:
    assert hw.IrisAgentHealthWorker is hw.HermesHealthWorker


def _check_no_legacy_log_path_in_setup() -> None:
    setup = (_ROOT / "iris" / "system" / "setup_protocol.py").read_text(encoding="utf-8")
    assert "%LOCALAPPDATA%\\hermes" not in setup
    assert r"%LOCALAPPDATA%\hermes" not in setup


def main() -> None:
    _check_public_ensure_symbol()
    _check_three_entry_points_call_supervisor()
    _check_alias_optional()
    _check_no_legacy_log_path_in_setup()
    print("iris_agent_supervisor_phase4b ok")


if __name__ == "__main__":
    main()
