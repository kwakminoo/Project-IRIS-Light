"""컨트롤 HTTP 경계. 임시 포트만 사용하고 ~/.iris-light 는 쓰지 않는다."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

os.environ["IRIS_CONTROL_TOKEN"] = "contract-check-token"
os.environ.pop("IRIS_CONTROL_URL", None)

import iris.system.control_surface as cs
from iris.mcp.iris_control_stdio import _http, _tool_result

cs.write_control_endpoint = lambda **_k: None  # type: ignore[assignment]
cs.clear_control_endpoint = lambda: None  # type: ignore[assignment]

TOKEN = os.environ["IRIS_CONTROL_TOKEN"]
RAN: list[str] = []
PENDING: list[object] = []


class _Invoker:
    mode = "now"

    def run(self, fn, timeout=15.0):  # noqa: ANN001
        if self.mode == "ui-timeout":
            PENDING.append(fn)
            raise cs.UiThreadTimeout()
        if self.mode == "disk":
            raise TimeoutError("disk")
        return fn()


def _req(port: int, method: str, path: str, raw: bytes | None) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=raw,
        method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def main() -> None:
    inv = _Invoker()
    surface = cs.ControlSurface(invoker=inv, host="127.0.0.1", port=18771, token=TOKEN)
    surface.booting = False
    surface.registry.register(
        "ping",
        lambda _a: RAN.append("ping") or {"alive": True},
        summary="ping",
    )
    surface.registry.register(
        "get_state",
        lambda _a: cs.err_result("get_state", "state failed"),
        summary="state",
    )

    def touch(_a: dict) -> dict:
        RAN.append("touch")
        return {"touched": True}

    def inner(_a: dict) -> dict:
        RAN.append("inner")
        raise TimeoutError("inside")

    surface.registry.register("touch", touch, summary="touch")
    surface.registry.register("inner", inner, summary="inner")
    port = surface.start()
    try:
        code, body = _req(port, "POST", "/v1/invoke", b'{"action":"ping","args":{}}')
        assert code == 200 and body["ok"] is True and body["status"] == "success" and RAN == ["ping"], (code, body, RAN)

        before = list(RAN)
        code, body = _req(port, "POST", "/v1/invoke", b"")
        assert code == 400 and body["ok"] is False and body["status"] == "failed"
        assert RAN == before, RAN

        code, body = _req(port, "POST", "/v1/invoke", b"{")
        assert code == 400 and body["status"] == "invalid" and body["error"] == "invalid JSON" and RAN == before

        code, body = _req(port, "POST", "/v1/invoke", b"[]")
        assert code == 400 and body["status"] == "invalid" and body["error"] == "JSON object required" and RAN == before

        code, body = _req(port, "POST", "/v1/invoke", b'{"action":"missing","args":{}}')
        assert code == 400 and body["status"] == "failed" and "unknown action" in body["error"]
        assert RAN == before

        inv.mode = "ui-timeout"
        code, body = _req(port, "POST", "/v1/invoke", b'{"action":"touch","args":{}}')
        assert code == 400 and body["status"] == "timeout" and body["ok"] is False
        assert "touch" not in RAN and PENDING, RAN
        PENDING.pop()()  # 응답 후에야 큐가 돈다 — 취소가 아님
        assert RAN[-1] == "touch"

        inv.mode = "now"
        code, body = _req(port, "POST", "/v1/invoke", b'{"action":"inner","args":{}}')
        assert code == 400 and body["status"] == "failed" and body["error"] == "inside"
        assert RAN[-1] == "inner"

        inv.mode = "disk"
        code, body = _req(port, "POST", "/v1/invoke", b'{"action":"touch","args":{}}')
        assert code == 400 and body["status"] == "failed" and body["error"] == "disk"
        assert RAN.count("touch") == 1

        def bridge_wait(_a: dict) -> dict:
            from iris.ui.control_bindings import BridgeCallTimeout

            raise BridgeCallTimeout()

        surface.registry.register("bridge_wait", bridge_wait, summary="bridge wait")
        inv.mode = "now"
        code, body = _req(port, "POST", "/v1/invoke", b'{"action":"bridge_wait","args":{}}')
        assert code == 400 and body["status"] == "failed"
        assert body["error"] == "iris_ide bridge call timeout"
        assert body["status"] != "timeout"

        inv.mode = "now"
        code, body = _req(port, "GET", "/v1/state", None)
        assert code == 200 and body["ok"] is False and body["error"] == "state failed", (code, body)

        os.environ["IRIS_CONTROL_HOST"] = "127.0.0.1"
        os.environ["IRIS_CONTROL_PORT"] = str(port)
        os.environ["IRIS_CONTROL_URL"] = f"http://127.0.0.1:{port}"
        inv.mode = "ui-timeout"
        before_n = len(PENDING)
        payload = _http("POST", "/v1/invoke", {"action": "touch", "args": {}})
        assert payload.get("status") == "timeout" and payload.get("transport") is not True
        tool = _tool_result(payload)
        assert tool["isError"] is False
        assert '"ok": false' in tool["content"][0]["text"]
        assert not bool(payload.get("ok"))
        assert len(PENDING) == before_n + 1  # MCP가 400을 재시도하지 않음

        inv.mode = "now"
        bridge = _http("POST", "/v1/invoke", {"action": "bridge_wait", "args": {}})
        assert bridge.get("status") == "failed" and bridge.get("transport") is not True
        assert bridge.get("error") == "iris_ide bridge call timeout"
        bridge_tool = _tool_result(bridge)
        assert bridge_tool["isError"] is False

        down = _tool_result({"ok": False, "error": "unreachable", "transport": True})
        assert down["isError"] is True
    finally:
        surface.stop()
    print("control http contract ok")


if __name__ == "__main__":
    main()
