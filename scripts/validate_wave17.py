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
from dataclasses import replace
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
        old = dict(definitions(ast.parse(git("show", f"{BASELINE}:{name}").removeprefix("\ufeff")))) if name in baseline_files else {}
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
        result = subprocess.run(["rg", "-n", pattern, *(scope for scope in SCOPES if Path(scope).exists())],
                                stdout=stream, check=False)
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
    from iris.system.iris_agent_control_sync import edit_mcp_servers
    from iris.system.control_surface import ActionRegistry
    from iris.system.execution_context import ExecutionContext
    from iris.ui.control_actions.local_files import register_local_file_actions

    py = engine_python(EngineHome(iris_agent_home()))
    if py is None:
        raise RuntimeError("No verified Owned Core Python")
    target = resolve_iris_agent_inference(
        MODEL, ollama_base_url=os.environ.get("IRIS_WAVE17_OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
    )
    if not re.fullmatch(r"http://127\.0\.0\.1:[0-9]{1,5}/v1", target.base_url):
        raise RuntimeError("Expected the local Ollama fixture endpoint")
    target = replace(target, api_key="ollama")
    results = []
    for number in range(1, attempts + 1):
        from uuid import uuid4

        home = out / f"{mode}-{number:02}"
        home.mkdir()
        (home / "config.yaml").write_text("agent:\n  tool_choice: auto\nmodel:\n  ollama_num_ctx: 64000\n", encoding="utf-8")
        calls = []
        registry = ActionRegistry()
        remote = mode in {"mcp", "mixed"}
        engine = Engine(InternalSidecar(home=EngineHome(home)), staged_python=py)
        if remote:
            script = home / "fixture.py"
            script.write_text(MCP_SERVER, encoding="utf-8")
            manager = NativeMCPManager(home=home)
            manager.register("iridium-fixture", {"command": str(py), "args": [str(script)], "model_enabled": True})
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
            def approve_fixture(spec, preview):
                allowed = spec.name == "MCP" and spec.summary == "iridium-fixture → fetch_iridium_validation_code" and preview == {"text": "{}"}
                calls.append({"action": "mcp.approval", "ok": allowed})
                return allowed

            registry.set_human_confirm(approve_fixture)
            prompt = "Get a fresh iridium validation code from the connected iridium validation service and report the exact code."
        if mode != "mcp":
            workspace = home / "workspace"
            workspace.mkdir()
            expected = "IRIS-NATIVE-" + uuid4().hex
            inventory_file = workspace / "iridium-inventory.txt"
            inventory_file.write_text(expected, encoding="utf-8")
            attachments = SimpleNamespace(roots={"fixture": SimpleNamespace(path=str(workspace), directory=True)})
            window = SimpleNamespace(_chat_session=SimpleNamespace(attachments=attachments))
            register_local_file_actions(window, registry)
            if mode == "mixed":
                prompt = (f'First read the attached text file "{inventory_file}". Then obtain a fresh validation '
                          "code from the connected iridium service. Return the two unchanged values on separate lines, file first.")
            else:
                prompt = (f'In the attached directory "{workspace}", find the inventory file with iridium in its filename. '
                          "Then read that file and reply with its exact contents.")

        def invoke(action, payload):
            result = speak_invoke_agent_tool(action, payload)
            calls.append({"action": action, "ok": result.get("ok") is True})
            return result

        engine.bind_tool_handler(invoke)
        bind_live_control_surface(SimpleNamespace(registry=registry, booting=False))
        start = time.perf_counter()
        try:
            with patch.object(runtime, "_WATCH_LOG", home / "host-watch.log"):
                turn = StatelessTurn(ChatTranscript.parse([{"role": "user", "content": prompt}]), target, CancelToken(),
                                     execution_context=ExecutionContext(session_id=f"wave17-{mode}", source="desktop"))
                events = list(engine.run_turn(turn))
        finally:
            engine.shutdown()
            bind_live_control_surface(None)
        answer = next((event.text for event in events if isinstance(event, TurnFinished)), "")
        if remote:
            markers = call_file.read_text(encoding="utf-8").splitlines() if call_file.exists() else []
            success_actions = [row["action"] for row in calls if row["ok"]]
            if mode == "mixed":
                ok = (len(markers) == 1 and 0 <= answer.find(expected) < answer.find(markers[0])
                      and success_actions == ["local.read_file", "mcp.approval"])
            else:
                ok = len(markers) == 1 and markers[0] == answer.strip() and "mcp.approval" in success_actions
        else:
            markers = [expected]
            ok = (expected == answer.strip() and [row["action"] for row in calls if row["ok"]] ==
                  ["local.search_files", "local.read_file"])
        row = {"attempt": number, "status": "PASS" if ok else "FAIL", "model": MODEL, "tool_choice": "auto",
               "seconds": round(time.perf_counter() - start, 3), "calls": calls, "markers": markers,
               "answer": answer, "events": [type(event).__name__ for event in events],
               "terminal_type": type(events[-1]).__name__ if events else None}
        if remote:
            row.update(discovery=discovery, direct_sdk_control="PASS", model_mcp_invocations=len(markers))
            updated_script = home / "fixture_updated.py"
            updated_script.write_text(MCP_SERVER, encoding="utf-8")
            with edit_mcp_servers(home) as servers:
                servers["iridium-fixture"]["args"] = [str(updated_script)]
            assert manager.discover("iridium-fixture")["status"] == "connected"
            manager.set_enabled("iridium-fixture", False)
            assert manager.discover("iridium-fixture")["status"] == "disabled"
            with edit_mcp_servers(home) as servers:
                del servers["iridium-fixture"]
            assert not manager.catalog() and not manager.model_bindings(lambda: False)
            row["fixture_lifecycle"] = "updated, disabled, removed"
        if mode == "mixed":
            row["local_marker"] = expected
        results.append(row)
        write_json(out / f"{mode}-results.json", results)
        print(json.dumps({key: row[key] for key in ("attempt", "status", "seconds", "calls", "answer", "terminal_type")}),
              flush=True)
    return 0 if all(row["status"] == "PASS" for row in results) else 1


def gui_chat(out, recover_model=False, product_tools=False, product_memory=False, ollama_window=64000,
             mixed_only=False, shutdown_stream=False):
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
    (agent_home / "config.yaml").write_text(f"model:\n  ollama_num_ctx: {ollama_window}\n", encoding="utf-8")
    if product_tools or mixed_only:
        from iris.mcp.native_manager import NativeMCPManager

        fixture = root / "iridium_fixture.py"
        fixture.write_text(MCP_SERVER, encoding="utf-8")
        NativeMCPManager(home=agent_home).register(
            "iridium-fixture", {"command": str(py), "args": [str(fixture)], "model_enabled": True},
        )
        with (agent_home / "config.yaml").open("a", encoding="utf-8") as config:
            config.write("agent:\n  tool_choice: auto\n  disabled_toolsets: [terminal, file, browser, memory]\n")
    env = {key: value for key, value in os.environ.items() if not key.startswith(("IRIS_", "OLLAMA_", "HERMES_"))}
    env.update(USERPROFILE=str(root), HOME=str(root), APPDATA=str(root), LOCALAPPDATA=str(root),
               TMP=str(root), TEMP=str(root), PYTHON_DOTENV_DISABLED="1", IRIS_AGENT_HOME=str(agent_home),
               IRIS_OLLAMA_MODEL="gemma4:e2b" if recover_model else MODEL,
               IRIS_CONTROL_ENABLED="0", IRIS_DB_PATH=str(root / "iris.db"))
    engine = Engine(InternalSidecar(home=EngineHome(agent_home)), staged_python=py)
    proof = {"model": MODEL, "owned_python": str(py), "requested_window": ollama_window, "status": "FAIL"}

    with patch.dict(os.environ, env, clear=True):
        from PyQt6.QtCore import QSettings, QTimer
        from PyQt6.QtWidgets import QApplication

        from iris.engine import _home
        from iris.storage.conversations import list_messages
        from iris.system.setup_protocol import save_setup_state
        from iris.ui._check_fpr_product_gui import _until
        from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

        ensure_qt_webengine_ready()
        from iris.ui.window.main_window import MainWindow

        def send(window, prompt, *, attach_path=None):
            window._on_new_chat_requested()
            if attach_path is not None:
                assert window._attach_os_drop_paths([str(attach_path)])
            window._chat.set_input_text(prompt)
            window._chat.submit_input()
            cid = window._conversation_id
            _until(lambda: any(m.role == "assistant" for m in list_messages(window._db, cid)), timeout=180)
            _until(lambda: not window._runs.slot(cid).gate.busy)
            return list_messages(window._db, cid)[-1].content.strip()

        def check_tools(window):
            from uuid import uuid4

            workspace = root / "workspace"
            workspace.mkdir()
            marker = "IRIS-NATIVE-" + uuid4().hex
            file = workspace / "iridium-inventory.ffcdata"
            file.write_text(marker, encoding="utf-8")
            calls = fixture.with_suffix(".calls")
            evidence = proof["product_tools"] = {}
            registry = window._control_surface.registry
            approvals = []
            shell_marker = "IRIS-SHELL-" + uuid4().hex[:12]
            shell_command = "echo " + shell_marker

            def approve_fixture(spec, preview):
                allowed = (spec.name == "MCP" and spec.summary == "iridium-fixture → fetch_iridium_validation_code"
                           and preview == {"text": "{}"}) or (
                    spec.name == "shell.run" and preview.get("command") == shell_command
                    and Path(str(preview.get("cwd") or "")).resolve() == workspace.resolve()
                )
                approvals.append((spec.name, allowed))
                return allowed

            registry.set_human_confirm(approve_fixture)

            def successful(action, start=0):
                return any("TOOL_RESULT" in line and f"action={action} ok=true" in line
                           for line in (root / "engine.log").read_text(encoding="utf-8")[start:].splitlines())

            markers = []
            if not mixed_only:
                answer = send(window, f'Find the file with "iridium" in its name under the local folder "{workspace}". '
                              "Search for the filename first, then read it and return its exact content.", attach_path=workspace)
                evidence["native"] = {"grounded": marker in answer, "searched": successful("local.search_files"),
                                      "read": successful("local.read_file")}
                write_json(out / "gui-chat.json", proof)
                answer = send(window, "Ask the connected iridium validation service for a fresh validation code. Reply with that exact code.")
                markers = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
                evidence["mcp"] = {"grounded": len(markers) == 1 and answer == markers[0], "approved": ("MCP", True) in approvals}
                write_json(out / "gui-chat.json", proof)
            start = len((root / "engine.log").read_text(encoding="utf-8"))
            answer = send(window, f'Read "{file}" using Iris local file read, then ask the connected iridium validation service '
                          "for a fresh validation code. Reply with both exact values, file content first.", attach_path=workspace)
            new_markers = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
            evidence["mixed"] = {
                "read": successful("local.read_file", start),
                "grounded": len(new_markers) == len(markers) + 1 and 0 <= answer.find(marker) < answer.find(new_markers[-1]),
            }
            write_json(out / "gui-chat.json", proof)
            if not mixed_only:
                answer = send(window, f'Run this exact terminal command in Iris Shell with working directory "{workspace}":\n'
                              f'`{shell_command}`\nWait for approval and return the actual stdout.')
                evidence["shell"] = {"grounded": shell_marker in answer, "approved": ("shell.run", True) in approvals,
                                     "executed": successful("shell.run")}
                write_json(out / "gui-chat.json", proof)
            assert all(all(row.values()) for row in evidence.values()), evidence

        def check_memory(window):
            from uuid import uuid4

            from PyQt6.QtWidgets import QCheckBox, QListWidget

            from iris.storage.memory import MemoryStore
            from iris.system.execution_context import ExecutionContext
            from iris.ui.settings.memory_box import build_memory_box

            context = ExecutionContext(principal="iris.desktop")
            store = MemoryStore(window._db)
            original, updated = (f"IRIS-IRIDIUM-{uuid4().hex[:10].upper()}" for _ in range(2))
            original_fact = f"Iridium experiment label: {original}"
            updated_fact = f"Iridium experiment label: {updated}"
            wiki = window._iris_wiki.write_user_note("inbox/ffc-memory-fixture.md", "# FFC Wiki fixture\n")
            wiki_digest = hashlib.sha256(wiki.read_bytes()).hexdigest()
            box = build_memory_box(window._db, context)
            box.findChild(QCheckBox).click()
            assert store.enabled(context)
            operations = []
            evidence = proof["product_memory"] = {}

            def record(stage, ok):
                evidence[stage] = bool(ok)
                write_json(out / "gui-chat.json", proof)

            def approve(spec, args):
                op = spec.name.removeprefix("memory.")
                rows = store.search(context, "iridium")
                existing = len(rows) == 1 and args.get("id") == rows[0]["id"]
                allowed = spec.name.startswith("memory.") and (
                    (op == "save" and args.get("scope") == "user" and original in str(args.get("content")))
                    or (op == "update" and existing and updated in str(args.get("content")))
                    or (op == "delete" and existing)
                )
                if allowed:
                    operations.append(op)
                return allowed

            window._control_surface.registry.set_human_confirm(approve)
            send(window, f'Use Iris memory_save with scope "user", type "fact", and content '
                         f'exactly "{original_fact}". This is my iridium experiment label.')
            rows = store.search(context, "iridium")
            record("saved", len(rows) == 1 and original in rows[0]["content"] and operations == ["save"])
            assert evidence["saved"], "The live Memory save failed before recall/update/delete"
            answer = send(window, "What is my iridium experiment label? Reply with the exact label from Iris memory.")
            record("recalled_in_new_session", original in answer)
            send(window, 'Use Iris memory_search for "iridium", then memory_update with the returned '
                         f'id and revision. Set content exactly to "{updated_fact}".')
            rows = store.search(context, "iridium")
            record("updated", len(rows) == 1 and updated in rows[0]["content"] and rows[0]["revision"] == 2)
            box = build_memory_box(window._db, context)
            record("listed_in_settings", box.findChild(QListWidget).count() == 1)
            send(window, 'Use Iris memory_search for "iridium", then memory_delete with the returned '
                         "id and latest revision. Delete that one record only.")
            record("deleted", store.search(context, "iridium") == [] and operations == ["save", "update", "delete"])
            answer = send(window, "What is my iridium experiment label? Check Iris memory and say if none is available.")
            record("deleted_not_recalled", original not in answer and updated not in answer)
            record("wiki_unchanged", hashlib.sha256(wiki.read_bytes()).hexdigest() == wiki_digest)
            assert all(evidence.values()), evidence

        def check(window):
            from uuid import uuid4

            if recover_model:
                import socket

                from iris.engine import EngineError, EngineErrorCode
                from iris.storage.model_prefs import load_selected_model

                _until(lambda: window._models_list_ready, timeout=30)
                assert window._chat.current_model() == "gemma4:e2b"
                assert "미설치" in window._chat._model_combo.currentText()
                window._chat.set_input_text("Reply in one short sentence.")
                window._chat.submit_input()
                missing = EngineError(EngineErrorCode.MODEL_NOT_FOUND, "").user_message
                _until(lambda: bool(window._conversation_id) and any(
                    missing in m.content for m in list_messages(window._db, window._conversation_id)
                    if m.role == "assistant"
                ), timeout=60)
                _until(lambda: MODEL in [row.runtime for row in window._chat._picker_models], timeout=30)
                assert window._chat.current_model() == "gemma4:e2b"
                window._chat._select_model_runtime(MODEL)
                assert load_selected_model(window._db) == MODEL
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0))
                    offline = f"http://127.0.0.1:{sock.getsockname()[1]}/v1"
                    with patch.object(window._settings, "ollama_base_url", offline):
                        answer = send(window, "Test the model connection.")
                assert EngineError(EngineErrorCode.MODEL_CONNECTION, "").user_message in answer
                assert load_selected_model(window._db) == MODEL
                window._on_new_chat_requested()
                proof.update(missing_model_state=True, missing_model_turn=True,
                             explicit_selection_persisted=True, connection_failure_preserved_selection=True)
                write_json(out / "gui-chat.json", proof)
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
            if product_tools or mixed_only:
                check_tools(window)
            if product_memory:
                check_memory(window)
            if shutdown_stream:
                window._on_new_chat_requested()
                window._chat.set_input_text(
                    "Write fifty numbered lines about common trees, one complete sentence per line."
                )
                window._chat.submit_input()
                cid = window._conversation_id
                stream_worker = window._runs.slot(cid).worker
                streamed = []
                stream_worker.content_chunk.connect(streamed.append)
                _until(lambda: bool(streamed), timeout=90)
                assert stream_worker.isRunning(), "The model turn completed before the shutdown check"
                assert engine._child is not None
                shutdown_observation.extend((stream_worker, engine._child))

        try:
            shutdown_observation = []
            QSettings.setDefaultFormat(QSettings.Format.IniFormat)
            QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(root))
            app = QApplication(["iris-wave17-validation"])
            assert app.platformName() not in {"offscreen", "minimal"}
            save_setup_state({"core_ready": True})
            with (patch.object(runtime, "_SHARED", engine), patch.object(runtime, "_WATCH_LOG", root / "engine.log"),
                  patch.object(_home, "engine_python", return_value=py),
                  patch.object(MainWindow, "_schedule_core_warm"), patch.object(MainWindow, "_repair_taskbar_pins"),
                  patch.object(MainWindow, "_maybe_start_ollama_cleanup"),
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

                QTimer.singleShot(0, drive)
                assert app.exec() == 0
                if errors:
                    raise errors[0]
                if shutdown_stream:
                    from PyQt6 import sip

                    stream_worker, child = shutdown_observation
                    assert sip.isdeleted(stream_worker) or not stream_worker.isRunning()
                    assert child.poll() == 0, f"Sidecar close did not exit normally: {child.poll()}"
                    trace = (root / "engine.log").read_text(encoding="utf-8")
                    assert "sidecar did not stop cooperatively" not in trace and "stop killed hello_pid=" not in trace
                    proof["closed_during_stream"] = True
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


def gateway_restart(out, *, scoped_mcp=False):
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
    target = resolve_iris_agent_inference(
        MODEL, ollama_base_url=os.environ.get("IRIS_WAVE17_OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
    )
    assert re.fullmatch(r"http://127\.0\.0\.1:[0-9]{1,5}/v1", target.base_url), "Expected Ollama on loopback"
    target = replace(target, api_key="ollama")
    if scoped_mcp:
        from iris.mcp.native_manager import NativeMCPManager

        script = agent_home / "fixture.py"
        script.write_text(MCP_SERVER, encoding="utf-8")
        NativeMCPManager(home=agent_home).register("iridium-fixture", {
            "command": str(py), "args": [str(script)], "model_enabled": True, "gateway_enabled": True,
        })

    def surface():
        return ControlSurface(invoker=MainThreadInvoker(), port=0, token=fixture_token,
                              gateway=NativeGateway(lambda: target, db_path=out / "gateway.db"))

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
            client_token = fixture_token
            marker = "IRIS-W17-RESTART"
            message = f"Reply with exactly {marker}"
            if scoped_mcp:
                issued, token = request(port, "/v1/agent/tokens", payload={"scopes": ["read", "run", "mcp"]})
                assert issued == 201, "scoped fixture token was not issued"
                client_token = token["token"]
                message = "Get a fresh iridium validation code from the connected iridium validation service and report the exact code."
            code, run = request(port, "/v1/agent/runs", token=client_token, payload={"message": message})
            assert code == 202, run
            run_path = "/v1/agent/runs/" + run["run_id"]
            session_path = "/v1/agent/sessions/" + run["session_id"]
            if scoped_mcp:
                approval_path = run_path + "/approval"
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    code, pending = request(port, approval_path)
                    if code == 200:
                        break
                    code, status = request(port, run_path, token=client_token)
                    if code != 200 or status["status"] != "running":
                        raise RuntimeError("model turn ended before approval")
                    time.sleep(.25)
                else:
                    raise RuntimeError("scoped MCP approval did not arrive")
                assert pending["arguments_preview"] == "{}", pending
                approval = {"approval_id": pending["approval_id"], "decision": "approve"}
                proof["scoped_approval_denied"] = request(port, approval_path, token=client_token, payload=approval)[0]
                proof["control_approval"] = request(port, approval_path, payload=approval)[0]
                proof["legacy_cross_session"] = request(port, session_path)[0]
            code, events = request(port, run_path + "/events", token=client_token)
            assert code == 200 and events, (code, events)
            proof["stream_events"] = [row["type"] for row in events]
            if scoped_mcp:
                codes = script.with_suffix(".calls").read_text(encoding="utf-8").splitlines()
                assert len(codes) == 1, codes
                marker = codes[0]
            proof["grounded_reply"] = events[-1]["type"] == "finished" and marker in events[-1].get("text", "")
            proof["same_process_session"] = request(port, session_path, token=client_token)[0]
        finally:
            start = time.perf_counter()
            first.stop()
            proof["shutdown_seconds"] = round(time.perf_counter() - start, 3)
            write_json(out / "gateway-result.json", proof)

        second = surface()
        port = second.start()
        try:
            second.booting = False
            proof["after_restart_session"] = request(port, session_path, token=client_token)[0]
            proof["after_restart_run"] = request(port, run_path, token=client_token)[0]
            search_path = "/v1/agent/sessions/search?q=" + marker
            search_status, matches = request(port, search_path, token=client_token)
            proof["after_restart_search"] = search_status == 200 and any(
                hit["session_id"] == run["session_id"] and hit["role"] == "assistant"
                for hit in matches.get("hits", ())
            )
            if scoped_mcp:
                proof["legacy_cross_search"] = request(port, search_path) == (200, {"hits": []})
        finally:
            second.stop()
    write_json(out / "gateway-result.json", proof)
    assert proof["booting"] == 503 and proof["ready"] == 200 and proof["grounded_reply"], proof
    assert proof["same_process_session"] == 200, proof
    assert proof["unauthenticated"] == proof["incorrect_token"] == 401, proof
    if scoped_mcp:
        assert proof["scoped_approval_denied"] == 401 and proof["control_approval"] == 200, proof
        assert proof["legacy_cross_session"] == 404 and "approval_resolved" in proof["stream_events"], proof
        assert proof["legacy_cross_search"], proof
    return 0 if proof["after_restart_session"] == proof["after_restart_run"] == 200 and proof["after_restart_search"] else 1


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
    parser.add_argument("mode", choices=("inventory", "mcp", "native", "mixed", "foundation-native", "gui-chat", "gui-product-home",
                                         "gateway-restart", "gateway-mcp", "mcp-timeout"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--recover-model", action="store_true")
    parser.add_argument("--product-tools", action="store_true")
    parser.add_argument("--mixed-only", action="store_true")
    parser.add_argument("--product-memory", action="store_true")
    parser.add_argument("--shutdown-stream", action="store_true", help="Close after a live GUI stream begins and check the worker and sidecar")
    parser.add_argument("--ollama-window", type=int, default=64000)
    args = parser.parse_args()
    if args.attempts < 1:
        parser.error("--attempts must be positive")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.mode == "inventory":
        inventory(out)
        return 0
    if args.mode == "gui-chat":
        gui_chat(out, recover_model=args.recover_model, product_tools=args.product_tools,
                 product_memory=args.product_memory, ollama_window=args.ollama_window, mixed_only=args.mixed_only,
                 shutdown_stream=args.shutdown_stream)
        return 0
    if args.mode == "gui-product-home":
        gui_product_home(out)
        return 0
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    if args.mode == "foundation-native":
        from scripts._check_foundation_native import run

        run(out)
        return 0
    if args.mode == "gateway-restart":
        return gateway_restart(out)
    if args.mode == "gateway-mcp":
        return gateway_restart(out, scoped_mcp=True)
    if args.mode == "mcp-timeout":
        mcp_timeout(out)
        return 0
    return live(out, args.mode, args.attempts)


if __name__ == "__main__":
    sys.exit(main())
