"""Iris product speak capability — SpeakAllowlist / SpeakTools (Unit2).

One name space: Control action ids. Speak path is always ``call_path=native``.
No MCP stdio / Control HTTP on the product speak path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Literal, Mapping, Protocol

from iris.apps.directory import AppDirectory, entries_as_dicts


class ExecKind(str, Enum):
    """How SpeakTools reaches the ActionRegistry body (or a pure stand-in)."""

    PURE = "pure"
    SURFACE = "surface"


@dataclass(frozen=True)
class SpeakGrant:
    """One agent-callable Control action. Name == ActionRegistry action id."""

    action: str
    kind: ExecKind
    summary: str = ""
    parameters: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class SpeakToolRow:
    """Catalog row derived from SpeakGrant + ActionSpec."""

    name: str
    summary: str
    domain: str
    needs_ui: bool
    confirm_required: bool
    risk: str


@dataclass(frozen=True)
class ToolResult:
    """Domain result. Not HTTP/MCP wire."""

    ok: bool
    action: str
    data: dict[str, Any]
    error: str = ""
    call_path: str = "native"
    bridge: str = "none"

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ok": self.ok,
            "action": self.action,
            "tool": self.action,
            "call_path": self.call_path,
            "bridge": self.bridge,
            "data": self.data,
        }
        if not self.ok:
            out["error"] = self.error
        return out


class ActionCatalogView(Protocol):
    def spec(self, name: str) -> Any | None: ...

    def catalog(self) -> list[dict[str, Any]]: ...


class SurfaceInvoker(Protocol):
    def invoke(self, action: str, args: dict[str, Any]) -> dict[str, Any] | None: ...


PureHandler = Callable[[dict[str, Any]], ToolResult]


# One-release shim: product iris.* seed ids → Control action ids.
_LEGACY_TO_ACTION: dict[str, str] = {
    "iris.tools.ping": "ping",
    "iris.tools.catalog": "get_catalog",
    "iris.session.get_state": "get_state",
    "iris.wiki.list_notes": "wiki.list_notes",
    "iris.wiki.search": "wiki.search",
    "iris.mail.list_accounts": "email.list_accounts",
    "iris.calendar.list_events": "calendar.list_events",
    "iris.ide.open_folder": "ide.open_folder",
    "iris.project.open_similar": "project.open_similar",
}


def resolve_legacy_name(name: str) -> str:
    """Map deprecated iris.* seed ids to Control action names."""
    key = (name or "").strip()
    return _LEGACY_TO_ACTION.get(key, key)


def _domain_of(action: str) -> str:
    if action in ("ping", "get_catalog", "get_state"):
        return "session"
    if "." in action:
        return action.split(".", 1)[0]
    return "session"


@dataclass(frozen=True)
class SpeakAllowlist:
    """Single hand-maintained product list. Catalog/engine names derive from this."""

    grants: tuple[SpeakGrant, ...]

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(g.action for g in self.grants))

    def grant(self, action: str) -> SpeakGrant | None:
        key = (action or "").strip()
        for g in self.grants:
            if g.action == key:
                return g
        return None


PHASE4_ALLOWLIST = SpeakAllowlist(
    grants=(
        SpeakGrant("ping", ExecKind.PURE, "Iris Agent alive check"),
        SpeakGrant("get_catalog", ExecKind.PURE, "List speak/control catalog projection"),
        SpeakGrant("get_state", ExecKind.SURFACE, "Current Iris UI/session state"),
        SpeakGrant("settings.get", ExecKind.SURFACE, "Get Ollama and Iris Agent version"),
        SpeakGrant("wiki.list_notes", ExecKind.PURE, "List Iris Wiki note paths"),
        SpeakGrant("wiki.search", ExecKind.PURE, "Search Iris Wiki notes"),
        SpeakGrant("wiki.write_user_note", ExecKind.SURFACE, "Save markdown into Iris Wiki"),
        SpeakGrant("email.list_accounts", ExecKind.PURE, "List email accounts"),
        SpeakGrant("calendar.list_events", ExecKind.PURE, "List calendar events"),
        SpeakGrant(
            "local.read_file",
            ExecKind.SURFACE,
            "Read one absolute local text file within the configured read scope",
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "max_bytes": {"type": "integer", "minimum": 1, "maximum": 1048576},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        ),
        SpeakGrant(
            "local.search_files",
            ExecKind.SURFACE,
            "Search filenames under one explicit absolute root within the configured read scope",
            {
                "type": "object",
                "properties": {
                    "root": {"type": "string"},
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                },
                "required": ["root", "query"],
                "additionalProperties": False,
            },
        ),
        SpeakGrant("ide.open_folder", ExecKind.SURFACE, "Open a folder in the IDE Companion"),
        SpeakGrant(
            "project.open_similar",
            ExecKind.SURFACE,
            "Find and open a similar project folder",
        ),
        SpeakGrant(
            "attachment.copy_to",
            ExecKind.SURFACE,
            "Copy an attached original to an absolute destination",
            {
                "type": "object",
                "properties": {
                    "attachment_id": {"type": "string"},
                    "destination": {"type": "string"},
                    "overwrite": {"type": "boolean", "default": False},
                },
                "required": ["attachment_id", "destination"],
                "additionalProperties": False,
            },
        ),
        SpeakGrant(
            "attachment.move_to",
            ExecKind.SURFACE,
            "Move an attached original after explicit human confirmation",
            {
                "type": "object",
                "properties": {
                    "attachment_id": {"type": "string"},
                    "destination": {"type": "string"},
                    "overwrite": {"type": "boolean", "default": False},
                },
                "required": ["attachment_id", "destination"],
                "additionalProperties": False,
            },
        ),
        SpeakGrant(
            "project.import_attachment",
            ExecKind.SURFACE,
            "Copy an attached original into the bound IDE workspace",
            {
                "type": "object",
                "properties": {
                    "attachment_id": {"type": "string"},
                    "rel_path": {"type": "string"},
                },
                "required": ["attachment_id", "rel_path"],
                "additionalProperties": False,
            },
        ),
        SpeakGrant("project.run", ExecKind.SURFACE, "Run in the bound IDE terminal"),
        SpeakGrant(
            "shell.run",
            ExecKind.SURFACE,
            "Run a home-surface shell command (no console window; chat Iris Shell card). "
            "Required: command. Optional cwd under user home. Use project.run in IDE Companion.",
            {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "cwd": {"type": "string"},
                    "timeout_s": {"type": "number", "minimum": 1, "maximum": 300},
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        ),
        SpeakGrant(
            "chat.search_past",
            ExecKind.SURFACE,
            "Search prior chat conversations (not wiki notes)",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 3},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        SpeakGrant("chat.new_session", ExecKind.SURFACE, "Start a new chat session"),
        SpeakGrant(
            "app.demo_ping",
            ExecKind.SURFACE,
            "Open the App Host demo (app_host_ping.html)",
        ),
        SpeakGrant(
            "app.directory_list",
            ExecKind.PURE,
            "List or search App Host directory apps",
        ),
        SpeakGrant(
            "note.export_pdf",
            ExecKind.SURFACE,
            "Create a verified PDF from content and/or source files.",
            {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Text to write into the PDF."},
                    "sources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional source file paths to append.",
                    },
                    "path": {
                        "type": "string",
                        "description": "Optional output .pdf path.",
                    },
                },
                "anyOf": [{"required": ["content"]}, {"required": ["sources"]}],
                "additionalProperties": False,
            },
        ),
        SpeakGrant(
            "diagram.render",
            ExecKind.SURFACE,
            "Render typed JSON IR to an interactive diagram in the Iris chat column "
            "(kind=architecture|workflow|sequence|dataflow|lifecycle). "
            "Do not write standalone HTML diagram files.",
            {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": [
                            "architecture",
                            "workflow",
                            "sequence",
                            "dataflow",
                            "lifecycle",
                        ],
                    },
                    "ir": {
                        "description": "Diagram IR object or JSON string for the chosen kind",
                    },
                    "title": {"type": "string"},
                },
                "required": ["kind", "ir"],
                "additionalProperties": False,
            },
        ),
        SpeakGrant("email.list_messages", ExecKind.SURFACE, "Fetch inbox summaries; optional since, today, limit, cached, refresh"),
        SpeakGrant("email.read_message", ExecKind.SURFACE, "Read and open an email message; uid required"),
        SpeakGrant("extension.install_github", ExecKind.SURFACE, "Install a GitHub MCP or skill; url required, optional kind and scope"),
        SpeakGrant("ide.debug", ExecKind.SURFACE, "Start an IDE debug session"),
        SpeakGrant("ide.definition", ExecKind.SURFACE, "Find definition at the IDE cursor or path, line and column"),
        SpeakGrant("ide.diagnostics", ExecKind.SURFACE, "Get IDE diagnostics; check reported before claiming clean"),
        SpeakGrant("ide.edit", ExecKind.SURFACE, "Edit the open IDE buffer; op and text required"),
        SpeakGrant("ide.enter_companion", ExecKind.SURFACE, "Enter IDE Companion"),
        SpeakGrant("ide.exit_companion", ExecKind.SURFACE, "Exit IDE Companion"),
        SpeakGrant("ide.marketplace_install", ExecKind.SURFACE, "Install an Open VSX extension; publisher.name id required"),
        SpeakGrant("ide.marketplace_search", ExecKind.SURFACE, "Search Open VSX extensions; query required"),
        SpeakGrant("ide.project_log", ExecKind.SURFACE, "Record an IDE project plan, decision, issue or progress"),
        SpeakGrant("ide.references", ExecKind.SURFACE, "Find references at the IDE cursor or path, line and column"),
        SpeakGrant("ide.save", ExecKind.SURFACE, "Save the open IDE buffer; optional path or all=true"),
        SpeakGrant("ide.symbols", ExecKind.SURFACE, "Get IDE document symbols; optional symbol filter and path"),
        SpeakGrant("ide.task", ExecKind.SURFACE, "Run an IDE tasks.json task by name"),
        SpeakGrant("learning.list", ExecKind.SURFACE, "List learned computer-use workflows"),
        SpeakGrant("learning.run", ExecKind.SURFACE, "Run a learned workflow; id and params from learning.list required"),
        SpeakGrant("learning.start", ExecKind.SURFACE, "Start demonstration recording"),
        SpeakGrant("learning.stop", ExecKind.SURFACE, "Stop demonstration recording"),
        SpeakGrant("project.rename_file", ExecKind.SURFACE, "Rename a bound-project file; path and new_path required"),
        SpeakGrant("project.write_file", ExecKind.SURFACE, "Write a requested file in the bound IDE project; rel_path and content required"),
        SpeakGrant("project.write_image_code", ExecKind.SURFACE, "Write code from an image; image path and rel_path required"),
        SpeakGrant("routine.create", ExecKind.SURFACE, "Create a routine; task must be the user's exact request, kind and schedule required"),
        SpeakGrant("routine.delete", ExecKind.SURFACE, "Delete a routine by id or name"),
        SpeakGrant("routine.list", ExecKind.SURFACE, "List registered routines"),
        SpeakGrant("routine.run", ExecKind.SURFACE, "Run a registered routine once"),
        SpeakGrant("routine.update", ExecKind.SURFACE, "Update a routine by id or name; enabled=false pauses it"),
        SpeakGrant("voice.mic_off", ExecKind.SURFACE, "Turn microphone listening off"),
        SpeakGrant("voice.mic_on", ExecKind.SURFACE, "Turn microphone listening on"),
        SpeakGrant("voice.toggle_mic", ExecKind.SURFACE, "Toggle microphone listening"),
        SpeakGrant("wiki.import_content", ExecKind.SURFACE, "Import and summarize one PDF, URL or file into Iris Wiki; source required"),
        SpeakGrant("wiki.import_pages", ExecKind.SURFACE, "Import and summarize multiple pages into Iris Wiki; sources required"),
        SpeakGrant("workspace.open_assistant", ExecKind.SURFACE, "Open the assistant home workspace"),
        SpeakGrant("workspace.open_calendar", ExecKind.SURFACE, "Open the calendar workspace"),
        SpeakGrant("workspace.open_email", ExecKind.SURFACE, "Open the email inbox workspace"),
        SpeakGrant("workspace.open_obsidian", ExecKind.SURFACE, "Open the Iris Wiki workspace"),
        SpeakGrant("browser.back", ExecKind.SURFACE, "Go back in the visible Iris browser"),
        SpeakGrant("browser.click", ExecKind.SURFACE, "Click a browser element by snapshot ref"),
        SpeakGrant("browser.extract", ExecKind.SURFACE, "Extract visible page article or document text"),
        SpeakGrant("browser.forward", ExecKind.SURFACE, "Go forward in the visible Iris browser"),
        SpeakGrant("browser.media", ExecKind.SURFACE, "Play, pause or resume visible browser media"),
        SpeakGrant("browser.mini_player", ExecKind.SURFACE, "Toggle the visible browser mini player"),
        SpeakGrant("browser.navigate", ExecKind.SURFACE, "Navigate the visible Iris browser; url required"),
        SpeakGrant("browser.open", ExecKind.SURFACE, "Open the Iris browser workspace"),
        SpeakGrant("browser.reload", ExecKind.SURFACE, "Reload the visible Iris browser page"),
        SpeakGrant("browser.scroll", ExecKind.SURFACE, "Scroll the visible Iris browser page or a ref"),
        SpeakGrant("browser.search", ExecKind.SURFACE, "Search the web or YouTube in the visible Iris browser; query required"),
        SpeakGrant("browser.snapshot", ExecKind.SURFACE, "Read the visible Iris browser controls and refs"),
        SpeakGrant("browser.type", ExecKind.SURFACE, "Type into a browser element by ref; text required"),
        SpeakGrant(
            "web.run_search",
            ExecKind.SURFACE,
            "Search the web (Iris Control; model name web_search).",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        SpeakGrant(
            "web.run_extract",
            ExecKind.SURFACE,
            "Extract page text from URLs (Iris Control; model name web_extract).",
            {
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "format": {"type": "string"},
                    "char_limit": {"type": "integer", "minimum": 1},
                },
                "required": ["urls"],
                "additionalProperties": False,
            },
        ),
        SpeakGrant("calendar.add_event", ExecKind.SURFACE, "Add a calendar event; title and start_at required"),
        SpeakGrant("calendar.delete_event", ExecKind.SURFACE, "Delete a calendar event by id"),
        SpeakGrant("calendar.refresh_holidays", ExecKind.SURFACE, "Refresh Korean public holidays"),
        SpeakGrant("calendar.select_day", ExecKind.SURFACE, "Select calendar day by date"),
        SpeakGrant("calendar.set_month", ExecKind.SURFACE, "Set calendar year and month"),
        SpeakGrant("calendar.status", ExecKind.SURFACE, "Get selected calendar day and events"),
        SpeakGrant(
            "content.extract",
            ExecKind.SURFACE,
            "Extract text from a PDF, URL, file, or chat attachment_id; optional page_from/page_to",
            {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "path": {"type": "string"},
                    "url": {"type": "string"},
                    "attachment_id": {"type": "string"},
                    "page_from": {"type": "integer", "minimum": 1},
                    "page_to": {"type": "integer", "minimum": 1},
                },
                "additionalProperties": True,
            },
        ),
        SpeakGrant("email.open_compose", ExecKind.SURFACE, "Open the email compose screen"),
        SpeakGrant("email.send", ExecKind.SURFACE, "Send email; to, subject and body required; human confirmation required"),
        SpeakGrant("emulator.input_text", ExecKind.SURFACE, "Type ASCII text into the Iris Android emulator"),
        SpeakGrant("emulator.install", ExecKind.SURFACE, "Install an APK by absolute apk path"),
        SpeakGrant("emulator.key", ExecKind.SURFACE, "Press an Android emulator key"),
        SpeakGrant("emulator.kill", ExecKind.SURFACE, "Stop the Iris Android emulator"),
        SpeakGrant("emulator.launch", ExecKind.SURFACE, "Start the Iris Android emulator"),
        SpeakGrant("emulator.logcat_tail", ExecKind.SURFACE, "Read the Android emulator logcat tail"),
        SpeakGrant("emulator.play_install", ExecKind.SURFACE, "Install an Android app through Play Store UI"),
        SpeakGrant("emulator.screenshot", ExecKind.SURFACE, "Capture the Iris Android emulator screenshot"),
        SpeakGrant("emulator.start_app", ExecKind.SURFACE, "Start an installed Android app by package"),
        SpeakGrant("emulator.status", ExecKind.SURFACE, "Get Iris Android emulator status"),
        SpeakGrant("emulator.swipe", ExecKind.SURFACE, "Swipe the Android emulator between coordinates"),
        SpeakGrant("emulator.tap", ExecKind.SURFACE, "Tap Android emulator coordinates"),
        SpeakGrant("emulator.tap_text", ExecKind.SURFACE, "Tap visible text in the Android emulator"),
        SpeakGrant("emulator.ui_texts", ExecKind.SURFACE, "List visible Android emulator text"),
        SpeakGrant("emulator.wait_ready", ExecKind.SURFACE, "Wait for the Android emulator to finish booting"),
        SpeakGrant("learning.status", ExecKind.SURFACE, "Get demonstration recording status"),
        SpeakGrant("project.create_scaffold", ExecKind.SURFACE, "Create and open a project folder; name and parent required"),
        SpeakGrant("project.list_files", ExecKind.SURFACE, "List files in the bound IDE project"),
        SpeakGrant("project.list_parents", ExecKind.SURFACE, "List permitted parent folders for new projects"),
        SpeakGrant("project.read_file", ExecKind.SURFACE, "Read a file in the bound IDE project by rel_path"),
        SpeakGrant("wiki.move_notes", ExecKind.SURFACE, "Move Wiki notes by sources and dest_folder"),
        SpeakGrant("wiki.open_note", ExecKind.SURFACE, "Open a Wiki note by rel_path"),
        SpeakGrant("wiki.reload", ExecKind.SURFACE, "Reload the Iris Wiki workspace"),
        SpeakGrant("workspace.open_mobile", ExecKind.SURFACE, "Open the Iris Android emulator workspace"),
        SpeakGrant("chat.exec_python", ExecKind.SURFACE, "Run Python for a chat plot and return chat_markdown"),
        SpeakGrant("content.dump_lab_scripts", ExecKind.SURFACE, "Create lab scripts from an attached lecture PDF"),
        SpeakGrant("ide.open_file", ExecKind.SURFACE, "Open an existing file in the bound IDE workspace"),
        SpeakGrant("project.delete", ExecKind.SURFACE, "Delete a project folder or relative path after confirmation"),
        SpeakGrant("voice.mic_status", ExecKind.SURFACE, "Read microphone listening status"),
    )
)


_BOUND_SURFACE: Any | None = None
_ENGINE_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")

SpeakSurface = Literal["home", "ide_companion"]
HOME_ONLY_SPEAK_ACTIONS = frozenset({"shell.run"})
_SPEAK_SURFACE: SpeakSurface = "home"


def normalize_speak_surface(raw: object) -> SpeakSurface:
    value = str(raw or "").strip().lower()
    if value in {"ide_companion", "companion", "ide"}:
        return "ide_companion"
    return "home"


def set_speak_surface(surface: SpeakSurface | str) -> None:
    global _SPEAK_SURFACE
    _SPEAK_SURFACE = normalize_speak_surface(surface)


def current_speak_surface() -> SpeakSurface:
    return _SPEAK_SURFACE


def grants_for_surface(
    allowlist: SpeakAllowlist, surface: SpeakSurface | str
) -> tuple[SpeakGrant, ...]:
    surf = normalize_speak_surface(surface)
    if surf == "home":
        return allowlist.grants
    return tuple(
        grant
        for grant in allowlist.grants
        if grant.action not in HOME_ONLY_SPEAK_ACTIONS
    )


def engine_tool_name(action: str) -> str:
    """Provider-safe function name for one dotted Control action id."""
    return (action or "").replace(".", "_")


def engine_tool_action(name: str) -> str:
    """Map a provider-visible function name back to its Control action id."""
    key = (name or "").strip()
    return next(
        (
            grant.action
            for grant in PHASE4_ALLOWLIST.grants
            if engine_tool_name(grant.action) == key
        ),
        key,
    )


def bind_live_control_surface(surface: Any | None) -> None:
    """Bind the GUI-owned surface so worker threads never enumerate Qt widgets."""
    global _BOUND_SURFACE
    _BOUND_SURFACE = surface


def engine_tool_schemas(
    surface: SpeakSurface | str | None = None,
) -> tuple[dict[str, Any], ...]:
    """OpenAI function bodies for engine-visible SpeakTools on one surface."""
    surf = (
        current_speak_surface()
        if surface is None
        else normalize_speak_surface(surface)
    )
    default_parameters = {"type": "object", "additionalProperties": True}
    schemas = tuple(
        {
            "name": engine_tool_name(grant.action),
            "description": grant.summary or grant.action,
            "parameters": dict(grant.parameters or default_parameters),
        }
        for grant in grants_for_surface(PHASE4_ALLOWLIST, surf)
    )
    names = [str(schema["name"]) for schema in schemas]
    if len(names) != len(set(names)) or not all(_ENGINE_TOOL_NAME_RE.fullmatch(n) for n in names):
        raise AssertionError("engine tool names must be unique provider-safe identifiers")
    return schemas


def _live_control_surface() -> Any | None:
    if _BOUND_SURFACE is not None:
        return _BOUND_SURFACE
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        return None
    app = QApplication.instance()
    if app is None:
        return None
    for widget in app.topLevelWidgets():
        surface = getattr(widget, "_control_surface", None)
        if surface is not None:
            return surface
    return None


def _invoke_live_control(action: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """In-process Control invoke (no HTTP). None when Iris UI surface is absent."""
    surface = _live_control_surface()
    if surface is None:
        return None
    from iris.system.control_surface import call_registered

    return call_registered(surface, action, dict(args or {}), timeout=30.0)


class _LiveSurfaceInvoker:
    def invoke(self, action: str, args: dict[str, Any]) -> dict[str, Any] | None:
        return _invoke_live_control(action, args)


class _LiveActionCatalog:
    def spec(self, name: str) -> Any | None:
        surface = _live_control_surface()
        if surface is None:
            return None
        reg = getattr(surface, "registry", None)
        if reg is None:
            return None
        return reg.spec(name)

    def catalog(self) -> list[dict[str, Any]]:
        surface = _live_control_surface()
        if surface is None:
            return []
        reg = getattr(surface, "registry", None)
        if reg is None:
            return []
        return list(reg.catalog())


def _from_control(action: str, control_out: dict[str, Any]) -> ToolResult:
    result = control_out.get("result")
    data = dict(result) if isinstance(result, dict) else {}
    data.setdefault("bridge", "none")
    if control_out.get("ok"):
        return ToolResult(ok=True, action=action, data=data, bridge="none")
    return ToolResult(
        ok=False,
        action=action,
        data=data,
        error=str(control_out.get("error") or "control invoke failed"),
        bridge="none",
    )


def _requires_iris_ui(action: str) -> ToolResult:
    return ToolResult(
        ok=False,
        action=action,
        data={"bridge": "none"},
        error="requires_iris_ui",
        bridge="none",
    )


def _wrap_registry_handler(
    registry: Any, iris_name: str, action: str
) -> PureHandler:
    def handler(args: dict[str, Any]) -> ToolResult:
        out = registry.invoke(iris_name, args)
        data = out.get("data") if isinstance(out.get("data"), dict) else {}
        data = dict(data)
        bridge = str(data.get("bridge") or "none")
        if out.get("ok"):
            return ToolResult(ok=True, action=action, data=data, bridge=bridge)
        return ToolResult(
            ok=False,
            action=action,
            data=data,
            error=str(out.get("error") or "invoke failed"),
            bridge=bridge,
        )

    return handler


def _app_directory_list_handler(args: dict[str, Any]) -> ToolResult:
    query = str((args or {}).get("query") or "").strip()
    directory = AppDirectory()
    entries = directory.search(query) if query else directory.list()
    return ToolResult(
        ok=True,
        action="app.directory_list",
        data={"apps": entries_as_dicts(entries), "query": query, "bridge": "none"},
        bridge="none",
    )


class SpeakTools:
    """Product speak surface: catalog + invoke over PHASE4 allowlist."""

    def __init__(
        self,
        allowlist: SpeakAllowlist,
        *,
        surface: SurfaceInvoker,
        actions: ActionCatalogView | None = None,
        pure_handlers: Mapping[str, PureHandler] | None = None,
    ) -> None:
        self._allowlist = allowlist
        self._surface = surface
        self._actions = actions
        self._pure = dict(pure_handlers or {})

    def catalog(self) -> list[SpeakToolRow]:
        rows: list[SpeakToolRow] = []
        for grant in grants_for_surface(self._allowlist, current_speak_surface()):
            spec = self._actions.spec(grant.action) if self._actions is not None else None
            summary = grant.summary
            confirm = False
            risk = "low"
            if spec is not None:
                summary = summary or str(getattr(spec, "summary", "") or "")
                confirm = bool(getattr(spec, "confirm_required", False))
                risk = str(getattr(spec, "risk", None) or "low")
            elif self._actions is not None and grant.kind is ExecKind.SURFACE:
                # SURFACE with no ActionSpec yet — still list from allowlist grant.
                pass
            rows.append(
                SpeakToolRow(
                    name=grant.action,
                    summary=summary,
                    domain=_domain_of(grant.action),
                    needs_ui=grant.kind is ExecKind.SURFACE,
                    confirm_required=confirm,
                    risk=risk,
                )
            )
        rows.sort(key=lambda r: r.name)
        return rows

    def engine_names(self) -> tuple[str, ...]:
        return self._allowlist.names()

    def invoke(self, action: str, args: dict[str, Any] | None = None) -> ToolResult:
        key = resolve_legacy_name((action or "").strip())
        payload = dict(args or {})
        grant = self._allowlist.grant(key)
        if grant is None:
            return ToolResult(
                ok=False,
                action=key or (action or ""),
                data={},
                error=f"not_allowed: {key or action}",
            )
        if (
            current_speak_surface() != "home"
            and key in HOME_ONLY_SPEAK_ACTIONS
        ):
            return ToolResult(
                ok=False,
                action=key,
                data={},
                error=f"not_allowed: {key}",
            )
        if grant.kind is ExecKind.PURE:
            if key == "get_catalog":
                return ToolResult(
                    ok=True,
                    action=key,
                    data={
                        "tools": [
                            {
                                "name": r.name,
                                "summary": r.summary,
                                "domain": r.domain,
                                "needs_ui": r.needs_ui,
                                "confirm_required": r.confirm_required,
                                "risk": r.risk,
                            }
                            for r in self.catalog()
                        ],
                        "bridge": "none",
                    },
                    bridge="none",
                )
            handler = self._pure.get(key)
            if handler is None:
                return ToolResult(
                    ok=False,
                    action=key,
                    data={},
                    error=f"pure handler missing: {key}",
                )
            try:
                return handler(payload)
            except Exception as exc:  # noqa: BLE001 — speak boundary
                return ToolResult(
                    ok=False,
                    action=key,
                    data={},
                    error=str(exc) or type(exc).__name__,
                )

        control_out = self._surface.invoke(key, payload)
        if control_out is None:
            return _requires_iris_ui(key)
        if not isinstance(control_out, dict):
            return ToolResult(
                ok=False,
                action=key,
                data={},
                error="invalid control result",
            )
        return _from_control(key, control_out)


def default_speak_tools(*, registry: Any | None = None) -> SpeakTools:
    from iris.infrastructure.agent_tool_registry import default_registry

    reg = registry if registry is not None else default_registry()
    pure: dict[str, PureHandler] = {
        "ping": _wrap_registry_handler(reg, "iris.tools.ping", "ping"),
        "wiki.list_notes": _wrap_registry_handler(
            reg, "iris.wiki.list_notes", "wiki.list_notes"
        ),
        "wiki.search": _wrap_registry_handler(reg, "iris.wiki.search", "wiki.search"),
        "email.list_accounts": _wrap_registry_handler(
            reg, "iris.mail.list_accounts", "email.list_accounts"
        ),
        "calendar.list_events": _wrap_registry_handler(
            reg, "iris.calendar.list_events", "calendar.list_events"
        ),
        "app.directory_list": _app_directory_list_handler,
    }
    return SpeakTools(
        PHASE4_ALLOWLIST,
        surface=_LiveSurfaceInvoker(),
        actions=_LiveActionCatalog(),
        pure_handlers=pure,
    )


def assert_engine_tools_match_allowlist(
    tools: tuple[str, ...] | None = None,
    allowlist: SpeakAllowlist = PHASE4_ALLOWLIST,
) -> None:
    """Boot check. Engine tool tuple must equal allowlist.names() — no MCP triple."""
    expected = allowlist.names()
    if tools is None:
        tools = expected
    mcp_triple = ("iris_get_state", "iris_get_catalog", "iris_invoke")
    if tuple(tools) == mcp_triple:
        raise AssertionError("engine tools must not be the MCP triple")
    if tuple(sorted(tools)) != expected:
        raise AssertionError(
            f"engine tools must match allowlist names: got {tuple(tools)!r} "
            f"expected {expected!r}"
        )
