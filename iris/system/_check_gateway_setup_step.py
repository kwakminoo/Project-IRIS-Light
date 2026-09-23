"""gateway 단계 멈춤·abort 회귀 검사."""

from __future__ import annotations

import threading
import time

from iris.system.hermes_gateway import (
    ensure_hermes_gateway_running,
    is_hermes_gateway_running,
    resolve_hermes_api_key,
    restart_hermes_gateway,
)
from iris.system.setup_protocol import SetupProtocol


def _main() -> None:
    key = resolve_hermes_api_key()
    base = "http://127.0.0.1:8642/v1"

    # 헬스 폴링은 반드시 짧은 timeout 경로
    t0 = time.monotonic()
    _ = is_hermes_gateway_running(base, api_key=key, timeout_sec=2.0)
    assert time.monotonic() - t0 < 6.0, "health ping too slow"

    notes: list[str] = []
    ok = ensure_hermes_gateway_running(
        base,
        api_key=key,
        wait_sec=35.0,
        on_progress=notes.append,
    )
    assert ok, "ensure failed"
    # 이미 떠 있으면 progress 없이 즉시 True — 재기동 경로에서만 필수

    proto = SetupProtocol()
    streams: list[str] = []
    proto.bind_stream(lambda t, _p, _r: streams.append(t or ""))
    t1 = time.monotonic()
    result = proto._step_hermes_gateway()
    dt = time.monotonic() - t1
    assert result.status == "done", result
    assert any("gateway" in s.lower() or "MCP" in s or "기동" in s or "확인" in s for s in streams), streams
    # 이미 떠 있으면 무조건 restart 하던 시절보다 빨라야 함
    assert dt < 45.0, dt

    # abort가 stop 루프를 끊는지
    flag = {"abort": False}

    def _abort() -> bool:
        return flag["abort"]

    def _kill_soon() -> None:
        time.sleep(0.4)
        flag["abort"] = True

    threading.Thread(target=_kill_soon, daemon=True).start()
    t2 = time.monotonic()
    restart_hermes_gateway(
        base,
        api_key=key,
        wait_sec=30.0,
        should_abort=_abort,
        on_progress=notes.append,
    )
    assert time.monotonic() - t2 < 8.0, "abort did not cut restart"
    assert notes, "restart should emit progress"

    # 복구
    ensure_hermes_gateway_running(base, api_key=key, wait_sec=35.0)
    print("gateway_step check ok", f"dt={dt:.1f}s", f"streams={len(streams)}")


if __name__ == "__main__":
    _main()
