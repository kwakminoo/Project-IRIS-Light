"""Phase 4b: App Directory registry (list / search / install persist).

Run: .venv\\Scripts\\python.exe -m iris.apps._check_app_directory
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from iris.apps.directory import AppDirectory, AppDirectoryEntry
from iris.engine.types import IRIS_ENGINE_TOOLS, assert_iris_engine_tools_catalog
from iris.infrastructure.agent_tool_registry import speak_invoke_agent_tool
from iris.infrastructure.speak_capability import (
    PHASE4_ALLOWLIST,
    ExecKind,
    assert_engine_tools_match_allowlist,
)
from iris.system.control_surface import ActionRegistry
from iris.ui.control_bindings import _register_actions

_DEMO_ID = "demo-ping"
_DEMO_RESOURCE = "app_host_ping.html"


def _surface() -> ActionRegistry:
    window = MagicMock()
    window._control_qt_invoker = None
    window._chat = MagicMock()
    window._get_bound_ide_session.return_value = None
    surface = MagicMock()
    surface.registry = ActionRegistry()
    surface.booting = False
    _register_actions(window, surface)
    surface.registry.set_human_confirm(lambda spec, args: True)
    return surface.registry


def _assert_registry(store: Path) -> None:
    first = AppDirectory(path=store)
    rows = first.list()
    demo = next((r for r in rows if r.id == _DEMO_ID), None)
    assert demo is not None, f"builtin demo missing: {[r.id for r in rows]}"
    assert demo.source == "builtin"
    assert demo.resource_uri == _DEMO_RESOURCE
    assert demo.title.strip()

    found = first.search("ping")
    assert any(r.id == _DEMO_ID for r in found), [r.id for r in found]
    assert first.get(_DEMO_ID) is not None

    custom = AppDirectoryEntry(
        id="custom-note",
        title="Custom Note App",
        summary="Installed for directory check",
        resource_uri="custom_note.html",
        source="installed",
    )
    saved = first.install(custom)
    assert saved.id == "custom-note"
    assert saved.source == "installed"
    assert store.is_file(), "install must persist to directory.json"

    second = AppDirectory(path=store)
    assert second.get("custom-note") is not None
    assert any(r.id == "custom-note" for r in second.list())
    assert second.get(_DEMO_ID) is not None

    assert second.uninstall("custom-note") is True
    assert second.get("custom-note") is None
    assert second.uninstall(_DEMO_ID) is False
    assert second.get(_DEMO_ID) is not None

    third = AppDirectory(path=store)
    assert third.get("custom-note") is None
    assert third.get(_DEMO_ID) is not None


def _assert_control() -> None:
    grant = PHASE4_ALLOWLIST.grant("app.directory_list")
    assert grant is not None
    assert grant.kind is ExecKind.PURE
    assert "app.directory_list" in IRIS_ENGINE_TOOLS
    assert_engine_tools_match_allowlist()
    assert_iris_engine_tools_catalog()

    reg = _surface()
    names = {row["name"] for row in reg.catalog()}
    assert "app.directory_list" in names

    listed = reg.invoke("app.directory_list", {})
    assert listed["ok"] is True, listed
    apps = listed["result"]["apps"]
    assert any(a.get("id") == _DEMO_ID for a in apps), apps

    searched = reg.invoke("app.directory_list", {"query": "ping"})
    assert searched["ok"] is True, searched
    hit = searched["result"]["apps"]
    assert any(a.get("id") == _DEMO_ID for a in hit), hit

    spoken = speak_invoke_agent_tool("app.directory_list", {})
    assert spoken.get("ok") is True, spoken
    spoken_data = spoken.get("data") if isinstance(spoken.get("data"), dict) else {}
    spoken_apps = spoken_data.get("apps")
    assert isinstance(spoken_apps, list), spoken
    assert any(a.get("id") == _DEMO_ID for a in spoken_apps), spoken_apps


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "directory.json"
        _assert_registry(store)
    _assert_control()
    print("app directory ok")


if __name__ == "__main__":
    main()
