"""Iris-bench style — Speak surface can reach control actions headless.

No live cloud model. Asserts engine names, SpeakTools / IrisAgentChatWorker
invoke shapes, and iris-skills SKILL.md teaching language.

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_iris_agent_surface_bench
"""

from __future__ import annotations

from pathlib import Path

from iris.engine.model_tool_names import catalog_uses_model_tool_names
from iris.infrastructure.tool_capability import default_agent_tools
from iris.system.iris_agent_control_sync import project_root
from iris.ui.workers.iris_agent_workers import IrisAgentChatWorker

_REQUIRED = ("get_state", "get_catalog", "control.invoke")
_FORBIDDEN = ("iris_invoke", "iris_get_state", "iris_get_catalog")
_STRUCTURED_CTRL_ERRORS = frozenset(
    {
        "requires_iris_ui",
        "missing action",
    }
)


def _tool_names(rows: object) -> set[str]:
    out: set[str] = set()
    if not isinstance(rows, list):
        return out
    for row in rows:
        if isinstance(row, str) and row.strip():
            out.add(row.strip())
        elif isinstance(row, dict):
            name = str(row.get("name") or "").strip()
            if name:
                out.add(name)
    return out


def _assert_engine_names() -> None:
    names = default_agent_tools().engine_names()
    for need in _REQUIRED:
        assert need in names, f"engine_names missing {need}: {names!r}"
    for bad in _FORBIDDEN:
        assert bad not in names, f"engine_names still lists {bad}"


def _assert_get_catalog_shape(data: dict) -> None:
    assert "tools" in data, f"get_catalog missing tools: {sorted(data)}"
    assert "control_actions" in data, (
        f"get_catalog missing control_actions: {sorted(data)}"
    )
    tool_names = _tool_names(data.get("tools"))
    # Familiar fold: control.invoke stays on engine_names/PHASE4, not model catalog.
    if catalog_uses_model_tool_names():
        assert "control.invoke" not in tool_names, (
            "familiar active: control.invoke must leave get_catalog.tools"
        )
    else:
        assert "control.invoke" in tool_names, (
            "get_catalog.tools must list control.invoke when "
            f"familiar fold off; got {sorted(tool_names)[:12]!r}…"
        )
    cas = data.get("control_actions")
    assert isinstance(cas, list), f"control_actions must be list, got {type(cas)}"


def _assert_speak_invoke_headless() -> None:
    tools = default_agent_tools()

    ping = tools.invoke("ping", {})
    assert ping.ok is True, ping
    assert isinstance(ping.data, dict)
    assert ping.data.get("alive") is True

    cat = tools.invoke("get_catalog", {})
    assert cat.ok is True, cat
    assert isinstance(cat.data, dict)
    _assert_get_catalog_shape(cat.data)

    missing = tools.invoke("control.invoke", {})
    assert missing.ok is False
    assert missing.error == "missing action"
    assert isinstance(missing.data, dict)

    # Headless: Control bridge has no MainWindow → structured requires_iris_ui.
    bridged = tools.invoke(
        "control.invoke", {"action": "ping", "args": {}}
    )
    assert bridged.ok is False, bridged
    err = bridged.error or ""
    assert err == "requires_iris_ui" or err.startswith("not_allowed"), (
        f"control.invoke headless must be structured, got {bridged!r}"
    )
    assert isinstance(bridged.data, dict)
    assert bridged.call_path == "native"


def _assert_worker_invoke_headless() -> None:
    ping = IrisAgentChatWorker.invoke_native_tool("ping", {})
    assert ping.get("ok") is True, ping
    assert ping.get("call_path") == "native"
    data = ping.get("data") or {}
    assert isinstance(data, dict)
    assert data.get("alive") is True

    cat = IrisAgentChatWorker.invoke_native_tool("get_catalog", {})
    assert cat.get("ok") is True, cat
    payload = cat.get("data") or {}
    assert isinstance(payload, dict)
    _assert_get_catalog_shape(payload)

    ctrl = IrisAgentChatWorker.invoke_native_tool(
        "control.invoke", {"action": "ping", "args": {}}
    )
    assert isinstance(ctrl, dict), ctrl
    assert ctrl.get("ok") is False
    err = str(ctrl.get("error") or "")
    assert err == "requires_iris_ui" or err.startswith("not_allowed") or (
        err in _STRUCTURED_CTRL_ERRORS
    ), f"worker control.invoke not structured: {ctrl!r}"
    assert ctrl.get("call_path") == "native"
    assert isinstance(ctrl.get("data"), dict)


def _assert_skills_language(repo: Path) -> None:
    skills = repo / "integrations" / "iris-skills"
    assert skills.is_dir(), skills
    paths = sorted(skills.rglob("SKILL.md"))
    assert paths, f"no SKILL.md under {skills}"

    forbidden_hits: list[str] = []
    speak_hits = 0
    control_hits = 0
    for path in paths:
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(repo).as_posix()
        for bad in _FORBIDDEN:
            if bad in text:
                forbidden_hits.append(f"{rel}:{bad}")
        if "SpeakTools" in text:
            speak_hits += 1
        if "control.invoke" in text:
            control_hits += 1

    assert not forbidden_hits, (
        "SKILL.md still teaches obsolete MCP tool names:\n"
        + "\n".join(forbidden_hits)
    )
    assert speak_hits >= 1, "no SKILL.md mentions SpeakTools"
    assert control_hits >= 1, "no SKILL.md mentions control.invoke"


def _main() -> None:
    repo = project_root()
    _assert_engine_names()
    _assert_speak_invoke_headless()
    _assert_worker_invoke_headless()
    _assert_skills_language(repo)
    print("iris_agent_surface_bench ok")


if __name__ == "__main__":
    _main()
