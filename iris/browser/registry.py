from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from iris.browser.types import (
    Actor,
    BrowserCommand,
    ByCss,
    ByRole,
    ByText,
    Click,
    HistoryStep,
    Locator,
    MiniPlayer,
    Navigate,
    Open,
    Reload,
    Scroll,
    Search,
    Snapshot,
    TypeText,
    parse_page_url,
)


@dataclass(frozen=True)
class CommandSpec:
    kind: str
    summary: str
    risk: str
    parse: Callable[[dict[str, Any]], BrowserCommand]
    off_ui: bool = True
    control_name: str = ""


def _actor(args: dict[str, Any]) -> Actor:
    raw = str(args.get("source") or "agent").strip().lower()
    if raw == "human":
        return Actor.HUMAN
    if raw == "system":
        return Actor.SYSTEM
    return Actor.AGENT


def _parse_locator(args: dict[str, Any]) -> Locator:
    if isinstance(args.get("target"), dict):
        return _parse_locator(args["target"])
    by = str(args.get("by") or args.get("strategy") or "").strip().lower()
    selector = str(args.get("selector") or "").strip()
    if selector.startswith("text="):
        return ByText(text=selector[5:], nth=int(args.get("nth") or 0), exact=bool(args.get("exact")))
    if selector.startswith("css="):
        return ByCss(css=selector[4:])
    if selector.startswith("role="):
        rest = selector[5:]
        name = str(args.get("name") or "").strip() or None
        return ByRole(role=rest, name=name, nth=int(args.get("nth") or 0), exact=bool(args.get("exact")))
    if by in ("css", "css_selector") or args.get("css"):
        css = str(args.get("css") or args.get("value") or args.get("name") or selector).strip()
        if not css:
            raise ValueError("css selector required")
        return ByCss(css=css)
    if by in ("text", "link") or (not by and args.get("text")):
        text = str(args.get("text") or args.get("value") or args.get("name") or "").strip()
        if not text:
            raise ValueError("text required")
        return ByText(
            text=text,
            nth=int(args.get("nth") or 0),
            exact=bool(args.get("exact")),
        )
    if by == "role":
        role = str(args.get("role") or args.get("value") or "").strip()
        if not role:
            raise ValueError("role required")
        name = str(args.get("name") or "").strip() or None
        return ByRole(
            role=role,
            name=name,
            nth=int(args.get("nth") or 0),
            exact=bool(args.get("exact")),
        )
    if selector:
        return ByCss(css=selector)
    raise ValueError("locator required (by=text|role|css)")


def _parse_open(args: dict[str, Any]) -> BrowserCommand:
    return Open(source=_actor(args))


def _parse_navigate(args: dict[str, Any]) -> BrowserCommand:
    return Navigate(url=parse_page_url(str(args.get("url") or "")), source=_actor(args))


def _parse_reload(args: dict[str, Any]) -> BrowserCommand:
    return Reload(source=_actor(args))


def _parse_back(args: dict[str, Any]) -> BrowserCommand:
    return HistoryStep(delta=-1, source=_actor(args))


def _parse_forward(args: dict[str, Any]) -> BrowserCommand:
    return HistoryStep(delta=1, source=_actor(args))


def _parse_search(args: dict[str, Any]) -> BrowserCommand:
    query = str(args.get("query") or args.get("q") or "").strip()
    if not query:
        raise ValueError("query required")
    engine = str(args.get("engine") or "web").strip().lower() or "web"
    if engine != "web":
        raise ValueError(f"unsupported search engine: {engine}")
    return Search(query=query, engine="web", source=_actor(args))


def _parse_click(args: dict[str, Any]) -> BrowserCommand:
    return Click(target=_parse_locator(args), source=_actor(args))


def _parse_type(args: dict[str, Any]) -> BrowserCommand:
    if "text" not in args:
        raise ValueError("text required")
    return TypeText(
        target=_parse_locator(args),
        text=str(args.get("text") or ""),
        clear=bool(args.get("clear", True)),
        source=_actor(args),
    )


def _parse_scroll(args: dict[str, Any]) -> BrowserCommand:
    page = str(args.get("page") or "").strip().lower()
    dx = int(args.get("dx") or args.get("delta_x") or 0)
    dy = int(args.get("dy") or args.get("delta_y") or 0)
    if page == "down":
        dy = dy or 800
    elif page == "up":
        dy = dy or -800
    return Scroll(delta_x=dx, delta_y=dy, source=_actor(args))


def _parse_snapshot(args: dict[str, Any]) -> BrowserCommand:
    return Snapshot(source=_actor(args))


def _parse_bool_on(args: dict[str, Any]) -> bool:
    if "on" not in args:
        raise ValueError("on required")
    raw = args.get("on")
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)) and raw in (0, 1):
        return bool(raw)
    text = str(raw).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    raise ValueError("on must be bool")


def _parse_mini_player(args: dict[str, Any]) -> BrowserCommand:
    return MiniPlayer(on=_parse_bool_on(args), source=_actor(args))


def command_specs() -> tuple[CommandSpec, ...]:
    return (
        CommandSpec("open", "Show Iris IDE browser stack page", "low", _parse_open, control_name="browser.open"),
        CommandSpec("navigate", "Navigate browser to url", "medium", _parse_navigate, control_name="browser.navigate"),
        CommandSpec("reload", "Reload current browser page", "low", _parse_reload, control_name="browser.reload"),
        CommandSpec("back", "Browser history back", "low", _parse_back, control_name="browser.back"),
        CommandSpec("forward", "Browser history forward", "low", _parse_forward, control_name="browser.forward"),
        CommandSpec("search", "Web search then open results", "medium", _parse_search, control_name="browser.search"),
        CommandSpec("click", "Click locator on current page", "medium", _parse_click, control_name="browser.click"),
        CommandSpec("type", "Type into locator on current page", "medium", _parse_type, control_name="browser.type"),
        CommandSpec("scroll", "Scroll current page", "low", _parse_scroll, control_name="browser.scroll"),
        CommandSpec("snapshot", "Refresh browser observation", "low", _parse_snapshot, control_name="browser.snapshot"),
        CommandSpec(
            "mini_player",
            "Detach or restore browser view as mini player",
            "low",
            _parse_mini_player,
            control_name="browser.mini_player",
        ),
    )


_SPECS_BY_KIND = {s.kind: s for s in command_specs()}
_SPECS_BY_CONTROL = {s.control_name: s for s in command_specs()}


def parse_command(args: dict[str, Any]) -> BrowserCommand:
    """Parse wire dict → BrowserCommand. Validation only at this boundary."""
    if not isinstance(args, dict):
        raise ValueError("args must be object")
    kind = str(args.get("command") or args.get("kind") or "").strip().lower()
    action = str(args.get("action") or "").strip().lower()
    if action.startswith("browser."):
        spec = _SPECS_BY_CONTROL.get(action)
        if spec is None:
            raise ValueError(f"unknown browser action: {action}")
        return spec.parse(args)
    if not kind:
        raise ValueError("command required")
    if kind == "history":
        delta = int(args.get("delta") or 0)
        if delta == -1:
            return HistoryStep(delta=-1, source=_actor(args))
        if delta == 1:
            return HistoryStep(delta=1, source=_actor(args))
        raise ValueError("history delta must be -1 or 1")
    spec = _SPECS_BY_KIND.get(kind)
    if spec is None:
        raise ValueError(f"unknown browser command: {kind}")
    return spec.parse(args)


def control_action_names() -> tuple[str, ...]:
    return tuple(s.control_name for s in command_specs())


def spec_for_control(name: str) -> CommandSpec | None:
    return _SPECS_BY_CONTROL.get(name)
