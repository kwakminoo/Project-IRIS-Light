"""Iris Agent engine setup step — ensure_ready only (no :8642 spawn)."""

from __future__ import annotations

import inspect

from iris.system.setup_protocol import CORE_STEP_IDS, SetupProtocol


def _main() -> None:
    assert "iris_agent_engine" in CORE_STEP_IDS
    assert "hermes_gateway" not in CORE_STEP_IDS

    step_src = inspect.getsource(SetupProtocol._step_iris_agent_engine)
    assert "ensure_ready" in step_src
    assert "shared_engine" in step_src
    assert "restart_hermes_gateway" not in step_src
    assert "ensure_iris_agent_gateway_running" not in step_src
    assert "start_hermes_gateway" not in step_src

    # Smoke: method is bound and records the new step id on abort.
    proto = SetupProtocol(simulate=True, dry_run=False)
    proto._abort = True
    result = proto._step_iris_agent_engine()
    assert result.step_id == "iris_agent_engine"
    assert result.status == "failed"
    print("iris_agent_engine_setup_step ok")


if __name__ == "__main__":
    _main()
