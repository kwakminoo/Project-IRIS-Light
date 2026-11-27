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
from iris.system.control_surface import ActionSpec, ControlSurface, MainThreadInvoker
from iris.system.execution_context import ExecutionContext, bind_host_tool_call_meta
from iris.system.native_gateway import NativeGateway


def _request(surface, path, payload=None, *, auth=True, post=False, token="test-key"):
    headers = {"Authorization": f"Bearer {token}"} if auth else {}
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


def test_gateway_dispatch_grants_only_safe_capabilities():
    assert {binding.canonical_action for binding in engine_tool_bindings("gateway")} == {"ping", "get_catalog"}
    with bind_host_tool_call_meta(execution_context=ExecutionContext(surface="gateway")):
        assert default_speak_tools().invoke("ping", {}).ok
        assert {row["name"] for row in default_speak_tools().invoke("get_catalog", {}).data["tools"]} == {"ping", "get_catalog"}
        assert not default_speak_tools().invoke("wiki.list_notes", {}).ok
        assert not default_speak_tools().invoke("shell.run", {}).ok


def test_gateway_token_scope_ownership_rotation_and_revocation(tmp_path):
    class FixtureEngine:
        def bind_tool_handler(self, handler):
            pass

        def run_turn(self, turn):
            yield TurnFinished("fixture")

        def shutdown(self):
            pass

    base = "/v1/agent"
    gateway = NativeGateway(lambda: IrisAgentInferenceTarget("local", "custom"), db_path=tmp_path / "gateway.db")
    surface = ControlSurface(invoker=MainThreadInvoker(), port=0, token="test-key", gateway=gateway)
    with (
        patch("iris.system.native_gateway.shared_engine") as shared,
        patch("iris.system.control_surface.write_control_endpoint"),
        patch("iris.system.control_surface.clear_control_endpoint"),
    ):
        shared.return_value.fork.side_effect = FixtureEngine
        surface.start()
        surface.booting = False
        try:
            code, issued = _request(surface, base + "/tokens", {"scopes": ["read", "run"], "ttl_seconds": 60})
            assert code == 201, issued
            client = issued["token"]
            assert _request(surface, "/v1/catalog", token=client)[0] == 401
            assert _request(surface, base + "/tokens", {}, token=client)[0] == 401
            code, run = _request(surface, base + "/runs", {"message": "hello"}, token=client)
            assert code == 202, run
            run_path = base + "/runs/" + run["run_id"]
            session_path = base + "/sessions/" + run["session_id"]
            assert _request(surface, run_path + "/events", token=client)[1][-1]["type"] == "finished"
            assert _request(surface, session_path)[0] == 404
            search = base + "/sessions/search?q=HELLO"
            code, matches = _request(surface, search, token=client)
            assert code == 200 and matches["hits"] == [
                {"session_id": run["session_id"], "role": "user", "snippet": "hello"},
            ]
            assert _request(surface, search)[1] == {"hits": []}
            assert _request(surface, base + "/sessions/search?q=%25", token=client)[1] == {"hits": []}
            assert _request(surface, base + "/sessions/search?q=", token=client)[0] == 400
            assert _request(surface, run_path + "/cancel", token=client, post=True)[0] == 403
            token_path = base + "/tokens/" + issued["token_id"]
            code, rotated = _request(surface, token_path + "/rotate", {"ttl_seconds": 60})
            assert code == 200, rotated
            assert _request(surface, session_path, token=client)[0] == 401
            assert _request(surface, session_path, token=rotated["token"])[0] == 200
            assert _request(surface, token_path + "/revoke", {})[0] == 200
            assert _request(surface, session_path, token=rotated["token"])[0] == 401
        finally:
            surface.stop()


def test_gateway_approval_requires_control_bearer(tmp_path):
    class FixtureEngine:
        def bind_tool_handler(self, handler):
            pass

        def bind_mcp_approval(self, handler):
            self.confirm = handler

        def run_turn(self, turn):
            accepted = self.confirm(ActionSpec("MCP", "fixture → write", confirm_required=True), {"text": "{}"})
            yield TurnFinished("accepted" if accepted else "denied")

        def shutdown(self):
            pass

    base = "/v1/agent"
    gateway = NativeGateway(lambda: IrisAgentInferenceTarget("local", "custom"), db_path=tmp_path / "gateway.db")
    surface = ControlSurface(invoker=MainThreadInvoker(), port=0, token="test-key", gateway=gateway)
    with (
        patch("iris.system.native_gateway.shared_engine") as shared,
        patch("iris.system.control_surface.write_control_endpoint"),
        patch("iris.system.control_surface.clear_control_endpoint"),
    ):
        shared.return_value.fork.side_effect = FixtureEngine
        surface.start()
        surface.booting = False
        try:
            code, issued = _request(surface, base + "/tokens", {"scopes": ["read", "run", "mcp"]})
            assert code == 201
            client = issued["token"]
            code, run = _request(surface, base + "/runs", {"message": "hello"}, token=client)
            assert code == 202
            from time import monotonic, sleep

            run_path = base + "/runs/" + run["run_id"]
            path = run_path + "/approval"
            deadline = monotonic() + 3
            while True:
                code, pending = _request(surface, path)
                if code == 200 or monotonic() >= deadline:
                    break
                sleep(0.02)
            assert code == 200 and pending["summary"] == "fixture → write"
            decision = {"approval_id": pending["approval_id"], "decision": "approve"}
            assert _request(surface, path, decision, token=client)[0] == 401
            assert _request(surface, path, decision)[0] == 200
            events = _request(surface, run_path + "/events", token=client)[1]
            assert [row["type"] for row in events] == ["approval_required", "approval_resolved", "finished"]
            assert events[-1]["text"] == "accepted"
            assert _request(surface, path, decision)[0] == 404
        finally:
            surface.stop()


def test_authenticated_http_runs_use_owned_engine_and_owned_sessions(tmp_path):
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

    target = lambda: IrisAgentInferenceTarget("local", "custom")
    path = tmp_path / "gateway.db"
    gateway = NativeGateway(target, db_path=path)
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

        reopened = NativeGateway(target, db_path=path)
        try:
            assert reopened.get(f"/v1/agent/sessions/{sid}")[1]["messages"] == [
                {"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"},
            ]
            assert reopened.get(run)[1]["status"] == "cancelled"
            assert list(reopened.events(opened["run_id"], 1)) == [events[-1]]
            assert reopened.search_sessions("hello")[1]["hits"] == [
                {"session_id": sid, "role": "assistant", "snippet": "hello"},
            ]
        finally:
            reopened.close()


@pytest.mark.skipif(os.environ.get("IRIS_WAVE17_LIVE") != "1", reason="requires installed Owned Core and local Ollama")
def test_live_gateway_owned_model(tmp_path):
    installed = engine_python(EngineHome(iris_agent_home()))
    assert installed is not None
    engine = Engine(InternalSidecar(home=EngineHome(tmp_path)), staged_python=installed)
    gateway = NativeGateway(lambda: resolve_iris_agent_inference("gpt-oss:20b"), db_path=tmp_path / "gateway.db")
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
