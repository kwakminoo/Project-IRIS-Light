"""Live IRIS IDE runtime start/stop when installed."""

from __future__ import annotations

import tempfile
import time

from iris.system.iris_ide_runtime import IrisIdeRuntimeManager


def main() -> None:
    mgr = IrisIdeRuntimeManager()
    ok, msg = mgr.verify_installation()
    if not ok:
        print("iris_ide_live skip:", msg)
        return
    with tempfile.TemporaryDirectory(prefix="iris-ide-live-") as tmp:
        ok, err = mgr.start(tmp)
        assert ok, err
        assert mgr.health(), "health failed"
        from iris.infrastructure.iris_ide_client import IrisIdeClient

        client = IrisIdeClient(base_url=mgr.bridge_base_url(), token=mgr.bridge_token())
        ws = client.get_workspace()
        assert ws.get("root")
        client.create_file("probe.txt", content="iris\n")
        client.open_file("probe.txt")
        ed = client.get_active_editor()
        assert ed.get("editor")
        term = client.run_terminal_command("echo IRIS_IDE_LIVE")
        assert "IRIS_IDE_LIVE" in str(term.get("output", ""))
        mgr.stop()
        time.sleep(0.5)
        assert not mgr.health()
    print("iris_ide_live check ok")


if __name__ == "__main__":
    main()
