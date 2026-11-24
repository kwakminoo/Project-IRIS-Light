"""Absorbed Hermes toolsets overlay: terminal/browser/file/web emptied."""

from __future__ import annotations

import tempfile
from pathlib import Path

_ABSORBED_NAMES = frozenset(
    {
        "terminal",
        "process_manage",
        "write_file",
        "read_file",
        "patch",
        "search_files",
        "web_search",
        "web_extract",
    }
)

_FIXTURE = '''\
_HERMES_CORE_TOOLS = [
    "web_search", "web_extract",
    "terminal", "process_manage",
    "read_file", "write_file", "patch", "search_files",
    "browser_exec", "browser_cdp",
    "vision_analyze",
]

def _ts(description, tools=(), includes=(), **extra):
    return {"description": description, "tools": list(tools), "includes": list(includes), **extra}

CLIENT_SURFACE_TOOLSETS = frozenset({"project", "desktop_ui", "catalog"})

TOOLSETS = {
    "web": _ts("Web research", ["web_search", "web_extract"]),
    "search": _ts("Web search only", ["web_search"]),
    "file": _ts("File tools", ["read_file", "write_file", "patch", "search_files"]),
    "terminal": _ts("Terminal", ["terminal", "process_manage"]),
    "browser": _ts("Browser", ["browser_exec", "browser_cdp"]),
    "debugging": _ts("Debug", ["terminal", "process_manage"], includes=["web"]),
}
'''

_STALE_OVERLAY = '''\
# iris: absorbed-toolsets — stale narrow set
IRIS_ABSORBED_TOOLSETS = frozenset({"terminal", "browser"})
_IRIS_ABSORBED_TOOL_NAMES = frozenset({"terminal", "process_manage"})


def _iris_strip_absorbed_tools(tools):
    out = []
    for t in tools or ():
        name = str(t)
        if name in _IRIS_ABSORBED_TOOL_NAMES or name.startswith("browser_"):
            continue
        out.append(t)
    return out


for _iris_ts_name in IRIS_ABSORBED_TOOLSETS:
    _iris_entry = TOOLSETS.get(_iris_ts_name)
    if isinstance(_iris_entry, dict):
        _iris_entry["tools"] = []
for _iris_entry in TOOLSETS.values():
    if isinstance(_iris_entry, dict) and "tools" in _iris_entry:
        _iris_entry["tools"] = _iris_strip_absorbed_tools(_iris_entry.get("tools"))
try:
    _HERMES_CORE_TOOLS[:] = _iris_strip_absorbed_tools(_HERMES_CORE_TOOLS)
except NameError:
    pass
# iris: absorbed-toolsets end
'''


def _assert_core_lacks_absorbed(core: list) -> None:
    for name in _ABSORBED_NAMES:
        assert name not in core, (name, core)
    for name in core:
        assert not str(name).startswith("browser_"), name


def main() -> None:
    from iris.system.iris_agent_absorbed_toolsets import (
        IRIS_ABSORBED_TOOLSETS,
        absorbed_toolsets_overlay_present,
        apply_absorbed_toolsets_overlay,
        load_toolsets_namespace,
    )

    assert IRIS_ABSORBED_TOOLSETS == frozenset({"terminal", "browser", "file", "web"})
    assert "file" in IRIS_ABSORBED_TOOLSETS and "web" in IRIS_ABSORBED_TOOLSETS

    with tempfile.TemporaryDirectory(prefix="iris-absorbed-ts-") as tmp:
        root = Path(tmp)
        (root / "toolsets.py").write_text(_FIXTURE, encoding="utf-8")
        assert not absorbed_toolsets_overlay_present(root)
        msgs = apply_absorbed_toolsets_overlay(root)
        assert any("applied" in m for m in msgs), msgs
        assert absorbed_toolsets_overlay_present(root)
        # idempotent when snippet unchanged
        msgs2 = apply_absorbed_toolsets_overlay(root)
        assert any("present" in m for m in msgs2), msgs2

        ns = load_toolsets_namespace(root)
        toolsets = ns["TOOLSETS"]
        core = ns["_HERMES_CORE_TOOLS"]
        for bucket in ("terminal", "browser", "file", "web"):
            assert toolsets[bucket]["tools"] == [], (bucket, toolsets[bucket])
        assert toolsets["search"]["tools"] == [], toolsets["search"]
        assert "terminal" not in toolsets["debugging"]["tools"]
        assert "process_manage" not in toolsets["debugging"]["tools"]
        _assert_core_lacks_absorbed(core)
        assert core == [], core  # Iris-only: Hermes CORE emptied
        absorbed = ns["IRIS_ABSORBED_TOOLSETS"]
        assert absorbed == IRIS_ABSORBED_TOOLSETS
        names = ns["_IRIS_ABSORBED_TOOL_NAMES"]
        assert _ABSORBED_NAMES <= names

    # Re-apply refreshes stale marker block when snippet expanded
    with tempfile.TemporaryDirectory(prefix="iris-absorbed-ts-refresh-") as tmp:
        root = Path(tmp)
        path = root / "toolsets.py"
        path.write_text(_FIXTURE + "\n" + _STALE_OVERLAY, encoding="utf-8")
        assert absorbed_toolsets_overlay_present(root)
        before = path.read_text(encoding="utf-8")
        assert 'frozenset({"terminal", "browser"})' in before
        assert "_IRIS_ABSORBED_TOOL_NAMES = frozenset({\"terminal\", \"process_manage\"})" in before
        msgs = apply_absorbed_toolsets_overlay(root)
        assert any("refreshed" in m for m in msgs), msgs
        after = path.read_text(encoding="utf-8")
        assert after.count("iris: absorbed-toolsets") == 2  # start + end
        ns = load_toolsets_namespace(root)
        assert ns["IRIS_ABSORBED_TOOLSETS"] == IRIS_ABSORBED_TOOLSETS
        assert _ABSORBED_NAMES <= ns["_IRIS_ABSORBED_TOOL_NAMES"]
        _assert_core_lacks_absorbed(ns["_HERMES_CORE_TOOLS"])
        assert ns["TOOLSETS"]["web"]["tools"] == []
        assert ns["TOOLSETS"]["file"]["tools"] == []
        # second refresh with identical snippet → present
        msgs3 = apply_absorbed_toolsets_overlay(root)
        assert any("present" in m for m in msgs3), msgs3

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
