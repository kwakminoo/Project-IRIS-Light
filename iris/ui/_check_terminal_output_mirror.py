"""U08 — Runtime stdout/stderr → Theia appendTerminalOutput mirror contract."""

from __future__ import annotations

from pathlib import Path


def main() -> None:
    from iris.system.iris_ide_runtime import runtime_install_dir, runtime_source_dir
    from iris.system.terminal_output_mirror import (
        advance_output_cursor,
        format_run_banner,
        merge_stderr_into_mirror,
    )

    # Pure cursor math
    assert "rid-1" in format_run_banner("rid-1")
    t, n = advance_output_cursor({"text": "ab", "offset": 0}, offset=0)
    assert t == "ab" and n == 2
    t2, n2 = advance_output_cursor({"text": "cd", "offset": 2}, offset=2)
    assert t2 == "cd" and n2 == 4
    assert merge_stderr_into_mirror("out\n", "err") == "out\nerr"

    root = Path(__file__).resolve().parents[1]
    project = (root / "ui" / "control_actions" / "project.py").read_text(encoding="utf-8")
    assert "append_terminal_output" in project
    assert "echo IRIS_RUN_ID=" not in project, "echo-only IRIS_RUN_ID viz must be removed"
    assert "format_run_banner" in project
    assert "advance_output_cursor" in project
    assert "bridge fail" in project.lower() or "Bridge fail" in project or "≠ process" in project

    client = (root / "infrastructure" / "iris_ide_client.py").read_text(encoding="utf-8")
    assert "def append_terminal_output" in client
    assert "appendTerminalOutput" in client
    assert "run_id" in client

    poller = (runtime_source_dir() / "src/browser/iris-ide-bridge-poller.ts").read_text(
        encoding="utf-8"
    )
    assert "appendTerminalOutput" in poller
    assert "anyTerm.write" in poller or "write === 'function'" in poller
    assert "revealed: true" in poller
    # HF-08: mirror must not call sendText (shell-input risk).
    mirror_fn = poller.split(
        "protected async appendTerminalOutput(args"
    )[1].split("protected async runInTerminal(args")[0]
    assert "sendText(" not in mirror_fn, "appendTerminalOutput must not fall back to sendText("
    assert "terminal_write_missing" in mirror_fn
    assert "theia_terminal_write" in mirror_fn

    protocol = (runtime_source_dir() / "src/common/iris-ide-protocol.ts").read_text(
        encoding="utf-8"
    )
    assert "'appendTerminalOutput'" in protocol

    bridge = (runtime_source_dir() / "bridge/standalone-bridge.js").read_text(encoding="utf-8")
    assert "case 'appendTerminalOutput'" in bridge
    assert "enqueueFrontend" in bridge and "appendTerminalOutput" in bridge

    backend = (
        runtime_source_dir() / "src/node/iris-ide-bridge-server.ts"
    ).read_text(encoding="utf-8")
    assert "appendTerminalOutput" in backend

    bundle = runtime_install_dir() / "lib/frontend/bundle.js"
    assert bundle.is_file(), "install bundle missing — sync_workspace_build first"
    text = bundle.read_text(encoding="utf-8", errors="ignore")
    assert "appendTerminalOutput" in text, "bundle missing appendTerminalOutput — rebuild"

    print("terminal_output_mirror check ok")


if __name__ == "__main__":
    main()
