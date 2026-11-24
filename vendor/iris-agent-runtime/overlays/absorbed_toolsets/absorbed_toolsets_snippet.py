# iris: absorbed-toolsets — terminal/browser/file/web owned by Iris SpeakTools
# (project.run / shell.run / engine iris tools / web.run_*). Do not delete this block.
IRIS_ABSORBED_TOOLSETS = frozenset({"terminal", "browser", "file", "web"})
_IRIS_ABSORBED_TOOL_NAMES = frozenset(
    {
        "terminal",
        "process_manage",
        "write_file",
        "read_file",
        "patch",
        "search_files",
        "web_search",
        "web_extract",
        # Remaining Hermes CORE — Iris SpeakTools only for the model.
        "vision_analyze",
        "image_generate",
        "skills_list",
        "skill_view",
        "skill_manage",
        "text_to_speech",
        "todo_list",
        "memory",
        "session_search",
        "clarify",
        "execute_code",
        "delegate_task",
        "cronjob_manage",
        "computer_use",
        "manage_connections",
    }
)


def _iris_strip_absorbed_tools(tools):
    out = []
    for t in tools or ():
        name = str(t)
        if (
            name in _IRIS_ABSORBED_TOOL_NAMES
            or name.startswith("browser_")
            or name.startswith("kanban_")
        ):
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
    # Product path: model must not see any Hermes CORE leftover.
    _HERMES_CORE_TOOLS[:] = []
except NameError:
    pass
# iris: absorbed-toolsets end
