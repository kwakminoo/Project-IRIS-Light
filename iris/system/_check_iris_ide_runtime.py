"""IRIS IDE runtime unit checks."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from iris.system.iris_ide_runtime import (
    IrisIdeRuntimeManager,
    is_iris_ide_demo,
    runtime_install_dir,
    runtime_source_dir,
)
from iris.system.node_runtime import is_node_ready
from iris.system.setup_protocol import OPTIONAL_IDS


def check_bridge_recovery(*, in_source: bool = False) -> None:
    from iris.system import iris_ide_runtime as runtime

    with TemporaryDirectory() as temp:
        root = Path(temp)
        for name in ("bridge/standalone-bridge.js", "node_modules/@theia/cli/bin/theia.js"):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        processes = [Mock(pid=i, poll=Mock(return_value=None)) for i in range(100, 104)]
        mgr = IrisIdeRuntimeManager()
        with (
            patch.object(runtime, "iris_state_dir", return_value=root),
            patch.object(runtime, "runtime_install_dir", return_value=root),
            patch.object(runtime, "runtime_source_dir", return_value=root if in_source else root / "unused"),
            patch.object(runtime, "_free_port", side_effect=range(8000, 8004)),
            patch.object(runtime.subprocess, "Popen", side_effect=processes) as launch,
            patch.object(runtime.subprocess, "run"),
            patch.object(runtime.os, "kill"),
            patch.object(mgr, "verify_installation", return_value=(True, "ok")),
            patch.object(mgr, "health", return_value=True),
        ):
            try:
                assert mgr.start(temp)[0]
                first_url, first_token = mgr.bridge_base_url(), mgr.bridge_token()
                assert mgr.start(temp)[0] and launch.call_count == 2
                processes[0].poll.return_value = 1
                assert mgr.start(temp)[0] and launch.call_count == 4
                assert mgr.bridge_base_url() != first_url and mgr.bridge_token() != first_token
            finally:
                mgr.stop()
            assert not mgr.bridge_base_url() and not mgr.bridge_token()
            assert not runtime.runtime_state_path().exists()


def check_launch_failure_signal() -> None:
    from iris.ui.workers.boot_checks_worker import IrisIdeLaunchWorker

    worker = IrisIdeLaunchWorker()
    errors = []
    worker.finished_err.connect(errors.append)
    manager = Mock()
    manager.start.side_effect = PermissionError("bridge locked")
    with patch("iris.system.iris_ide_runtime.shared_iris_ide_runtime", return_value=manager):
        worker.run()
    assert len(errors) == 1 and "bridge locked" in errors[0], errors


def main() -> None:
    check_launch_failure_signal()
    check_bridge_recovery()
    check_bridge_recovery(in_source=True)
    assert "iris_ide" in OPTIONAL_IDS
    assert runtime_source_dir().joinpath("package.json").is_file()
    mgr = IrisIdeRuntimeManager()
    st = mgr.status()
    assert isinstance(st.installed, bool)
    ok_node, _ = is_node_ready()
    assert isinstance(ok_node, bool)
    demo = is_iris_ide_demo()
    os.environ["IRIS_IDE_DEMO"] = "1"
    assert IrisIdeRuntimeManager().is_installed()
    os.environ.pop("IRIS_IDE_DEMO", None)
    print("iris_ide_runtime check ok", runtime_install_dir(), "demo_was", demo)


if __name__ == "__main__":
    main()
