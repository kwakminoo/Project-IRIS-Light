"""Independent Wave 1.7 evidence. Run from the repository with --help."""

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


BASELINE = "c51d5ba6e88157ad7d9c9fb196a49aa8094e4bfe"
SCOPES = (
    "AGENTS.md", "IRIS_launcher.py", "IRIS.spec", "requirements.txt", "REVISION",
    "package-lock.json", "setup.ps1", "setup.sh", "setup.bat", "run.bat", "run.sh",
    ".github", "iris", "vendor", "tests", "scripts", "installer", "services", "integrations",
)
MODEL = "gpt-oss:20b"


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def git(*args):
    return subprocess.check_output(["git", *args]).decode("utf-8")


def definitions(source, parents=()):
    for node in source.body:
        if isinstance(node, ast.ClassDef):
            name = (*parents, node.name)
            yield ".".join(name), (node.lineno, ast.dump(node))
            yield from definitions(node, name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield ".".join((*parents, node.name)), (node.lineno, ast.dump(node))


def inventory(out):
    head = git("rev-parse", "HEAD").strip()
    names = set(git("ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *SCOPES).split("\0")) - {""}
    files = {}
    for name in sorted(names):
        path = Path(name)
        if path.is_file():
            with path.open("rb") as stream:
                files[name] = hashlib.file_digest(stream, "sha256").hexdigest()
        else:
            files[name] = None
    encoded = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    fingerprint = hashlib.sha256(encoded).hexdigest()
    write_json(out / "source.json", {"head": head, "fingerprint": fingerprint, "file_count": len(files), "files": files})
    tracked_changes = set(git("diff", "--name-only", "-z", BASELINE).split("\0")) - {""}
    untracked = set(git("ls-files", "-z", "--others", "--exclude-standard").split("\0")) - {""}
    baseline_files = set(git("ls-tree", "-r", "--name-only", "-z", BASELINE, "--", *SCOPES).split("\0"))
    rows = []
    for name in sorted(tracked_changes | untracked):
        if not name.endswith(".py") or name not in names:
            continue
        path = Path(name)
        old = dict(definitions(ast.parse(git("show", f"{BASELINE}:{name}")))) if name in baseline_files else {}
        new = dict(definitions(ast.parse(path.read_text(encoding="utf-8-sig")))) if path.is_file() else {}
        for symbol in sorted(old.keys() | new.keys()):
            before = old.get(symbol, (None, None))
            after = new.get(symbol, (None, None))
            if before[1] != after[1]:
                rows.append({"file": name, "symbol": symbol, "before": before[0], "after": after[0]})
    write_json(out / "symbols.json", rows)
    symbols = sorted({row["symbol"].rsplit(".", 1)[-1] for row in rows if row["before"] is not None})
    pattern = r"\b(?:" + "|".join(map(re.escape, symbols)) + r")\b"
    with (out / "symbol-references.txt").open("wb") as stream:
        result = subprocess.run(["rg", "-n", pattern, *SCOPES], stdout=stream, check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"rg exited with {result.returncode}")
    print(f"{head} {fingerprint} ({len(files)} files, {len(rows)} changed definitions)")


MCP_SERVER = '''\
from pathlib import Path
from uuid import uuid4
from mcp.server.mcpserver import MCPServer

server = MCPServer("Iris validation fixture")

@server.tool()
def fetch_iridium_validation_code() -> str:
    """Return the freshly generated iridium validation code."""
    code = "IRIS-MCP-" + uuid4().hex
    with Path(__file__).with_suffix(".calls").open("a", encoding="utf-8") as log:
        print(code, file=log)
    return code

server.run(transport="stdio")
'''

MCP_CONTROL = '''\
import asyncio
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    async with stdio_client(StdioServerParameters(command=sys.argv[2], args=[sys.argv[1]])) as (reader, writer, *_):
        async with ClientSession(reader, writer) as client:
            await client.discover()
            response = await client.call_tool("fetch_iridium_validation_code", {})
            assert not response.is_error
            print(response.content[0].text)

asyncio.run(main())
'''


def live(out, mode, attempts):
    from iris.engine import CancelToken, ChatTranscript, Engine, EngineHome, InternalSidecar, StatelessTurn, TurnFinished
    from iris.engine import runtime
    from iris.engine._home import engine_python
    from iris.infrastructure.agent_runtime import iris_agent_home
    from iris.infrastructure.agent_tool_registry import speak_invoke_agent_tool
    from iris.infrastructure.iris_agent_client import resolve_iris_agent_inference
    from iris.infrastructure.speak_capability import bind_live_control_surface
    from iris.mcp.native_manager import NativeMCPManager
    from iris.system.control_surface import ActionRegistry
    from iris.ui.control_actions.local_files import register_local_file_actions

    py = engine_python(EngineHome(iris_agent_home()))
    if py is None:
        raise RuntimeError("No verified Owned Core Python")
    target = resolve_iris_agent_inference(MODEL)
    if target.base_url != "http://127.0.0.1:11434/v1":
        raise RuntimeError("Expected the local Ollama fixture endpoint")
    results = []
    for number in range(1, attempts + 1):
        home = out / f"{mode}-{number:02}"
        home.mkdir()
        (home / "config.yaml").write_text("agent:\n  tool_choice: auto\nmodel:\n  ollama_num_ctx: 64000\n", encoding="utf-8")
        calls = []
        engine = Engine(InternalSidecar(home=EngineHome(home)), staged_python=py)
        if mode == "mcp":
            script = home / "fixture.py"
            script.write_text(MCP_SERVER, encoding="utf-8")
            manager = NativeMCPManager(home=home)
            manager.register("iridium-fixture", {"command": str(py), "args": [str(script)]})
            discovery = manager.discover("iridium-fixture", timeout=12)
            assert discovery["status"] == "connected", discovery
            assert [row["name"] for row in discovery["tools"]] == ["fetch_iridium_validation_code"], discovery
            control = subprocess.run([str(py), "-I", "-c", MCP_CONTROL, str(script), str(py)],
                                     capture_output=True, text=True, timeout=25)
            assert control.returncode == 0, control.stderr
            call_file = script.with_suffix(".calls")
            assert control.stdout.strip() == call_file.read_text(encoding="utf-8").strip()
            call_file.unlink()
            expected = ""
            prompt = "Get a fresh iridium validation code from the connected iridium validation service and report the exact code."
        else:
            from uuid import uuid4

            workspace = home / "workspace"
            workspace.mkdir()
            expected = "IRIS-NATIVE-" + uuid4().hex
            (workspace / "iridium-inventory.txt").write_text(expected, encoding="utf-8")
            attachments = SimpleNamespace(roots={"fixture": SimpleNamespace(path=str(workspace), directory=True)})
            window = SimpleNamespace(_chat_session=SimpleNamespace(attachments=attachments))
            registry = ActionRegistry()
            register_local_file_actions(window, registry)
            bind_live_control_surface(SimpleNamespace(registry=registry, booting=False))
            prompt = (f'In the attached directory "{workspace}", find the inventory file with iridium in its filename. '
                      "Then read that file and reply with its exact contents.")

        def invoke(action, payload):
            result = speak_invoke_agent_tool(action, payload)
            calls.append({"action": action, "ok": result.get("ok") is True})
            return result

        engine.bind_tool_handler(invoke)
        start = time.perf_counter()
        try:
            with patch.object(runtime, "_WATCH_LOG", home / "host-watch.log"):
                turn = StatelessTurn(ChatTranscript.parse([{"role": "user", "content": prompt}]), target, CancelToken())
                events = list(engine.run_turn(turn))
        finally:
            engine.shutdown()
            bind_live_control_surface(None)
        answer = next((event.text for event in events if isinstance(event, TurnFinished)), "")
        if mode == "mcp":
            markers = call_file.read_text(encoding="utf-8").splitlines() if call_file.exists() else []
            ok = bool(markers and markers[-1] == answer.strip())
        else:
            markers = [expected]
            ok = (expected == answer.strip() and [row["action"] for row in calls if row["ok"]] ==
                  ["local.search_files", "local.read_file"])
        row = {"attempt": number, "status": "PASS" if ok else "FAIL", "model": MODEL, "tool_choice": "auto",
               "seconds": round(time.perf_counter() - start, 3), "calls": calls, "markers": markers,
               "answer": answer, "events": [type(event).__name__ for event in events],
               "terminal_type": type(events[-1]).__name__ if events else None}
        if mode == "mcp":
            row.update(discovery=discovery, direct_sdk_control="PASS", model_mcp_invocations=len(markers))
        results.append(row)
        write_json(out / f"{mode}-results.json", results)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    return 0 if all(row["status"] == "PASS" for row in results) else 1


def gui_chat(out):
    import faulthandler

    from iris.engine import Engine, EngineHome, InternalSidecar, runtime
    from iris.engine._home import engine_python
    from iris.infrastructure.agent_runtime import iris_agent_home

    py = engine_python(EngineHome(iris_agent_home()))
    assert py is not None, "No verified Owned Core Python"
    faulthandler.enable()
    root = out / "profile"
    root.mkdir()
    agent_home = root / "agent"
    agent_home.mkdir()
    (agent_home / "config.yaml").write_text("model:\n  ollama_num_ctx: 64000\n", encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if not key.startswith(("IRIS_", "OLLAMA_", "HERMES_"))}
    env.update(USERPROFILE=str(root), HOME=str(root), APPDATA=str(root), LOCALAPPDATA=str(root),
               TMP=str(root), TEMP=str(root), PYTHON_DOTENV_DISABLED="1", IRIS_AGENT_HOME=str(agent_home),
               IRIS_OLLAMA_MODEL=MODEL, IRIS_CONTROL_ENABLED="0", IRIS_DB_PATH=str(root / "iris.db"))
    engine = Engine(InternalSidecar(home=EngineHome(agent_home)), staged_python=py)
    proof = {"model": MODEL, "owned_python": str(py), "status": "FAIL"}

    with patch.dict(os.environ, env, clear=True):
        from PyQt6.QtCore import QSettings, QTimer
        from PyQt6.QtWidgets import QApplication

        from iris.storage.conversations import list_messages
        from iris.system.setup_protocol import save_setup_state
        from iris.ui._check_fpr_product_gui import _until
        from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

        ensure_qt_webengine_ready()
        from iris.ui.window.main_window import MainWindow

        def check(window):
            from uuid import uuid4

            _until(lambda: window._chat.current_model() == MODEL, timeout=30)
            window._chat._open_model_picker_menu()
            assert window._chat._model_picker_menu.isVisible()
            window._chat._model_picker_menu.close()
            _until(lambda: window._control_surface is not None and not window._control_surface.booting, timeout=30)
            assert window._control_surface.bound_port is None
            marker = "IRIS-GUI-" + uuid4().hex[:10]
            start = time.perf_counter()
            window._chat.set_input_text(f"Reply with exactly {marker} and no other text.")
            window._chat.submit_input()
            _until(lambda: bool(window._conversation_id), timeout=10)
            cid = window._conversation_id
            worker = window._runs.slot(cid).worker
            chunks = []
            if hasattr(worker, "content_chunk"):
                worker.content_chunk.connect(chunks.append)
            _until(lambda: any(message.role == "assistant" for message in list_messages(window._db, cid)), timeout=180)
            messages = list_messages(window._db, cid)
            assert messages[-1].role == "assistant" and messages[-1].content.strip() == marker, messages[-1].content
            proof.update(marker=marker, elapsed_seconds=round(time.perf_counter() - start, 3),
                         streamed_chunks=len(chunks), conversation=cid, gateway_http_disabled=True,
                         worker_type=type(worker).__name__)
            write_json(out / "gui-chat.json", proof)
            assert type(worker).__name__ == "IrisAgentChatWorker", proof
            window._on_new_chat_requested()
            assert window._conversation_id != cid
            window._on_conversation_selected(cid)
            assert window._conversation_id == cid
            _until(lambda: (view := window._chat.transcript()._view) is not None and view.isVisible())
            view = window._chat.transcript()._view
            rendered = []
            view.page().runJavaScript("document.body.innerText", rendered.append)
            _until(lambda: bool(rendered))
            assert marker in rendered[0], rendered[0]
            proof.update(conversation_switch=True, transcript_restored=True, status="PARTIAL")
            write_json(out / "gui-chat.json", proof)

        try:
            QSettings.setDefaultFormat(QSettings.Format.IniFormat)
            QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(root))
            app = QApplication(["iris-wave17-validation"])
            assert app.platformName() not in {"offscreen", "minimal"}
            save_setup_state({"core_ready": True})
            with (patch.object(runtime, "_SHARED", engine), patch.object(runtime, "_WATCH_LOG", root / "engine.log"),
                  patch.object(MainWindow, "_schedule_core_warm"), patch.object(MainWindow, "_repair_taskbar_pins"),
                  patch.object(MainWindow, "_register_toast_click"),
                  patch.object(MainWindow, "_begin_app_update_check"), patch.object(MainWindow, "_begin_iris_agent_update_check")):
                window = MainWindow()
                window.show()
                errors = []

                def drive():
                    try:
                        _until(lambda: window.windowOpacity() > 0.9 and window._intro is not None)
                        check(window)
                    except Exception as error:
                        errors.append(error)
                    finally:
                        window.close()
                        app.quit()

                QTimer.singleShot(0, drive)
                assert app.exec() == 0
                if errors:
                    raise errors[0]
                proof["window_closed"] = True
                proof["status"] = "PASS"
        finally:
            engine.shutdown()
            write_json(out / "gui-chat.json", proof)


def gui_product_home(out):
    from iris.ui import _check_fpr_product_gui as gui
    from iris.ui import _check_local_vibe_smoke as smoke

    runner_home = out / "runner-profile"
    runner_home.mkdir()

    def run_fpr(_argv):
        env = {**os.environ, "USERPROFILE": str(runner_home), "HOME": str(runner_home)}
        return subprocess.run([
            sys.executable, "-m", "iris.system._check_fpr13_runner",
            "--product-home", os.environ["USERPROFILE"], "--out-dir", str(out),
        ], env=env, check=False).returncode

    with patch.object(smoke, "main", run_fpr), patch.object(sys, "argv", ["iris-product-gui-check", "ide"]):
        gui.main()


def gateway_restart(out):
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    from iris.engine import Engine, EngineHome, InternalSidecar, runtime
    from iris.engine._home import engine_python
    from iris.infrastructure.agent_runtime import iris_agent_home
    from iris.infrastructure.iris_agent_client import resolve_iris_agent_inference
    from iris.system.control_surface import ControlSurface, MainThreadInvoker
    from iris.system.native_gateway import NativeGateway

    py = engine_python(EngineHome(iris_agent_home()))
    assert py is not None, "No verified Owned Core Python"
    agent_home = out / "agent"
    agent_home.mkdir()
    engine = Engine(InternalSidecar(home=EngineHome(agent_home)), staged_python=py)
    fixture_token = "wave17-fixture-token"
    target = resolve_iris_agent_inference(MODEL)
    assert target.base_url == "http://127.0.0.1:11434/v1", "Expected the local Ollama fixture endpoint"

    def surface():
        return ControlSurface(invoker=MainThreadInvoker(), port=0, token=fixture_token,
                              gateway=NativeGateway(lambda: target))

    def request(port, path, *, token=fixture_token, payload=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        body = json.dumps(payload).encode() if payload is not None else None
        try:
            response = urlopen(Request(f"http://127.0.0.1:{port}{path}", data=body, headers=headers), timeout=60)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            if response.headers.get_content_type() == "application/x-ndjson":
                return response.status, [json.loads(row) for row in raw.splitlines()]
            return response.status, json.loads(raw)

    proof = {}
    with (patch("iris.system.native_gateway.shared_engine", return_value=engine),
          patch("iris.system.control_surface.write_control_endpoint"),
          patch("iris.system.control_surface.clear_control_endpoint"),
          patch.object(runtime, "_WATCH_LOG", out / "engine.log")):
        first = surface()
        port = first.start()
        try:
            proof["booting"] = request(port, "/v1/agent/health")[0]
            first.booting = False
            proof["unauthenticated"] = request(port, "/v1/agent/health", token="")[0]
            proof["incorrect_token"] = request(port, "/v1/agent/health", token="wrong-fixture-token")[0]
            proof["ready"] = request(port, "/v1/agent/health")[0]
            marker = "IRIS-W17-RESTART"
            code, run = request(port, "/v1/agent/runs", payload={"message": f"Reply with exactly {marker}"})
            assert code == 202, run
            run_path = "/v1/agent/runs/" + run["run_id"]
            session_path = "/v1/agent/sessions/" + run["session_id"]
            code, events = request(port, run_path + "/events")
            assert code == 200 and events, (code, events)
            proof["stream_events"] = [row["type"] for row in events]
            proof["grounded_reply"] = events[-1]["type"] == "finished" and marker in events[-1].get("text", "")
            proof["same_process_session"] = request(port, session_path)[0]
        finally:
            start = time.perf_counter()
            first.stop()
            proof["shutdown_seconds"] = round(time.perf_counter() - start, 3)
            write_json(out / "gateway-result.json", proof)

        second = surface()
        port = second.start()
        try:
            second.booting = False
            proof["after_restart_session"] = request(port, session_path)[0]
            proof["after_restart_run"] = request(port, run_path)[0]
        finally:
            second.stop()
    write_json(out / "gateway-result.json", proof)
    assert proof["booting"] == 503 and proof["ready"] == 200 and proof["grounded_reply"], proof
    assert proof["same_process_session"] == 200, proof
    assert proof["unauthenticated"] == proof["incorrect_token"] == 401, proof
    return 0 if proof["after_restart_session"] == proof["after_restart_run"] == 200 else 1


def mcp_timeout(out):
    from iris.mcp.native_manager import NativeMCPManager

    server = out / "slow_fixture.py"
    server.write_text("import time\ntime.sleep(20)\n", encoding="utf-8")
    manager = NativeMCPManager(home=out)
    manager.register("slow-fixture", {"command": sys.executable, "args": [str(server)]})
    start = time.perf_counter()
    reply = manager.discover("slow-fixture", timeout=2)
    proof = {"reply": reply, "seconds": round(time.perf_counter() - start, 3)}
    write_json(out / "mcp-timeout.json", proof)
    assert reply["status"] == "timeout", proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inventory", "mcp", "native", "gui-chat", "gui-product-home",
                                         "gateway-restart", "mcp-timeout"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--attempts", type=int, default=1)
    args = parser.parse_args()
    if args.attempts < 1:
        parser.error("--attempts must be positive")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.mode == "inventory":
        inventory(out)
        return 0
    if args.mode == "gui-chat":
        gui_chat(out)
        return 0
    if args.mode == "gui-product-home":
        gui_product_home(out)
        return 0
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    if args.mode == "gateway-restart":
        return gateway_restart(out)
    if args.mode == "mcp-timeout":
        mcp_timeout(out)
        return 0
    return live(out, args.mode, args.attempts)


if __name__ == "__main__":
    sys.exit(main())
