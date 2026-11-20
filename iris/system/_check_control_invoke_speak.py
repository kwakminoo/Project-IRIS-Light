"""Unit — SpeakTools control.invoke bridge + get_catalog control_actions.

Fails until PHASE4_ALLOWLIST includes control.invoke and SpeakTools.invoke
dispatches inner action via surface.invoke. get_catalog must project live
ActionRegistry rows as control_actions when an actions view is bound.
"""

from __future__ import annotations

from pathlib import Path

from iris.infrastructure.tool_capability import (
    PHASE4_ALLOWLIST,
    ExecKind,
    ToolAllowlist,
    ToolGrant,
    SpeakTools,
    ToolResult,
    default_agent_tools,
)


_ROOT = Path(__file__).resolve().parents[2]
_FORBIDDEN_TOOL_NAMES = ("iris_get_state", "iris_get_catalog", "iris_invoke")


class _FakeActions:
    def spec(self, name: str):
        return None

    def catalog(self) -> list[dict]:
        return [
            {
                "name": "browser.search",
                "summary": "Search the web",
                "risk": "low",
                "confirm_required": False,
            },
            {
                "name": "emulator.launch",
                "summary": "Launch emulator",
                "risk": "medium",
                "confirm_required": False,
            },
        ]


class _RecordingSurface:
    def __init__(self, reply: dict | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.reply = reply

    def invoke(self, action: str, args: dict) -> dict | None:
        self.calls.append((action, dict(args)))
        return self.reply


def _assert_product_teaching_scrubbed() -> None:
    roots = [
        _ROOT / "iris" / "ui" / "window" / "main_window.py",
        _ROOT / "iris" / "ui" / "chat" / "skill_mcp_dialogs.py",
        _ROOT / "iris" / "infrastructure" / "email_client.py",
        _ROOT / "iris" / "infrastructure" / "calendar_agent.py",
        _ROOT / "iris" / "system" / "setup_protocol.py",
    ]
    for path in roots:
        text = path.read_text(encoding="utf-8")
        for bad in _FORBIDDEN_TOOL_NAMES:
            assert bad not in text, f"{path.relative_to(_ROOT)} still teaches {bad}"

    skills_root = _ROOT / "integrations" / "iris-skills"
    assert skills_root.is_dir(), skills_root
    hits: list[str] = []
    for path in skills_root.rglob("*"):
        if path.suffix.lower() not in {".md", ".txt", ".json"}:
            continue
        text = path.read_text(encoding="utf-8")
        for bad in _FORBIDDEN_TOOL_NAMES:
            if bad in text:
                hits.append(f"{path.relative_to(_ROOT)}:{bad}")
        if "mcp__iris_control__" in text:
            hits.append(f"{path.relative_to(_ROOT)}:mcp__iris_control__")
    assert not hits, "iris-skills still teach obsolete MCP names:\n" + "\n".join(hits)


def _main() -> None:
    assert "control.invoke" in PHASE4_ALLOWLIST.names()
    grant = PHASE4_ALLOWLIST.grant("control.invoke")
    assert grant is not None
    assert grant.kind in (ExecKind.PURE, ExecKind.SURFACE)
    assert grant.parameters is not None
    assert "action" in (grant.parameters.get("properties") or {})

    surface = _RecordingSurface(
        {"ok": True, "action": "browser.search", "result": {"query": "q"}}
    )
    tools = SpeakTools(
        PHASE4_ALLOWLIST,
        surface=surface,
        actions=_FakeActions(),
        pure_handlers={
            "ping": lambda _a: ToolResult(
                ok=True, action="ping", data={"alive": True, "bridge": "none"}
            ),
        },
    )

    missing = tools.invoke("control.invoke", {})
    assert missing.ok is False
    assert "action" in (missing.error or "").lower() or missing.error

    out = tools.invoke(
        "control.invoke",
        {"action": "browser.search", "args": {"query": "iris"}},
    )
    assert out.ok is True, out
    assert out.call_path == "native"
    assert surface.calls == [("browser.search", {"query": "iris"})], surface.calls

    no_ui = SpeakTools(
        ToolAllowlist(
            grants=(ToolGrant("control.invoke", ExecKind.SURFACE, "bridge"),)
        ),
        surface=_RecordingSurface(None),
        actions=_FakeActions(),
    )
    blocked = no_ui.invoke(
        "control.invoke", {"action": "emulator.launch", "args": {}}
    )
    assert blocked.ok is False
    assert blocked.error == "requires_iris_ui"

    cat = tools.invoke("get_catalog", {})
    assert cat.ok is True, cat
    assert "tools" in cat.data
    assert "control_actions" in cat.data, cat.data.keys()
    names = {row["name"] for row in cat.data["control_actions"]}
    assert "browser.search" in names
    assert "emulator.launch" in names

    live = default_agent_tools()
    assert "control.invoke" in live.engine_names()
    assert "get_state" in live.engine_names()
    assert "get_catalog" in live.engine_names()
    for bad in _FORBIDDEN_TOOL_NAMES:
        assert bad not in live.engine_names()

    _assert_product_teaching_scrubbed()

    print(
        "control_invoke_speak ok",
        f"grants={len(PHASE4_ALLOWLIST.names())}",
        f"control_actions={len(cat.data['control_actions'])}",
    )


if __name__ == "__main__":
    _main()
