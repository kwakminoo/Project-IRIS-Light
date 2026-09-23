"""Live check: hermes install → gateway → core smoke.

실행: .venv\\Scripts\\python.exe -m iris.ui._check_setup_hermes_live
"""

from __future__ import annotations

import sys


def _safe(s: str) -> str:
    return (s or "").encode("ascii", "replace").decode()


def main() -> int:
    from iris.system.hermes_gateway import (
        is_hermes_gateway_running,
        probe_hermes_runtime,
        resolve_hermes_api_key,
    )
    from iris.system.setup_protocol import SetupProtocol

    print("probe", probe_hermes_runtime())
    key = resolve_hermes_api_key()
    url = "http://127.0.0.1:8642/v1"
    print("running_before", is_hermes_gateway_running(url, api_key=key, timeout_sec=2.0))

    proto = SetupProtocol(dry_run=False, simulate=False)
    proto.bind_stream(
        lambda t, _p, _r: print(f"[stream] {_safe(t or '')}", flush=True)
    )

    steps = [
        ("hermes_install", proto._step_hermes_install),
        ("hermes_env", proto._step_hermes_env),
        ("hermes_provider", proto._step_hermes_provider),
        ("iris_control_sync", proto._step_iris_control_sync),
        ("hermes_gateway", proto._step_hermes_gateway),
        ("core_smoke", proto._step_core_smoke),
    ]
    for name, fn in steps:
        print(f"=== {name} ===", flush=True)
        result = fn()
        print(f"{name} -> {result.status}: {_safe(result.message)[:240]}", flush=True)
        if result.status == "needs_user" and name == "hermes_install":
            result = proto._install_hermes()
            print(
                f"install -> {result.status}: {_safe(result.message)[:240]}",
                flush=True,
            )
        if result.status == "failed":
            print("STOP")
            return 1

    print("ALL_STEPS_OK")
    print("running_after", is_hermes_gateway_running(url, api_key=key, timeout_sec=3.0))
    ok, detail = proto.verify_core()
    print("verify_core", ok, _safe(detail)[:300])
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
