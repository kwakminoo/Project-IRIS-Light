"""Absorbed Hermes toolsets overlay: terminal/browser empty; web kept."""

from __future__ import annotations

import tempfile
from pathlib import Path

_FIXTURE = '''\
_HERMES_CORE_TOOLS = [
    "web_search", "web_extract",
    "terminal", "process_manage",
    "browser_exec", "browser_cdp",
]

def _ts(description, tools=(), includes=(), **extra):
    return {"description": description, "tools": list(tools), "includes": list(includes), **extra}

CLIENT_SURFACE_TOOLSETS = frozenset({"project", "desktop_ui", "catalog"})

TOOLSETS = {
    "web": _ts("Web research", ["web_search", "web_extract"]),
    "terminal": _ts("Terminal", ["terminal", "process_manage"]),
    "browser": _ts("Browser", ["browser_exec", "browser_cdp"]),
    "debugging": _ts("Debug", ["terminal", "process_manage"], includes=["web"]),
}
'''


def main() -> None:
    from iris.system.iris_agent_absorbed_toolsets import (
        IRIS_ABSORBED_TOOLSETS,
        absorbed_toolsets_overlay_present,
        apply_absorbed_toolsets_overlay,
        load_toolsets_namespace,
    )

    assert IRIS_ABSORBED_TOOLSETS == frozenset({"terminal", "browser"})
    assert "web" not in IRIS_ABSORBED_TOOLSETS

    with tempfile.TemporaryDirectory(prefix="iris-absorbed-ts-") as tmp:
        root = Path(tmp)
        (root / "toolsets.py").write_text(_FIXTURE, encoding="utf-8")
        assert not absorbed_toolsets_overlay_present(root)
        msgs = apply_absorbed_toolsets_overlay(root)
        assert any("applied" in m for m in msgs), msgs
        assert absorbed_toolsets_overlay_present(root)
        # idempotent
        msgs2 = apply_absorbed_toolsets_overlay(root)
        assert any("present" in m for m in msgs2), msgs2

        ns = load_toolsets_namespace(root)
        toolsets = ns["TOOLSETS"]
        core = ns["_HERMES_CORE_TOOLS"]
        assert toolsets["terminal"]["tools"] == [], toolsets["terminal"]
        assert toolsets["browser"]["tools"] == [], toolsets["browser"]
        assert "web_search" in toolsets["web"]["tools"]
        assert "web_extract" in toolsets["web"]["tools"]
        assert "terminal" not in toolsets["debugging"]["tools"]
        assert "process_manage" not in toolsets["debugging"]["tools"]
        assert "terminal" not in core and "process_manage" not in core
        assert "browser_exec" not in core and "browser_cdp" not in core
        assert "web_search" in core

    with tempfile.TemporaryDirectory(prefix="iris-absorbed-ts-invalid-") as tmp:
        root = Path(tmp)
        path = root / "toolsets.py"
        path.write_text(_FIXTURE + "invalid syntax !", encoding="utf-8")
        before = path.read_text(encoding="utf-8")
        msgs = apply_absorbed_toolsets_overlay(root)
        assert any("syntax check fail" in m for m in msgs), msgs
        assert path.read_text(encoding="utf-8") == before

    print("iris_agent_absorbed_toolsets check ok", sorted(IRIS_ABSORBED_TOOLSETS))


if __name__ == "__main__":
    main()
