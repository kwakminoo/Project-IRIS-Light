import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty, Queue
from threading import Event, Thread
from unittest.mock import patch

import pytest

from iris.engine._home import engine_python
from iris.engine.types import EngineHome
from iris.infrastructure.agent_runtime import iris_agent_home
from iris.mcp.native_manager import NativeMCPManager


def test_disabled_invalid_and_unregistered_servers_do_not_spawn(tmp_path):
    (tmp_path / "config.yaml").write_text("""
mcp_servers:
  disabled: {command: python, enabled: false}
  unknown: {command: python, transport: websocket}
  ambiguous: {command: python, url: 'https://example.test'}
  valid: {url: 'https://example.test/mcp', transport: sse}
""", encoding="utf-8")
    manager = NativeMCPManager(home=tmp_path)
    assert manager.catalog() == [
        {"name": "disabled", "status": "disabled", "transport": "stdio"},
        {"name": "unknown", "status": "unsupported_transport", "transport": "websocket"},
        {"name": "ambiguous", "status": "invalid_config", "transport": ""},
        {"name": "valid", "status": "configured", "transport": "sse"},
    ]
    with patch("iris.mcp.native_manager.subprocess.Popen") as spawn:
        assert manager.discover("disabled")["status"] == "disabled"
        assert manager.discover("unknown")["status"] == "unsupported_transport"
        assert manager.discover("missing")["status"] == "not_registered"
    spawn.assert_not_called()


def test_mcp_ui_uses_shared_catalog_without_exposing_credentials(tmp_path, monkeypatch):
    from iris.ui.chat import composer_plus_menu, skill_mcp_dialogs

    (tmp_path / "config.yaml").write_text(
        "mcp_servers: {demo: {command: python, args: [private-token]}, off-server: {command: python, enabled: false}}",
        encoding="utf-8",
    )
    monkeypatch.setattr(composer_plus_menu, "_iris_agent_root", lambda: tmp_path)
    monkeypatch.setattr(skill_mcp_dialogs, "iris_agent_root", lambda: tmp_path)
    assert composer_plus_menu.list_iris_agent_mcp_names() == ["demo", "off-server"]
    descriptions = dict(skill_mcp_dialogs.list_iris_agent_mcps())
    assert "private-token" not in descriptions["demo"]
    assert "비활성" in descriptions["off-server"]


def test_registration_and_mobile_sync_preserve_user_settings(tmp_path, monkeypatch):
    import yaml

    from iris.system.iris_agent_control_sync import ensure_mcp_in_config
    from iris.ui.chat import skill_mcp_dialogs

    path = tmp_path / "config.yaml"
    original = {"other_setting": "keep", "mcp_servers": {
        "mobile-mcp": {"command": "custom-mobile", "enabled": False, "env": {"API_TOKEN": "keep-secret"}},
    }}
    path.write_text(yaml.safe_dump(original), encoding="utf-8")
    monkeypatch.setattr(skill_mcp_dialogs, "iris_agent_root", lambda: tmp_path)
    with pytest.raises(RuntimeError):
        skill_mcp_dialogs.add_mcp_server("mobile-mcp", "replacement", "")
    assert yaml.safe_load(path.read_text(encoding="utf-8")) == original
    assert ensure_mcp_in_config(repo=tmp_path, home=tmp_path)[0]
    assert yaml.safe_load(path.read_text(encoding="utf-8")) == original

    skill_mcp_dialogs.add_mcp_server("new-server", "python", "server.py")
    manager = NativeMCPManager(home=tmp_path)
    manager.set_enabled("new-server", False)
    assert manager.discover("new-server")["status"] == "disabled"
    updated = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert updated["other_setting"] == "keep"
    assert updated["mcp_servers"]["mobile-mcp"] == original["mcp_servers"]["mobile-mcp"]
    assert yaml.safe_load((tmp_path / "config.yaml.bak-iris").read_text(encoding="utf-8")) == original


def test_legacy_health_probe_does_not_forward_credentials_on_redirect():
    from urllib.request import HTTPRedirectHandler

    from iris.system.iris_agent_control_sync import probe_mcp_server

    with patch("urllib.request.urlopen") as fetch:
        fetch.return_value.__enter__.return_value.status = 200
        assert probe_mcp_server("server", {
            "url": "https://mcp.test/health", "headers": {"Authorization": "Bearer fixture"},
        })["ok"]
    first = fetch.call_args.args[0]
    assert first.get_header("Authorization") == "Bearer fixture"
    redirected = HTTPRedirectHandler().redirect_request(first, None, 302, "Found", {}, "https://other.test/")
    assert redirected.get_header("Authorization") is None


def test_owned_stdio_sdk_discovers_resources_without_invoking_tools(tmp_path):
    import yaml

    if engine_python(EngineHome(iris_agent_home())) is None:
        pytest.skip("Owned Core is not installed")
    script = tmp_path / "fixture.py"
    script.write_text("""
import json
import pathlib
import sys

for line in sys.stdin:
    req = json.loads(line)
    method = req.get('method')
    with pathlib.Path(__file__).with_suffix('.methods').open('a') as methods:
        print(method, file=methods)
    if 'id' not in req:
        continue
    if method == 'initialize':
        result = {'protocolVersion': req['params']['protocolVersion'],
                  'capabilities': {'tools': {}, 'resources': {}, 'prompts': {}},
                  'serverInfo': {'name': 'fixture', 'version': '1'}}
    elif method == 'tools/list':
        cursor = (req.get('params') or {}).get('cursor')
        if cursor == 'page-2':
            result = {'tools': [{'name': 'touch_again', 'inputSchema': {'type': 'object'}}]}
        else:
            result = {'tools': [{'name': 'touch', 'inputSchema': {'type': 'object'}}], 'nextCursor': 'page-2'}
    elif method == 'resources/list':
        result = {'resources': [{'uri': 'ui://fixture/app', 'name': 'app'}]}
    elif method == 'prompts/list':
        result = {'prompts': [{'name': 'template'}]}
    else:
        pathlib.Path(__file__).with_suffix('.called').touch()
        result = {}
    print(json.dumps({'jsonrpc': '2.0', 'id': req['id'], 'result': result}), flush=True)
""", encoding="utf-8")
    (tmp_path / "config.yaml").write_text(yaml.safe_dump({"mcp_servers": {
        "fixture": {"command": sys.executable, "args": [str(script)]},
    }}), encoding="utf-8")
    manager = NativeMCPManager(home=tmp_path)
    found = manager.discover("fixture", timeout=10)
    methods = script.with_suffix(".methods")
    assert found["status"] == "connected", (found, methods.read_text() if methods.exists() else "no server messages")
    assert [row["name"] for row in found["tools"]] == ["touch", "touch_again"]
    assert [row["uri"] for row in found["resources"]] == ["ui://fixture/app"]
    assert [row["name"] for row in found["prompts"]] == ["template"]
    assert not script.with_suffix(".called").exists()


@pytest.mark.parametrize("transport", ["streamable_http", "sse"])
def test_http_auth_and_discovery(tmp_path, transport):
    import yaml

    if engine_python(EngineHome(iris_agent_home())) is None:
        pytest.skip("Owned Core is not installed")
    received = []
    sse_messages = Queue()
    stopped = Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if transport != "sse":
                self.send_error(405)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b"event: endpoint\ndata: /messages\n\n")
            self.wfile.flush()
            while not stopped.is_set():
                try:
                    body = sse_messages.get(timeout=0.1)
                except Empty:
                    continue
                self.wfile.write(b"event: message\ndata: " + body + b"\n\n")
                self.wfile.flush()

        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            method = req["method"]
            received.append((method, self.headers.get("Authorization")))
            if "id" not in req:
                self.send_response(202)
                self.end_headers()
                return
            if method == "initialize":
                result = {"protocolVersion": req["params"]["protocolVersion"], "capabilities": {"tools": {}},
                          "serverInfo": {"name": "http-fixture", "version": "1"}}
            elif method == "tools/list":
                result = {"tools": [{"name": "read", "inputSchema": {"type": "object"}}]}
            else:
                self.send_error(404)
                return
            body = json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": result}).encode()
            if transport == "sse":
                self.send_response(202)
                self.end_headers()
                sse_messages.put(body)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as httpd:
        serving = Thread(target=httpd.serve_forever, daemon=True)
        serving.start()
        try:
            (tmp_path / "config.yaml").write_text(yaml.safe_dump({"mcp_servers": {
                "fixture": {"url": f"http://127.0.0.1:{httpd.server_port}/mcp", "transport": transport,
                            "headers": {"Authorization": "Bearer test-token"}},
            }}), encoding="utf-8")
            result = NativeMCPManager(home=tmp_path).discover("fixture", timeout=10)
            assert result["status"] == "connected", (result, received)
            assert result["tools"][0]["name"] == "read"
        finally:
            stopped.set()
            httpd.shutdown()
            serving.join(timeout=5)
    assert received == [
        ("initialize", "Bearer test-token"), ("notifications/initialized", "Bearer test-token"),
        ("tools/list", "Bearer test-token"),
    ]
