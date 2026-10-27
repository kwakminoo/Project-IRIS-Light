"""project.run / runTerminalCommand 회귀 — dual-bridge skip + poller markers."""

from __future__ import annotations

from pathlib import Path


def main() -> None:
    from iris.system.iris_ide_runtime import (
        runtime_install_dir,
        runtime_source_dir,
        shared_iris_ide_runtime,
    )

    src = (runtime_source_dir() / "src/node/iris-ide-backend-contribution.ts").read_text(
        encoding="utf-8"
    )
    assert "IRIS_IDE_STANDALONE_BRIDGE" in src, "backend must skip when standalone bridge owns port"

    runtime = (Path(__file__).resolve().parents[1] / "system" / "iris_ide_runtime.py").read_text(
        encoding="utf-8"
    )
    assert 'IRIS_IDE_STANDALONE_BRIDGE' in runtime and '"1"' in runtime

    poller = (runtime_source_dir() / "src/browser/iris-ide-bridge-poller.ts").read_text(
        encoding="utf-8"
    )
    assert "ensureTerminal" in poller
    assert "currentTerminal" in poller and "lastUsedTerminal" in poller, "터미널 재사용 경로 소실"
    assert "via: 'theia_terminal'" in poller or 'via: "theia_terminal"' in poller
    assert "bridge_fallback" not in poller, "via=bridge_fallback 터미널 성공 재도입 금지"
    assert "withTimeout" in poller
    assert "pollBusy" in poller

    bridge = (runtime_source_dir() / "bridge/standalone-bridge.js").read_text(encoding="utf-8")
    assert "lastFrontendPollAt" in bridge
    assert "no frontend poll yet" in bridge

    bundle = runtime_install_dir() / "lib/frontend/bundle.js"
    assert bundle.is_file(), "install bundle missing — sync_workspace_build first"
    text = bundle.read_text(encoding="utf-8", errors="ignore")
    assert "pollPendingCommands" in text
    assert "runTerminalCommand" in text

    # install backend contribution compiled
    lib = runtime_install_dir() / "lib/node/iris-ide-backend-contribution.js"
    if lib.is_file():
        assert "IRIS_IDE_STANDALONE_BRIDGE" in lib.read_text(encoding="utf-8", errors="ignore")

    mgr = shared_iris_ide_runtime()
    assert hasattr(mgr, "workspace_open")
    print("project_run_terminal check ok")


if __name__ == "__main__":
    main()
