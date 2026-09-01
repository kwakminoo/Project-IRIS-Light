"""Live IRIS IDE bridge integration (standalone Node process)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from iris.infrastructure.iris_ide_client import IrisIdeClient
from iris.system.iris_ide_runtime import runtime_source_dir, runtime_state_path
from iris.system.node_runtime import node_executable


def main() -> None:
    bridge_js = runtime_source_dir() / "bridge" / "standalone-bridge.js"
    assert bridge_js.is_file(), bridge_js
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
        env["IRIS_IDE_STATE_FILE"] = str(state)
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
                if state.is_file():
                    import json

                    data = json.loads(state.read_text(encoding="utf-8"))
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
            client.open_file("hello.py")
            ed = client.get_active_editor()
            assert "hello.py" in str(ed.get("editor", {}).get("path", ""))
            client.replace_selection("# iris\n", path="hello.py")
            assert "# iris" in hello.read_text(encoding="utf-8")
            term = client.run_terminal_command("echo IRIS_IDE_TEST")
            assert "IRIS_IDE_TEST" in str(term.get("output", ""))
            diag = client.get_diagnostics()
            assert isinstance(diag.get("diagnostics"), list)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            if backup is None:
                try:
                    state.unlink(missing_ok=True)  # type: ignore[call-arg]
                except TypeError:
                    if state.is_file():
                        state.unlink()
            elif backup is not None:
                state.write_text(backup, encoding="utf-8")

    print("iris_ide_bridge check ok")


if __name__ == "__main__":
    main()
