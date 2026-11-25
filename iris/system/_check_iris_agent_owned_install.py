"""ACO-P5: Iris Agent install defaults to vendor/iris-agent-core → live iris-agent.

python -m iris.system._check_iris_agent_owned_install
"""

from __future__ import annotations

import inspect
import tempfile
from pathlib import Path

from iris.infrastructure.agent_runtime import IRIS_AGENT_CHECKOUT_NAME
from iris.system import iris_agent_install as m


def main() -> None:
    vendor = m.vendor_iris_agent_core_root()
    assert vendor.is_dir(), f"vendor missing: {vendor}"
    assert (vendor / "run_agent.py").is_file(), "run_agent.py missing in vendor"

    src = Path(m.__file__).read_text(encoding="utf-8")
    assert (
        "vendor_iris_agent_core" in src or "_materialize_owned_core" in src
    ), "install source missing owned-core materialize"

    body = inspect.getsource(m.install_iris_agent_with_system_python)
    assert "_checkout_pinned_sha" not in body, (
        "default install must not call _checkout_pinned_sha"
    )
    assert "_materialize_owned_core" in body
    assert "IRIS_AGENT_CHECKOUT_NAME" in body

    swap = inspect.getsource(m._swap_in_staging)
    assert "IRIS_AGENT_CHECKOUT_NAME" in swap
    assert 'home / "hermes-agent"' not in swap

    assert IRIS_AGENT_CHECKOUT_NAME == "iris-agent"

    with tempfile.TemporaryDirectory(prefix="iris-owned-core-") as tmp:
        staging = Path(tmp) / "staging"
        proc = m._materialize_owned_core(staging)
        assert proc.returncode == 0, proc.stderr or proc.stdout
        assert (staging / "run_agent.py").is_file()
        assert (staging / "iris_agent_cli").is_dir() or (staging / "hermes_cli").is_dir()

    print("iris_agent_owned_install ok", vendor)


if __name__ == "__main__":
    main()
