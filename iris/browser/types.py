from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, Union


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
class Landmark:
    role: str
    name: str
    bbox: tuple[int, int, int, int] | None = None


ViewHost = Literal["panel", "mini"]
MediaAction = Literal["play", "pause", "resume"]


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
    landmarks: tuple[Landmark, ...] = ()
    mini_player: bool = False
    media: MediaState | None = None
    tab_index: int = 0
    tab_count: int = 1
    target_id: str = ""

    def to_control_dict(self) -> dict[str, Any]:
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
            "landmarks": [
                {
                    "role": lm.role,
                    "name": lm.name,
                    "bbox": list(lm.bbox) if lm.bbox is not None else None,
                }
                for lm in self.landmarks
            ],
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
        }

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
            "landmarks": self.landmarks,
            "mini_player": self.mini_player,
            "media": self.media,
            "tab_index": self.tab_index,
            "tab_count": self.tab_count,
            "target_id": self.target_id,
        }
        data.update(kwargs)
        return BrowserSnapshot(**data)


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


Locator = Union[ByCss, ByText, ByRole]


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
    target: Locator
    source: Actor = Actor.AGENT
    kind: Literal["click"] = "click"


@dataclass(frozen=True)
class TypeText:
    target: Locator
    text: str
    clear: bool = True
    source: Actor = Actor.AGENT
    kind: Literal["type"] = "type"


@dataclass(frozen=True)
class Scroll:
    delta_x: int = 0
    delta_y: int = 0
    source: Actor = Actor.AGENT
    kind: Literal["scroll"] = "scroll"


@dataclass(frozen=True)
class Snapshot:
    source: Actor = Actor.AGENT
    kind: Literal["snapshot"] = "snapshot"


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
    MiniPlayer,
    Media,
]


@dataclass(frozen=True)
class BrowserResult:
    ok: bool
    command_kind: str
    snapshot: BrowserSnapshot
    detail: str = ""

    def to_control_dict(self) -> dict[str, Any]:
        data = self.snapshot.to_control_dict()
        data["ok"] = self.ok
        data["command_kind"] = self.command_kind
        if self.detail:
            data["detail"] = self.detail
        return data


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
