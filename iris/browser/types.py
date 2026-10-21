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

    def to_control_dict(self) -> dict[str, Any]:
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
        }


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
    engine: Literal["web"] = "web"
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
