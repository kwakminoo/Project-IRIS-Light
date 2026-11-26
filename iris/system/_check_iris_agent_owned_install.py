"""ACO-P5: Iris Agent install defaults to vendor/iris-agent-core → live iris-agent.

python -m iris.system._check_iris_agent_owned_install
"""

from __future__ import annotations

import inspect
import os
import tempfile
from pathlib import Path

from iris.infrastructure.agent_runtime import IRIS_AGENT_CHECKOUT_NAME
from iris.system import iris_agent_install as m


def _assert_hermes_replace_gate() -> None:
    """Without IRIS_DEV_OWNED_CUTOVER hermes replace stays blocked; with env allowed."""
    prev = os.environ.pop("IRIS_DEV_OWNED_CUTOVER", None)
    try:
        assert not m._dev_owned_cutover_allowed()
        with tempfile.TemporaryDirectory(prefix="iris-hermes-gate-") as tmp:
            home = Path(tmp)
            reference = home / "hermes-agent"
            reference.mkdir()
            m._write_engine_selection(home, reference, None)
            blocked = m.install_iris_agent_with_system_python(
                home=home, update=True, model_check=lambda _: None
            )
            assert blocked.ok is False and blocked.kind == "gate", (
                f"expected gate block, got ok={blocked.ok} kind={blocked.kind} msg={blocked.message}"
            )
        os.environ["IRIS_DEV_OWNED_CUTOVER"] = "1"
        assert m._dev_owned_cutover_allowed()
        body = inspect.getsource(m.install_iris_agent_with_system_python)
        assert "_dev_owned_cutover_allowed" in body
    finally:
        if prev is None:
            os.environ.pop("IRIS_DEV_OWNED_CUTOVER", None)
        else:
            os.environ["IRIS_DEV_OWNED_CUTOVER"] = prev


def main() -> None:
    vendor = m.vendor_iris_agent_core_root()
    assert vendor.is_dir(), f"vendor missing: {vendor}"
    assert (vendor / "run_agent.py").is_file(), "run_agent.py missing in vendor"

    src = Path(m.__file__).read_text(encoding="utf-8")
    assert (
        "vendor_iris_agent_core" in src or "_materialize_owned_core" in src
    ), "install source missing owned-core materialize"

    # materialize-only: dead pin-checkout helper must be gone entirely
    assert "_checkout_pinned_sha" not in src, (
        "dead _checkout_pinned_sha must be removed; materialize-only is required"
    )
    assert "HERMES_REPO_HTTPS" not in src
    body = inspect.getsource(m.install_iris_agent_with_system_python)
    assert "_materialize_owned_core" in body
    assert "IRIS_AGENT_CHECKOUT_NAME" in body

    swap = inspect.getsource(m._swap_in_staging)
    assert "IRIS_AGENT_CHECKOUT_NAME" in swap
    assert 'home / "hermes-agent"' not in swap

    assert IRIS_AGENT_CHECKOUT_NAME == "iris-agent"
    _assert_hermes_replace_gate()

    with tempfile.TemporaryDirectory(prefix="iris-owned-core-") as tmp:
        staging = Path(tmp) / "staging"
        proc = m._materialize_owned_core(staging)
        assert proc.returncode == 0, proc.stderr or proc.stdout
        assert (staging / "run_agent.py").is_file()
        assert (staging / "iris_agent_cli").is_dir() or (staging / "hermes_cli").is_dir()

    print("iris_agent_owned_install ok", vendor)


if __name__ == "__main__":
    main()
