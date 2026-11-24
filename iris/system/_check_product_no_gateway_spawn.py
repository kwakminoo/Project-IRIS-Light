"""Unit 2 — Product callers must not spawn/restart :8642 Hermes gateway."""

from __future__ import annotations

import inspect
from pathlib import Path

from iris.ui.workers import extension_install_worker as eiw
from iris.ui.workers import iris_agent_workers as hw


_ROOT = Path(__file__).resolve().parents[2]
_FORBIDDEN = (
    "restart_hermes_gateway",
    "ensure_iris_agent_gateway_running",
    "start_hermes_gateway",
)

# Product surfaces that must stay disk/engine-only.
_PRODUCT_FILES = (
    _ROOT / "iris" / "ui" / "workers" / "iris_agent_workers.py",
    _ROOT / "iris" / "ui" / "workers" / "extension_install_worker.py",
    _ROOT / "iris" / "system" / "iris_agent_update.py",
    _ROOT / "iris" / "ui" / "control_actions" / "agent_turn.py",
)


def _assert_no_forbidden(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for name in _FORBIDDEN:
        assert name not in text, f"{path.name} still references {name}"


def _check_product_files_scraped() -> None:
    for path in _PRODUCT_FILES:
        assert path.is_file(), path
        _assert_no_forbidden(path)


def _check_control_sync_worker_run() -> None:
    src = inspect.getsource(hw.IrisAgentControlSyncWorker.run)
    for name in _FORBIDDEN:
        assert name not in src, f"ControlSyncWorker.run calls {name}"
    assert "sync_iris_control" in src
    assert "verify_iris_mcp_tools" not in src


def _check_extension_reload_no_gateway() -> None:
    src = inspect.getsource(eiw.ExtensionInstallWorker)
    for name in _FORBIDDEN:
        assert name not in src
    assert "ensure_ready" in src or "reload_runtime" in src


def main() -> None:
    _check_product_files_scraped()
    _check_control_sync_worker_run()
    _check_extension_reload_no_gateway()
    print("product_no_gateway_spawn ok")


if __name__ == "__main__":
    main()
