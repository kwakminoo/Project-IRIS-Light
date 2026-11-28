"""Runnable contract for signed Gateway webhook connectors."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from iris.engine import TurnFinished
from iris.infrastructure.iris_agent_client import IrisAgentInferenceTarget
from iris.system.control_surface import ControlSurface, MainThreadInvoker
from iris.system.native_gateway import NativeGateway


def _request(surface, path: str, payload: dict, headers: dict[str, str] | None = None):
    req = Request(
        f"http://127.0.0.1:{surface.bound_port}{path}",
        data=json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(),
        headers=headers or {},
        method="POST",
    )
    try:
        response = urlopen(req, timeout=5)
    except HTTPError as exc:
        response = exc
    with response:
        raw = response.read()
        if response.headers.get_content_type() == "application/x-ndjson":
            return response.code, [json.loads(line) for line in raw.splitlines()]
        return response.code, json.loads(raw)


def _get(surface, path: str, token: str):
    req = Request(
        f"http://127.0.0.1:{surface.bound_port}{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        response = urlopen(req, timeout=5)
    except HTTPError as exc:
        response = exc
    with response:
        raw = response.read()
        if response.headers.get_content_type() == "application/x-ndjson":
            return response.code, [json.loads(line) for line in raw.splitlines()]
        return response.code, json.loads(raw)


def _signed(secret: str, connector_id: str, payload: dict, *, stamp: int, nonce: str):
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    key = hashlib.sha256(secret.encode()).digest()
    material = str(stamp).encode() + b"." + nonce.encode() + b"." + canonical
    return {
        "Content-Type": "application/json",
        "X-Iris-Connector": connector_id,
        "X-Iris-Timestamp": str(stamp),
        "X-Iris-Nonce": nonce,
        "X-Iris-Signature": hmac.new(key, material, hashlib.sha256).hexdigest(),
    }


def main() -> None:
    class Engine:
        def bind_tool_handler(self, _handler):
            pass

        def run_turn(self, turn):
            yield TurnFinished(f"echo:{turn.transcript.messages[-1].content}")

        def shutdown(self):
            pass

    with TemporaryDirectory() as root:
        gateway = NativeGateway(
            lambda: IrisAgentInferenceTarget("local", "fixture"),
            db_path=Path(root) / "gateway.db",
        )
        surface = ControlSurface(
            invoker=MainThreadInvoker(), port=0, token="control", gateway=gateway
        )
        with (
            patch("iris.system.native_gateway.shared_engine") as shared,
            patch("iris.system.control_surface.write_control_endpoint"),
            patch("iris.system.control_surface.clear_control_endpoint"),
        ):
            shared.return_value.fork.side_effect = Engine
            surface.start()
            surface.booting = False
            try:
                code, registered = _request(
                    surface,
                    "/v1/agent/connectors",
                    {"name": "loopback", "channels": ["support"]},
                    {"Authorization": "Bearer control", "Content-Type": "application/json"},
                )
                assert code == 201, registered
                connector_id = registered["connector_id"]
                secret = registered["secret"]
                result_token = registered["token"]
                payload = {
                    "event_id": "evt-1",
                    "channel_id": "support",
                    "actor_id": "user-7",
                    "thread_id": "case-9",
                    "message": "signed hello",
                }
                stamp = int(time())
                path = f"/v1/agent/connectors/{connector_id}/events"
                headers = _signed(secret, connector_id, payload, stamp=stamp, nonce="nonce-001")
                code, accepted = _request(surface, path, payload, headers)
                assert code == 202, accepted
                assert accepted["session_id"] and accepted["run_id"]
                events_path = f"/v1/agent/runs/{accepted['run_id']}/events"
                code, events = _get(surface, events_path, result_token)
                assert code == 200 and events[-1]["text"] == "echo:signed hello"
                assert _get(surface, events_path, "control")[0] == 404

                bad = dict(headers, **{"X-Iris-Signature": "0" * 64})
                assert _request(surface, path, {**payload, "event_id": "evt-bad"}, bad)[0] == 401
                assert _request(surface, path, payload, headers)[0] == 409
                expired = _signed(secret, connector_id, payload, stamp=stamp - 1000, nonce="nonce-old")
                assert _request(surface, path, {**payload, "event_id": "evt-old"}, expired)[0] == 401
                denied_payload = {**payload, "event_id": "evt-other", "channel_id": "other"}
                denied = _signed(secret, connector_id, denied_payload, stamp=stamp, nonce="nonce-002")
                assert _request(surface, path, denied_payload, denied)[0] == 403
                large = {**payload, "event_id": "evt-large", "message": "x" * 8001}
                signed_large = _signed(secret, connector_id, large, stamp=stamp, nonce="nonce-big")
                assert _request(surface, path, large, signed_large)[0] == 400

                control = {"Authorization": "Bearer control", "Content-Type": "application/json"}
                lifecycle = f"/v1/agent/connectors/{connector_id}"
                assert _request(surface, lifecycle + "/disconnect", {}, control)[1]["status"] == "disconnected"
                second = {**payload, "event_id": "evt-2", "message": "second"}
                signed = _signed(secret, connector_id, second, stamp=stamp, nonce="nonce-003")
                assert _request(surface, path, second, signed)[0] == 401
                assert _request(surface, lifecycle + "/reconnect", {}, control)[1]["status"] == "connected"
                code, reopened = _request(surface, path, second, signed)
                assert code == 202 and reopened["session_id"] == accepted["session_id"]
                assert _request(surface, lifecycle + "/revoke", {}, control)[1]["status"] == "revoked"
                assert _get(surface, events_path, result_token)[0] == 401
            finally:
                surface.stop()
    print("ok: signed webhook connector")


if __name__ == "__main__":
    main()
