import json
import os
from threading import Event
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from iris.engine import ContentDelta, Engine, EngineHome, InternalSidecar, TurnCancelled, TurnFinished
from iris.engine._home import engine_python
from iris.infrastructure.agent_runtime import iris_agent_home
from iris.infrastructure.iris_agent_client import IrisAgentInferenceTarget, resolve_iris_agent_inference
from iris.infrastructure.speak_capability import default_speak_tools, engine_tool_bindings
from iris.system.control_surface import ControlSurface, MainThreadInvoker
from iris.system.execution_context import ExecutionContext, bind_host_tool_call_meta
from iris.system.native_gateway import NativeGateway


def _request(surface, path, payload=None, *, auth=True, post=False):
    headers = {"Authorization": "Bearer test-key"} if auth else {}
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(f"http://127.0.0.1:{surface.bound_port}{path}", data=data, headers=headers,
                  method="POST" if post else None)
    try:
        response = urlopen(req, timeout=20)
    except HTTPError as exc:
        response = exc
    with response:
        raw = response.read()
        if response.headers.get_content_type() == "application/x-ndjson":
            return response.code, [json.loads(line) for line in raw.splitlines()]
        return response.code, json.loads(raw)


def test_gateway_dispatch_grants_only_ping():
    assert {binding.canonical_action for binding in engine_tool_bindings("gateway")} == {"ping"}
    with bind_host_tool_call_meta(execution_context=ExecutionContext(surface="gateway")):
        assert default_speak_tools().invoke("ping", {}).ok
        assert not default_speak_tools().invoke("wiki.list_notes", {}).ok
        assert not default_speak_tools().invoke("shell.run", {}).ok


def test_authenticated_http_runs_use_owned_engine_and_owned_sessions():
    entered = Event()
    release = Event()
    turns = []

    class TestEngine:
        def run_turn(self, turn):
            turns.append(turn)
            if turn.transcript.messages[-1].content == "wait":
                entered.set()
                assert release.wait(5)
                assert turn.cancel.cancelled()
                yield TurnCancelled()
                return
            yield ContentDelta("hel")
            yield TurnFinished("hello")

        def bind_tool_handler(self, handler):
            assert callable(handler)

        def shutdown(self):
            pass

    gateway = NativeGateway(lambda: IrisAgentInferenceTarget("local", "custom"))
    surface = ControlSurface(invoker=MainThreadInvoker(), port=0, token="test-key", gateway=gateway)

    def request(path, payload=None, **options):
        return _request(surface, path, payload, **options)

    with (
        patch("iris.system.native_gateway.shared_engine") as shared,
        patch("iris.system.control_surface.write_control_endpoint"),
        patch("iris.system.control_surface.clear_control_endpoint"),
    ):
        shared.return_value.fork.side_effect = TestEngine
        surface.start()
        try:
            assert request("/v1/agent/capabilities", auth=False)[0] == 401
            assert request("/v1/agent/health")[0] == 503
            assert request("/v1/agent/runs", {"message": "hi"})[0] == 503
            surface.booting = False
            assert request("/v1/agent/health")[1]["ready"]
            assert request("/v1/agent/runs", {"message": "hi", "session_id": "1"})[0] == 404
            assert request("/v1/agent/runs", {"message": "hi", "principal": "admin"})[0] == 400
            code, opened = request("/v1/agent/runs", {"message": "hi"})
            assert code == 202, opened
            run = "/v1/agent/runs/" + opened["run_id"]
            sid = opened["session_id"]
            code, events = request(run + "/events")
            assert code == 200
            assert [(row["seq"], row["type"]) for row in events] == [(1, "delta"), (2, "finished")]
            assert request(run + "/events?after=1")[1] == [events[-1]]
            assert request(run)[1]["status"] == "finished"
            assert request(f"/v1/agent/sessions/{sid}")[1]["messages"] == [
                {"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"},
            ]

            code, pending = request("/v1/agent/runs", {"message": "wait", "session_id": sid})
            assert code == 202 and entered.wait(3)
            assert turns[-1].execution_context.session_id == sid
            assert turns[-1].execution_context.principal == "iris.local_gateway"
            assert turns[-1].speak_surface == "gateway"
            assert [m.content for m in turns[-1].transcript.messages] == ["hi", "hello", "wait"]
            assert request("/v1/agent/runs", {"message": "concurrent", "session_id": sid})[0] == 409
            run = "/v1/agent/runs/" + pending["run_id"]
            assert request(run + "/cancel", post=True)[0] == 202
            release.set()
            assert request(run + "/events")[1][-1]["type"] == "cancelled"
            assert len(request(f"/v1/agent/sessions/{sid}")[1]["messages"]) == 2
        finally:
            release.set()
            surface.stop()


@pytest.mark.skipif(os.environ.get("IRIS_WAVE17_LIVE") != "1", reason="requires installed Owned Core and local Ollama")
def test_live_gateway_owned_model(tmp_path):
    installed = engine_python(EngineHome(iris_agent_home()))
    assert installed is not None
    engine = Engine(InternalSidecar(home=EngineHome(tmp_path)), staged_python=installed)
    gateway = NativeGateway(lambda: resolve_iris_agent_inference("gpt-oss:20b"))
    surface = ControlSurface(invoker=MainThreadInvoker(), port=0, token="test-key", gateway=gateway)
    with (
        patch("iris.system.native_gateway.shared_engine", return_value=engine),
        patch("iris.system.control_surface.write_control_endpoint"),
        patch("iris.system.control_surface.clear_control_endpoint"),
        patch("iris.engine.runtime._WATCH_LOG", tmp_path / "watch.log"),
    ):
        surface.start()
        surface.booting = False
        try:
            code, opened = _request(surface, "/v1/agent/runs", {"message": "Reply with exactly IRIS-W17-GATEWAY"})
            assert code == 202
            code, events = _request(surface, f"/v1/agent/runs/{opened['run_id']}/events")
            assert code == 200
            assert events[-1]["type"] == "finished", events[-1]
            assert "IRIS-W17-GATEWAY" in events[-1]["text"]
        finally:
            surface.stop()
