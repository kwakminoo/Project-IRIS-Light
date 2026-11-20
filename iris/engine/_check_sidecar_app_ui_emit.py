"""Sidecar tool.completed with _meta.ui emits t=app_ui.

Run: .venv\\Scripts\\python.exe -m iris.engine._check_sidecar_app_ui_emit
"""

from __future__ import annotations

import json
from pathlib import Path

from iris.engine import _sidecar_main as sidecar
from iris.engine.app_ui import emit_app_ui_payload

_FIXTURE = (
    Path(__file__).resolve().parents[1] / "ui" / "chat" / "fixtures" / "app_host_ping.html"
)
_META = {"_meta": {"ui": {"resourceUri": "app_host_ping.html"}}}


def _with_emit(emitted: list[dict]):
    original = sidecar._emit
    sidecar._emit = emitted.append
    return original


def main() -> None:
    assert _FIXTURE.is_file(), f"missing fixture {_FIXTURE}"
    expected = emit_app_ui_payload(_META, default_title="app.demo_ping")
    assert expected is not None
    assert expected["t"] == "app_ui"
    assert Path(expected["html_path"]).resolve() == _FIXTURE.resolve()

    emitted: list[dict] = []
    original = _with_emit(emitted)
    try:
        sidecar._on_tool(
            "tool.completed",
            "app.demo_ping",
            None,
            None,
            result=_META,
        )
    finally:
        sidecar._emit = original

    assert emitted[0] == {
        "t": "tool",
        "label": "[IRIS tool use: app.demo_ping]",
    }
    app_uis = [row for row in emitted if row.get("t") == "app_ui"]
    assert len(app_uis) == 1, emitted
    assert app_uis[0] == expected

    emitted.clear()
    original = _with_emit(emitted)
    try:
        sidecar._on_tool(
            "tool.completed",
            "app.demo_ping",
            None,
            None,
            result={"ok": True, "result": _META},
        )
    finally:
        sidecar._emit = original
    assert any(row.get("t") == "tool" for row in emitted)
    assert any(row.get("t") == "app_ui" for row in emitted), emitted

    emitted.clear()
    original = _with_emit(emitted)
    try:
        sidecar._on_tool(
            "tool.completed",
            "mcp_demo",
            None,
            None,
            result=json.dumps(_META),
        )
    finally:
        sidecar._emit = original
    assert any(row.get("t") == "app_ui" for row in emitted), emitted

    emitted.clear()
    original = _with_emit(emitted)
    try:
        sidecar._on_tool(
            "tool.completed",
            "bad_remote",
            None,
            None,
            result={"_meta": {"ui": {"resourceUri": "https://example.com/x.html"}}},
        )
        sidecar._on_tool(
            "tool.completed",
            "no_meta",
            None,
            None,
            result={"ok": True},
        )
        sidecar._on_tool(
            "tool.started",
            "app.demo_ping",
            None,
            None,
            result=_META,
        )
    finally:
        sidecar._emit = original
    assert all(row.get("t") != "app_ui" for row in emitted), emitted
    assert any(
        row.get("t") == "tool" and "bad_remote" in str(row.get("label"))
        for row in emitted
    )

    print("sidecar app_ui emit ok")


if __name__ == "__main__":
    main()
