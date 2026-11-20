"""P1: app.present_html SpeakTools + ephemeral App Host materialization.

Run: .venv\\Scripts\\python.exe -m iris.ui.chat._check_app_present_html
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from iris.engine.app_ui import MAX_APP_UI_BYTES
from iris.engine.types import IRIS_ENGINE_TOOLS, assert_iris_engine_tools_catalog
from iris.infrastructure.agent_tool_registry import speak_invoke_agent_tool
from iris.infrastructure.tool_capability import (
    PHASE4_ALLOWLIST,
    ExecKind,
    assert_engine_tools_match_allowlist,
)
from iris.system.control_surface import ActionRegistry
from iris.ui.control_bindings import _register_actions

_CALC_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>calc</title></head>
<body>
<button id="a">1</button><button id="b">+</button><button id="c">1</button>
<script>
document.getElementById('a').onclick=()=>{};
</script>
</body></html>
"""


def _surface() -> tuple[MagicMock, ActionRegistry]:
    window = MagicMock()
    window._control_qt_invoker = None
    window._chat = MagicMock()
    window._chat.show_app_host.return_value = True
    window._chat.present_chat_app_offer = None
    window._get_bound_ide_session.return_value = None
    surface = MagicMock()
    surface.registry = ActionRegistry()
    surface.booting = False
    _register_actions(window, surface)
    surface.registry.set_human_confirm(lambda spec, args: True)
    return window, surface.registry


def main() -> None:
    grant = PHASE4_ALLOWLIST.grant("app.present_html")
    assert grant is not None
    assert grant.kind is ExecKind.SURFACE
    assert grant.parameters is not None
    assert "html" in grant.parameters.get("required", [])
    assert "app.present_html" in IRIS_ENGINE_TOOLS
    assert_engine_tools_match_allowlist()
    assert_iris_engine_tools_catalog()

    window, reg = _surface()
    names = {row["name"] for row in reg.catalog()}
    assert "app.present_html" in names

    out = reg.invoke(
        "app.present_html",
        {"title": "Mini Calc", "html": _CALC_HTML},
    )
    assert out["ok"] is True, out
    result = out["result"]
    assert result.get("ok") is True
    assert result.get("shown") is True
    assert result.get("kind") == "ephemeral"
    assert result.get("title") == "Mini Calc"
    offer_id = str(result.get("offer_id") or "")
    assert offer_id, result
    html_path = Path(str(result.get("html_path") or ""))
    assert html_path.is_file(), html_path
    assert result["_meta"]["ui"]["resourceUri"] == str(html_path)
    window._chat.show_app_host.assert_called_once()
    call_args = window._chat.show_app_host.call_args
    assert Path(call_args.args[0]).resolve() == html_path.resolve()
    assert call_args.kwargs.get("title") == "Mini Calc" or (
        len(call_args.args) > 1 and call_args.args[1] == "Mini Calc"
    )

    empty = reg.invoke("app.present_html", {"html": ""})
    assert empty.get("ok") is False, empty

    oversized = reg.invoke(
        "app.present_html",
        {"html": "x" * (MAX_APP_UI_BYTES + 1)},
    )
    assert oversized.get("ok") is False, oversized

    spoken = speak_invoke_agent_tool("app.present_html", {"html": _CALC_HTML})
    assert spoken.get("ok") is False
    assert spoken.get("error") == "requires_iris_ui"

    print("app.present_html ok")


if __name__ == "__main__":
    main()
