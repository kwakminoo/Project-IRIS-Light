"""Phase 3: app.demo_ping SpeakTools + App Host meta.

Run: .venv\\Scripts\\python.exe -m iris.ui.chat._check_app_demo_ping
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from iris.engine.app_ui import app_ui_from_tool_meta, emit_app_ui_payload
from iris.engine.types import IRIS_ENGINE_TOOLS, assert_iris_engine_tools_catalog
from iris.infrastructure.agent_tool_registry import speak_invoke_agent_tool
from iris.infrastructure.speak_capability import (
    PHASE4_ALLOWLIST,
    ExecKind,
    assert_engine_tools_match_allowlist,
)
from iris.system.control_surface import ActionRegistry
from iris.ui.control_bindings import _register_actions

_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "app_host_ping.html"
)
_RESOURCE = "app_host_ping.html"


def _surface() -> tuple[MagicMock, ActionRegistry]:
    window = MagicMock()
    window._control_qt_invoker = None
    window._chat = MagicMock()
    window._chat.show_app_host.return_value = True
    window._get_bound_ide_session.return_value = None
    surface = MagicMock()
    surface.registry = ActionRegistry()
    surface.booting = False
    _register_actions(window, surface)
    surface.registry.set_human_confirm(lambda spec, args: True)
    return window, surface.registry


def main() -> None:
    assert _FIXTURE.is_file(), f"missing fixture {_FIXTURE}"

    grant = PHASE4_ALLOWLIST.grant("app.demo_ping")
    assert grant is not None
    assert grant.kind is ExecKind.SURFACE
    assert "app.demo_ping" in IRIS_ENGINE_TOOLS
    assert_engine_tools_match_allowlist()
    assert_iris_engine_tools_catalog()

    tool_shape = {
        "ok": True,
        "_meta": {"ui": {"resourceUri": _RESOURCE}},
    }
    offer = app_ui_from_tool_meta(tool_shape, default_title="데모 앱")
    assert offer is not None
    assert Path(offer.html_path).resolve() == _FIXTURE.resolve()
    assert offer.title == "데모 앱"

    control_shape = {
        "ok": True,
        "result": {
            "ok": True,
            "shown": True,
            "_meta": {"ui": {"resourceUri": _RESOURCE}},
        },
    }
    payload = emit_app_ui_payload(control_shape, default_title="데모 앱")
    assert payload is not None
    assert payload["t"] == "app_ui"
    assert payload["title"] == "데모 앱"
    assert Path(payload["html_path"]).resolve() == _FIXTURE.resolve()
    assert payload["resource_uri"] == _RESOURCE
    assert emit_app_ui_payload(None) is None
    assert emit_app_ui_payload({"ok": True}) is None

    window, reg = _surface()
    names = {row["name"] for row in reg.catalog()}
    assert "app.demo_ping" in names

    out = reg.invoke("app.demo_ping", {})
    assert out["ok"] is True, out
    result = out["result"]
    assert result.get("ok") is True
    assert result.get("shown") is True
    assert result["_meta"]["ui"]["resourceUri"] == _RESOURCE
    assert Path(result["html_path"]).resolve() == _FIXTURE.resolve()
    window._chat.show_app_host.assert_called_once()
    call_args = window._chat.show_app_host.call_args
    assert Path(call_args.args[0]).resolve() == _FIXTURE.resolve()
    assert call_args.kwargs.get("title") == "데모 앱" or (
        len(call_args.args) > 1 and call_args.args[1] == "데모 앱"
    )

    spoken = speak_invoke_agent_tool("app.demo_ping", {})
    assert spoken.get("ok") is False
    assert spoken.get("error") == "requires_iris_ui"

    print("app.demo_ping ok")


if __name__ == "__main__":
    main()
