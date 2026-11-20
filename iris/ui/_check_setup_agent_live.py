"""Live check: Iris Agent install → sidecar runtime → core smoke.

실행: .venv\\Scripts\\python.exe -m iris.ui._check_setup_agent_live
"""

from __future__ import annotations

import sys


def _safe(s: str) -> str:
    return (s or "").encode("ascii", "replace").decode()


def main() -> int:
    from iris.system.iris_agent_gateway import (
        probe_agent_runtime,
        resolve_agent_api_key,
    )
    from iris.system.setup_protocol import SetupProtocol

    print("probe", probe_agent_runtime())
    _ = resolve_agent_api_key()

    proto = SetupProtocol(dry_run=False, simulate=False)
    proto.bind_stream(
        lambda t, _p, _r: print(f"[stream] {_safe(t or '')}", flush=True)
    )

    steps = [
        ("agent_install", proto._step_agent_install),
        ("agent_env", proto._step_agent_env),
        ("agent_provider", proto._step_agent_provider),
        ("iris_control_sync", proto._step_iris_control_sync),
        ("agent_runtime", proto._step_agent_runtime),
        ("core_smoke", proto._step_core_smoke),
    ]
    for name, fn in steps:
        print(f"=== {name} ===", flush=True)
        result = fn()
        print(f"{name} -> {result.status}: {_safe(result.message)[:240]}", flush=True)
        if result.status == "needs_user" and name == "agent_install":
            result = proto._install_agent()
            print(
                f"install -> {result.status}: {_safe(result.message)[:240]}",
                flush=True,
            )
        if result.status == "failed":
            print("STOP")
            return 1

    print("ALL_STEPS_OK")
    ok, detail = proto.verify_core()
    print("verify_core", ok, _safe(detail)[:300])
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
