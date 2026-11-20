"""P3: app.open SpeakTools + directory demo-ping.

Run: .venv\\Scripts\\python.exe -m iris.ui.chat._check_app_open
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from iris.apps.directory import AppDirectory
from iris.engine.types import IRIS_ENGINE_TOOLS, assert_iris_engine_tools_catalog
from iris.infrastructure.agent_tool_registry import speak_invoke_agent_tool
from iris.infrastructure.tool_capability import (
    PHASE4_ALLOWLIST,
    ExecKind,
    assert_engine_tools_match_allowlist,
)
from iris.system.control_surface import ActionRegistry
from iris.ui.control_bindings import _register_actions

_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "app_host_ping.html"
)
_APP_ID = "demo-ping"
_RESOURCE = "app_host_ping.html"


def _surface() -> tuple[MagicMock, ActionRegistry]:
    window = MagicMock()
    window._control_qt_invoker = None
    window._chat = MagicMock()
    window._chat._open_directory_app.return_value = True
    window._get_bound_ide_session.return_value = None
    surface = MagicMock()
    surface.registry = ActionRegistry()
    surface.booting = False
    _register_actions(window, surface)
    surface.registry.set_human_confirm(lambda spec, args: True)
    return window, surface.registry


def main() -> None:
    assert _FIXTURE.is_file(), f"missing fixture {_FIXTURE}"
    entry = AppDirectory().get(_APP_ID)
    assert entry is not None
    assert entry.resource_uri == _RESOURCE

    grant = PHASE4_ALLOWLIST.grant("app.open")
    assert grant is not None
    assert grant.kind is ExecKind.SURFACE
    assert grant.parameters is not None
    assert "app_id" in grant.parameters.get("required", [])
    assert "app.open" in IRIS_ENGINE_TOOLS
    assert_engine_tools_match_allowlist()
    assert_iris_engine_tools_catalog()

    window, reg = _surface()
    names = {row["name"] for row in reg.catalog()}
    assert "app.open" in names

    missing = reg.invoke("app.open", {})
    assert missing.get("ok") is False, missing

    unknown = reg.invoke("app.open", {"app_id": "no-such-app"})
    assert unknown.get("ok") is False, unknown

    out = reg.invoke("app.open", {"app_id": _APP_ID})
    assert out["ok"] is True, out
    result = out["result"]
    assert result.get("ok") is True
    assert result.get("shown") is True
    assert result.get("title") == entry.title
    assert result.get("resource_uri") == _RESOURCE
    assert result.get("app_id") == _APP_ID
    window._chat._open_directory_app.assert_called_once()
    called = window._chat._open_directory_app.call_args.args[0]
    assert getattr(called, "id", None) == _APP_ID

    spoken = speak_invoke_agent_tool("app.open", {"app_id": _APP_ID})
    assert spoken.get("ok") is False
    assert spoken.get("error") == "requires_iris_ui"

    print("app.open ok")


if __name__ == "__main__":
    main()
