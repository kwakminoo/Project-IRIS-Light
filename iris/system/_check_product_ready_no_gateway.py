"""Unit 1 — ProductReady is EngineReady(InternalSidecar), not :8642 gateway."""

from __future__ import annotations

import inspect
from pathlib import Path

from iris.infrastructure.agent_runtime import ensure_iris_agent_runtime
from iris.system.setup_protocol import SetupProtocol
from iris.ui.workers import iris_agent_workers as hw


_ROOT = Path(__file__).resolve().parents[2]


def _check_start_gateway_default_false() -> None:
    sig = inspect.signature(ensure_iris_agent_runtime)
    param = sig.parameters["start_gateway"]
    assert param.default is False, param.default


def _check_step_no_gateway_spawn() -> None:
    step_src = inspect.getsource(SetupProtocol._step_iris_agent_engine)
    assert "restart_hermes_gateway" not in step_src
    assert "ensure_iris_agent_gateway_running" not in step_src
    assert "ensure_ready" in step_src
    assert "shared_engine" in step_src


def _check_warm_cli_no_gateway_up() -> None:
    warm = (_ROOT / "iris" / "iris_agent_login_warm_cli.py").read_text(encoding="utf-8")
    assert "gateway up" not in warm
    assert "runtime ready" in warm or "engine ready" in warm
    assert "start_gateway=True" not in warm


def _check_health_uses_ensure_ready() -> None:
    health_src = inspect.getsource(hw.IrisAgentHealthWorker.run)
    assert "ensure_ready" in health_src
    assert "ensure_iris_agent_gateway_running" not in health_src


def main() -> None:
    _check_start_gateway_default_false()
    _check_step_no_gateway_spawn()
    _check_warm_cli_no_gateway_up()
    _check_health_uses_ensure_ready()
    print("product_ready_no_gateway ok")


if __name__ == "__main__":
    main()
