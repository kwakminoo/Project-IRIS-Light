from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, Union

NODE_CAP = 40
NAME_CAP = 80
CTX_CAP = 24
EXCERPT_CAP = 800
EXTRACT_DEFAULT = 4000
EXTRACT_MAX = 8000

_PAGE_REF = re.compile(r"^g(\d+)e(\d+)$")


def make_page_ref(gen: int, index: int) -> str:
    if gen < 1 or index < 0:
        raise ValueError("ref parts out of range")
    return f"g{gen}e{index}"


def split_page_ref(ref: str) -> tuple[int, int]:
    match = _PAGE_REF.match(str(ref or ""))
    if match is None:
        raise ValueError("bad_ref")
    return int(match.group(1)), int(match.group(2))


class BrowserPhase(str, Enum):
    CLOSED = "closed"
    OPENING = "opening"
    READY = "ready"
    BUSY = "busy"
    FAULTED = "faulted"


class Actor(str, Enum):
    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"


@dataclass(frozen=True)
class PageNode:
    ref: str
    role: str
    name: str
    interactive: bool = True
    frame: str = ""
    in_view: bool = True
    disabled: bool = False
    checked: bool = False
    selected: bool = False
    focused: bool = False
    context: str = ""


@dataclass(frozen=True)
class FrameInfo:
    id: str
    origin: str
    reachable: bool
    reason: str = ""


DockedSite = Literal["dedicated", "ide_internal"]


@dataclass(frozen=True)
class PanelHost:
    """QWebEngineView is in BrowserPanel on this screen."""

    site: DockedSite
    kind: Literal["panel"] = "panel"


@dataclass(frozen=True)
class MiniHost:
    """QWebEngineView is in the Qt.Tool mini. resume is the dock to restore."""

    resume: DockedSite
    kind: Literal["mini"] = "mini"


ViewHost = Union[PanelHost, MiniHost]
UiMode = Literal["normal", "ide_hero", "ide_companion", "dedicated_browser"]
MediaAction = Literal["play", "pause", "resume"]


def is_mini(host: ViewHost) -> bool:
    return isinstance(host, MiniHost)


def is_docked(host: ViewHost) -> bool:
    return isinstance(host, PanelHost)


def docked_site(host: ViewHost) -> DockedSite:
    if isinstance(host, MiniHost):
        return host.resume
    return host.site


def as_mini(host: ViewHost) -> MiniHost:
    return MiniHost(resume=docked_site(host))


def as_docked(host: ViewHost) -> PanelHost:
    return PanelHost(site=docked_site(host))


def parse_view_host(raw: object, *, docked_default: DockedSite) -> ViewHost:
    """Boundary only. Leftover 'panel' cannot name a screen."""
    if isinstance(raw, (PanelHost, MiniHost)):
        return raw
    if raw == "mini":
        return MiniHost(resume=docked_default)
    if raw == "dedicated":
        return PanelHost(site="dedicated")
    if raw == "ide_internal":
        return PanelHost(site="ide_internal")
    if raw == "panel":
        raise ValueError("view host 'panel' is gone; use dedicated or ide_internal")
    raise ValueError(f"unknown view host: {raw!r}")


def uses_unified_shell(mode: str) -> bool:
    return mode in ("ide_companion", "dedicated_browser")


def left_occupant(mode: str) -> Literal["none", "theia", "browser"]:
    if mode == "ide_companion":
        return "theia"
    if mode == "dedicated_browser":
        return "browser"
    return "none"


@dataclass(frozen=True)
class MediaState:
    playing: bool = False
    paused: bool = True
    current_time: float = 0.0
    ready_state: int = 0
    block: str = ""
    ad: bool = False
    kind: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "playing": self.playing,
            "paused": self.paused,
            "current_time": self.current_time,
            "ready_state": self.ready_state,
            "block": self.block,
            "ad": self.ad,
            "kind": self.kind,
        }


def media_from_dict(raw: object) -> MediaState | None:
    if not isinstance(raw, dict):
        return None
    try:
        return MediaState(
            playing=bool(raw.get("playing")),
            paused=bool(raw.get("paused", not raw.get("playing"))),
            current_time=float(raw.get("currentTime") or raw.get("current_time") or 0),
            ready_state=int(raw.get("readyState") or raw.get("ready_state") or 0),
            block=str(raw.get("block") or ""),
            ad=bool(raw.get("ad")),
            kind=str(raw.get("kind") or ""),
        )
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class BrowserSnapshot:
    url: str
    title: str
    phase: BrowserPhase
    can_go_back: bool
    can_go_forward: bool
    scroll_x: int
    scroll_y: int
    last_error: str | None = None
    gen: int = 0
    nodes: tuple[PageNode, ...] = ()
    excerpt: str = ""
    mini_player: bool = False
    media: MediaState | None = None
    tab_index: int = 0
    tab_count: int = 1
    target_id: str = ""
    frames: tuple[FrameInfo, ...] = ()

    def to_gui_dict(self) -> dict[str, Any]:
        media = self.media.to_dict() if self.media is not None else None
        return {
            "url": self.url,
            "title": self.title,
            "phase": self.phase.value,
            "browser_phase": self.phase.value,
            "can_go_back": self.can_go_back,
            "can_go_forward": self.can_go_forward,
            "scroll_x": self.scroll_x,
            "scroll_y": self.scroll_y,
            "last_error": self.last_error,
            "browser_open": self.phase != BrowserPhase.CLOSED,
            "browser_url": self.url,
            "browser_title": self.title,
            "mini_player": self.mini_player,
            "media": media,
            "browser_playing": bool(self.media and self.media.playing),
            "browser_media_block": (self.media.block if self.media else "") or "",
            "tab_index": self.tab_index,
            "tab_count": self.tab_count,
            "target_id": self.target_id or f"tab:{self.tab_index}",
            "gen": self.gen,
        }

    def to_control_dict(self) -> dict[str, Any]:
        return self.to_gui_dict()

    def evolve(self, **kwargs: Any) -> "BrowserSnapshot":
        data = {
            "url": self.url,
            "title": self.title,
            "phase": self.phase,
            "can_go_back": self.can_go_back,
            "can_go_forward": self.can_go_forward,
            "scroll_x": self.scroll_x,
            "scroll_y": self.scroll_y,
            "last_error": self.last_error,
            "gen": self.gen,
            "nodes": self.nodes,
            "excerpt": self.excerpt,
            "mini_player": self.mini_player,
            "media": self.media,
            "tab_index": self.tab_index,
            "tab_count": self.tab_count,
            "target_id": self.target_id,
            "frames": self.frames,
        }
        data.update(kwargs)
        return BrowserSnapshot(**data)


@dataclass(frozen=True)
class ByRef:
    ref: str


@dataclass(frozen=True)
class ByCss:
    css: str


@dataclass(frozen=True)
class ByText:
    text: str
    nth: int = 0
    exact: bool = False


@dataclass(frozen=True)
class ByRole:
    role: str
    name: str | None = None
    nth: int = 0
    exact: bool = False


DriverLocator = Union[ByCss, ByText, ByRole]
Locator = Union[ByRef, DriverLocator]


@dataclass(frozen=True)
class Open:
    source: Actor = Actor.AGENT
    kind: Literal["open"] = "open"


@dataclass(frozen=True)
class Navigate:
    url: str
    source: Actor = Actor.AGENT
    kind: Literal["navigate"] = "navigate"


@dataclass(frozen=True)
class Reload:
    source: Actor = Actor.AGENT
    kind: Literal["reload"] = "reload"


@dataclass(frozen=True)
class HistoryStep:
    delta: Literal[-1, 1]
    source: Actor = Actor.AGENT
    kind: Literal["history"] = "history"


@dataclass(frozen=True)
class Search:
    query: str
    engine: Literal["web", "google", "youtube"] = "web"
    play: bool = False
    source: Actor = Actor.AGENT
    kind: Literal["search"] = "search"


@dataclass(frozen=True)
class Click:
    target: ByRef
    source: Actor = Actor.AGENT
    kind: Literal["click"] = "click"


@dataclass(frozen=True)
class TypeText:
    target: ByRef
    text: str
    clear: bool = True
    source: Actor = Actor.AGENT
    kind: Literal["type"] = "type"


@dataclass(frozen=True)
class Scroll:
    delta_x: int = 0
    delta_y: int = 0
    ref: str | None = None
    source: Actor = Actor.AGENT
    kind: Literal["scroll"] = "scroll"


@dataclass(frozen=True)
class Snapshot:
    source: Actor = Actor.AGENT
    kind: Literal["snapshot"] = "snapshot"


@dataclass(frozen=True)
class Extract:
    scope: Literal["article", "document"] = "article"
    ref: str | None = None
    max_chars: int = EXTRACT_DEFAULT
    source: Actor = Actor.AGENT
    kind: Literal["extract"] = "extract"


@dataclass(frozen=True)
class MiniPlayer:
    on: bool
    source: Actor = Actor.AGENT
    kind: Literal["mini_player"] = "mini_player"


@dataclass(frozen=True)
class Media:
    action: MediaAction
    source: Actor = Actor.AGENT
    kind: Literal["media"] = "media"


BrowserCommand = Union[
    Open,
    Navigate,
    Reload,
    HistoryStep,
    Search,
    Click,
    TypeText,
    Scroll,
    Snapshot,
    Extract,
    MiniPlayer,
    Media,
]


@dataclass(frozen=True)
class BrowserResult:
    ok: bool
    command_kind: str
    snapshot: BrowserSnapshot
    detail: str = ""
    read_text: str = ""

    def to_gui_dict(self) -> dict[str, Any]:
        data = self.snapshot.to_gui_dict()
        data["ok"] = self.ok
        data["command_kind"] = self.command_kind
        if self.detail:
            data["detail"] = self.detail
        return data

    def to_control_dict(self) -> dict[str, Any]:
        return self.to_gui_dict()


def empty_snapshot(*, phase: BrowserPhase = BrowserPhase.CLOSED) -> BrowserSnapshot:
    return BrowserSnapshot(
        url="",
        title="",
        phase=phase,
        can_go_back=False,
        can_go_forward=False,
        scroll_x=0,
        scroll_y=0,
    )


def parse_page_url(raw: str) -> str:
    """Boundary: reject javascript:/data:; normalize bare hosts to https."""
    u = (raw or "").strip()
    if not u:
        raise ValueError("url required")
    low = u.lower()
    if low.startswith("javascript:") or low.startswith("data:"):
        raise ValueError("disallowed url scheme")
    if low in ("about:blank",):
        return "about:blank"
    if low.startswith(("http://", "https://", "file:")):
        return u
    if "://" in u:
        raise ValueError("disallowed url scheme")
    return "https://" + u
