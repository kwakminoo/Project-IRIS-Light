"""Unit 5/6/7 — public ``iris.agent`` façade (≤10 exports) + primary call-site names.

Logic lives in ``iris_agent_*``; ``hermes_*`` files are thin re-export shims.
Product hot paths must use Iris Agent names and must not import
``hermes_workers`` / HermesChatWorker.

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_iris_agent_facade
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN_WINDOW = ROOT / "iris" / "ui" / "window" / "main_window.py"
SETTINGS_DIALOG = ROOT / "iris" / "ui" / "settings" / "settings_dialog.py"

# Product surface ceiling (Unit 6: +Control/Model sync; hard max 10).
_MAX_EXPORTS = 10
_REQUIRED = frozenset(
    {
        "home",
        "iris_agent_home",
        "ensure_runtime",
        "ensure_iris_agent_runtime",
        "IrisAgentHealthWorker",
        "IrisAgentChatWorker",
        "IrisAgentControlSyncWorker",
        "IrisAgentModelSyncWorker",
        "speak_invoke",
        "pin_sha",
    }
)

# Hot product paths that must not import hermes_workers / Hermes* chat-health names.
_HOT_PATH_FILES = (
    ROOT / "iris" / "ui" / "window" / "main_window.py",
    ROOT / "iris" / "ui" / "settings" / "settings_dialog.py",
    ROOT / "iris" / "system" / "setup_protocol.py",
    ROOT / "iris" / "iris_agent_login_warm_cli.py",
    ROOT / "iris" / "__main__.py",
    ROOT / "iris" / "ui" / "window" / "setup_wizard.py",
)
_HOT_PATH_DIRS = (
    ROOT / "iris" / "ui" / "control_actions",
    ROOT / "iris" / "ui" / "ai_hub",
)

_BANNED_IMPORT = re.compile(
    r"from\s+iris\.ui\.workers\.hermes_workers\b|import\s+iris\.ui\.workers\.hermes_workers\b"
)
_BANNED_WORKER = re.compile(r"\bHermesChatWorker\b|\bHermesHealthWorker\b")


def _iter_hot_path_py() -> list[Path]:
    out: list[Path] = []
    for path in _HOT_PATH_FILES:
        if path.is_file():
            out.append(path)
    for folder in _HOT_PATH_DIRS:
        if not folder.is_dir():
            continue
        for path in folder.rglob("*.py"):
            if path.name.startswith("_check_"):
                continue
            out.append(path)
    return out


def _check_export_surface() -> None:
    agent = importlib.import_module("iris.agent")
    exported = list(getattr(agent, "__all__", ()))
    assert len(exported) <= _MAX_EXPORTS, exported
    assert set(exported) == _REQUIRED, (set(exported), _REQUIRED)
    for name in _REQUIRED:
        assert hasattr(agent, name), name


def _check_aliases_are_thin() -> None:
    import iris.agent as agent
    from iris.infrastructure import agent_runtime as ar
    from iris.infrastructure.agent_tool_registry import speak_invoke_agent_tool
    from iris.ui.workers import iris_agent_workers as hw

    assert agent.iris_agent_home is ar.iris_agent_home
    assert agent.home is ar.iris_agent_home
    assert agent.ensure_iris_agent_runtime is ar.ensure_iris_agent_runtime
    assert agent.ensure_runtime is ar.ensure_iris_agent_runtime
    assert agent.pin_sha is ar.load_pinned_sha
    assert agent.speak_invoke is speak_invoke_agent_tool
    assert agent.IrisAgentHealthWorker is hw.HermesHealthWorker
    assert agent.IrisAgentChatWorker is hw.HermesChatWorker
    assert agent.IrisAgentControlSyncWorker is hw.HermesControlSyncWorker
    assert agent.IrisAgentModelSyncWorker is hw.HermesModelSyncWorker
    assert hw.IrisAgentChatWorker is hw.HermesChatWorker
    assert hw.IrisAgentHealthWorker is hw.HermesHealthWorker
    assert hw.IrisAgentControlSyncWorker is hw.HermesControlSyncWorker
    assert hw.IrisAgentModelSyncWorker is hw.HermesModelSyncWorker


def _check_main_window_uses_facade_names() -> None:
    src = MAIN_WINDOW.read_text(encoding="utf-8")
    assert "from iris.agent import" in src
    assert "IrisAgentChatWorker" in src
    assert "IrisAgentHealthWorker" in src
    assert "IrisAgentModelSyncWorker" in src
    assert "worker = IrisAgentHealthWorker(" in src
    assert "worker = IrisAgentChatWorker(" in src
    assert "isinstance(worker, IrisAgentChatWorker)" in src
    assert "HermesChatWorker" not in src
    assert "HermesHealthWorker" not in src
    assert "hermes_workers" not in src


def _check_settings_uses_facade_control_sync() -> None:
    src = SETTINGS_DIALOG.read_text(encoding="utf-8")
    assert "IrisAgentControlSyncWorker" in src
    assert "worker = IrisAgentControlSyncWorker(" in src
    assert "from iris.ui.workers.iris_agent_workers" not in src
    assert "HermesControlSyncWorker" not in src


def _check_hot_paths_no_hermes_workers() -> None:
    for path in _iter_hot_path_py():
        src = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT).as_posix()
        assert not _BANNED_IMPORT.search(src), rel
        assert not _BANNED_WORKER.search(src), rel


def main() -> None:
    _check_export_surface()
    _check_aliases_are_thin()
    _check_main_window_uses_facade_names()
    _check_settings_uses_facade_control_sync()
    _check_hot_paths_no_hermes_workers()
    print("iris_agent_facade: ok")


if __name__ == "__main__":
    main()
