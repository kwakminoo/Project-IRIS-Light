# iris: absorbed-toolsets — terminal/browser owned by Iris SpeakTools
# (project.run / shell.run / engine iris tools). Do not delete this block.
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
