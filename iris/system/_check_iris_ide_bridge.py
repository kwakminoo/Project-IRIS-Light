"""Live IRIS IDE bridge integration (standalone Node process) — honesty contracts."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from iris.infrastructure.iris_ide_client import IrisIdeClient, IrisIdeClientError
from iris.system.iris_ide_runtime import runtime_source_dir, runtime_state_path
from iris.system.node_runtime import node_executable


def main() -> None:
    bridge_js = runtime_source_dir() / "bridge" / "standalone-bridge.js"
    assert bridge_js.is_file(), bridge_js
    # Source contract: no disk-only save disguise, no selection disk-append soft path, no Theia in poll errors.
    src = bridge_js.read_text(encoding="utf-8")
    assert "via: 'disk', editor: false" not in src and 'via: "disk", editor: false' not in src
    assert "saved: true, via: 'disk'" not in src and 'saved: true, via: "disk"' not in src
    assert "buffer edit requires via=editor" in src
    assert "is IRIS IDE Theia loaded?" not in src
    assert "is IRIS IDE loaded?" in src

    node = node_executable()
    assert node, "node not found"

    with tempfile.TemporaryDirectory(prefix="iris-ide-bridge-") as tmp:
        ws = Path(tmp)
        hello = ws / "hello.py"
        hello.write_text("print('hi')\n", encoding="utf-8")
        state = runtime_state_path()
        if state.is_file():
            backup = state.read_text(encoding="utf-8")
        else:
            backup = None
        env = os.environ.copy()
        env["IRIS_IDE_WORKSPACE"] = str(ws)
        env["IRIS_IDE_BRIDGE_TOKEN"] = "test-bridge-token"
        env["IRIS_IDE_BRIDGE_PORT"] = "0"
        test_state = state.parent / "iris_ide_bridge_test_state.json"
        env["IRIS_IDE_STATE_FILE"] = str(test_state)
        kwargs: dict = {
            "cwd": str(runtime_source_dir()),
            "env": env,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        proc = subprocess.Popen([node, str(bridge_js)], **kwargs)  # noqa: S603
        try:
            port = 0
            for _ in range(40):
                if proc.poll() is not None:
                    out = proc.stdout.read() if proc.stdout else ""
                    raise AssertionError(f"bridge exited early: {out}")
                if test_state.is_file():
                    import json

                    data = json.loads(test_state.read_text(encoding="utf-8"))
                    port = int(data.get("bridge_port") or 0)
                    if port:
                        break
                time.sleep(0.15)
            assert port, "bridge port not written to state"

            client = IrisIdeClient(base_url=f"http://127.0.0.1:{port}", token="test-bridge-token")
            h = client.health()
            assert h.get("product") == "IRIS IDE"
            ws_info = client.get_workspace()
            assert Path(ws_info["root"]).resolve() == ws.resolve()

            # Without frontend poller: open / save must hard-fail (no soft success).
            try:
                client.open_file("hello.py")
                raise AssertionError("openFile without frontend returned success")
            except IrisIdeClientError as exc:
                msg = str(exc).lower()
                assert "frontend" in msg or "poll" in msg, exc
                assert "theia" not in msg, exc

            try:
                client.save_file("hello.py")
                raise AssertionError("saveFile without frontend returned success")
            except IrisIdeClientError as exc:
                msg = str(exc).lower()
                assert "frontend" in msg or "poll" in msg or "save" in msg, exc

            try:
                client.save_all()
                raise AssertionError("saveAll without frontend returned success")
            except IrisIdeClientError as exc:
                assert "frontend" in str(exc).lower() or "poll" in str(exc).lower(), exc

            # Buffer edit without frontend must hard-fail (no disk-append disguise).
            before = hello.read_text(encoding="utf-8")
            try:
                client.replace_selection("# iris\n", path="hello.py")
                raise AssertionError("replaceSelection without frontend returned success")
            except IrisIdeClientError as exc:
                msg = str(exc).lower()
                assert "frontend" in msg or "poll" in msg or "editor" in msg or "buffer" in msg, exc
            assert hello.read_text(encoding="utf-8") == before
            assert "# iris" not in before

            try:
                client.run_terminal_command("echo IRIS_IDE_TEST")
                raise AssertionError("terminal without frontend returned success")
            except IrisIdeClientError as exc:
                assert "frontend" in str(exc).lower(), exc

            diag = client.get_diagnostics()
            assert diag.get("reported") is False and diag.get("diagnostics") is None, diag
            pushed = client.set_diagnostics([])
            assert pushed.get("reported") is True
            clean = client.get_diagnostics()
            assert clean.get("reported") is True and clean.get("diagnostics") == []

            try:
                client.start_debug({"name": "Python"})
                raise AssertionError("debug without frontend returned success")
            except IrisIdeClientError as exc:
                assert "hooked" not in str(exc).lower()
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            try:
                test_state.unlink(missing_ok=True)  # type: ignore[call-arg]
            except TypeError:
                if test_state.is_file():
                    test_state.unlink()
            if backup is None:
                try:
                    state.unlink(missing_ok=True)  # type: ignore[call-arg]
                except TypeError:
                    if state.is_file():
                        state.unlink()
            elif backup is not None:
                state.write_text(backup, encoding="utf-8")

    # Embedded Theia bridge server must not claim opened:true without poller.
    server_ts = runtime_source_dir() / "src" / "node" / "iris-ide-bridge-server.ts"
    assert server_ts.is_file(), server_ts
    server_src = server_ts.read_text(encoding="utf-8")
    assert "return { path: abs, opened: true };" not in server_src
    assert "standalone-bridge frontend queue (IRIS IDE editor)" in server_src

    print("iris_ide_bridge check ok")


if __name__ == "__main__":
    main()
