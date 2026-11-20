"""App Directory registry — builtin seed + installed persist.

Owns: list / search / get / install / uninstall for App Host apps.
Does not: render ChatPanel UI or talk to external MCP servers.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from iris.system.iris_agent_control_sync import iris_state_dir

SOURCE_BUILTIN = "builtin"
SOURCE_INSTALLED = "installed"


@dataclass(frozen=True)
class AppDirectoryEntry:
    id: str
    title: str
    summary: str
    resource_uri: str
    source: str
    server_name: str = ""


BUILTIN_APPS: tuple[AppDirectoryEntry, ...] = (
    AppDirectoryEntry(
        id="demo-ping",
        title="데모 앱",
        summary="App Host ping demo (app_host_ping.html)",
        resource_uri="app_host_ping.html",
        source=SOURCE_BUILTIN,
    ),
)


def default_directory_path() -> Path:
    return iris_state_dir() / "apps" / "directory.json"


def _parse_entry(raw: object) -> AppDirectoryEntry | None:
    if not isinstance(raw, dict):
        return None
    app_id = str(raw.get("id") or "").strip()
    title = str(raw.get("title") or "").strip()
    summary = str(raw.get("summary") or "").strip()
    resource_uri = str(raw.get("resource_uri") or "").strip()
    source = str(raw.get("source") or SOURCE_INSTALLED).strip() or SOURCE_INSTALLED
    server_name = str(raw.get("server_name") or "").strip()
    if not app_id or not title or not resource_uri:
        return None
    if source not in (SOURCE_BUILTIN, SOURCE_INSTALLED):
        source = SOURCE_INSTALLED
    return AppDirectoryEntry(
        id=app_id,
        title=title,
        summary=summary,
        resource_uri=resource_uri,
        source=source,
        server_name=server_name,
    )


class AppDirectory:
    """Registry for builtin + installed App Host entries."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path if path is not None else default_directory_path()
        self._installed: dict[str, AppDirectoryEntry] = {}
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        self._installed = {}
        if not self._path.is_file():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        rows = data.get("installed") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return
        for raw in rows:
            entry = _parse_entry(raw)
            if entry is None:
                continue
            installed = AppDirectoryEntry(
                id=entry.id,
                title=entry.title,
                summary=entry.summary,
                resource_uri=entry.resource_uri,
                source=SOURCE_INSTALLED,
                server_name=entry.server_name,
            )
            self._installed[installed.id] = installed

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "installed": [asdict(e) for e in self._installed.values()],
        }
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list(self) -> list[AppDirectoryEntry]:
        by_id: dict[str, AppDirectoryEntry] = {e.id: e for e in BUILTIN_APPS}
        by_id.update(self._installed)
        return sorted(by_id.values(), key=lambda e: e.id)

    def search(self, query: str) -> list[AppDirectoryEntry]:
        needle = (query or "").strip().lower()
        if not needle:
            return self.list()
        out: list[AppDirectoryEntry] = []
        for entry in self.list():
            hay = f"{entry.id} {entry.title} {entry.summary}".lower()
            if needle in hay:
                out.append(entry)
        return out

    def get(self, app_id: str) -> AppDirectoryEntry | None:
        key = (app_id or "").strip()
        if not key:
            return None
        if key in self._installed:
            return self._installed[key]
        for entry in BUILTIN_APPS:
            if entry.id == key:
                return entry
        return None

    def install(self, entry: AppDirectoryEntry) -> AppDirectoryEntry:
        app_id = (entry.id or "").strip()
        if not app_id:
            raise ValueError("app id required")
        stored = AppDirectoryEntry(
            id=app_id,
            title=(entry.title or "").strip() or app_id,
            summary=(entry.summary or "").strip(),
            resource_uri=(entry.resource_uri or "").strip(),
            source=SOURCE_INSTALLED,
            server_name=(entry.server_name or "").strip(),
        )
        if not stored.resource_uri:
            raise ValueError("resource_uri required")
        self._installed[stored.id] = stored
        self._save()
        return stored

    def uninstall(self, app_id: str) -> bool:
        key = (app_id or "").strip()
        if not key or key not in self._installed:
            return False
        del self._installed[key]
        self._save()
        return True


def entries_as_dicts(entries: list[AppDirectoryEntry]) -> list[dict[str, str]]:
    return [asdict(e) for e in entries]
