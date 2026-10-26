from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from iris.browser.search import normalize_search_engine
from iris.browser.types import (
    Actor,
    BrowserCommand,
    ByRef,
    Click,
    Extract,
    HistoryStep,
    Media,
    MiniPlayer,
    Navigate,
    Open,
    Reload,
    Scroll,
    Search,
    Snapshot,
    TypeText,
    EXTRACT_MAX,
    EXTRACT_DEFAULT,
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


def _parse_ref(args: dict[str, Any]) -> ByRef:
    if isinstance(args.get("target"), dict):
        return _parse_ref(args["target"])
    ref = str(args.get("ref") or "").strip()
    if not ref:
        raise ValueError("ref required")
    return ByRef(ref=ref)


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
    engine = normalize_search_engine(str(args.get("engine") or "web"))
    play = bool(args.get("play") or args.get("autoplay"))
    return Search(query=query, engine=engine, play=play, source=_actor(args))


def _parse_click(args: dict[str, Any]) -> BrowserCommand:
    return Click(target=_parse_ref(args), source=_actor(args))


def _parse_type(args: dict[str, Any]) -> BrowserCommand:
    if "text" not in args:
        raise ValueError("text required")
    return TypeText(
        target=_parse_ref(args),
        text=str(args.get("text") or ""),
        clear=bool(args.get("clear", True)),
        source=_actor(args),
    )


def _parse_extract(args: dict[str, Any]) -> BrowserCommand:
    scope = str(args.get("scope") or "article").strip().lower() or "article"
    if scope not in ("article", "document"):
        raise ValueError("scope must be article|document")
    raw_ref = args.get("ref")
    ref = str(raw_ref).strip() if raw_ref else None
    if ref == "":
        ref = None
    try:
        max_chars = int(args.get("max_chars") or EXTRACT_DEFAULT)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_chars must be int") from exc
    if max_chars < 1:
        max_chars = 1
    if max_chars > EXTRACT_MAX:
        max_chars = EXTRACT_MAX
    return Extract(scope=scope, ref=ref, max_chars=max_chars, source=_actor(args))  # type: ignore[arg-type]


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


def _parse_media(args: dict[str, Any]) -> BrowserCommand:
    action = str(args.get("media") or args.get("op") or "").strip().lower()
    if not action:
        raw = str(args.get("action") or "").strip().lower()
        if raw.startswith("browser."):
            raw = raw.split(".", 1)[-1]
        action = "" if raw == "media" else raw
    if action in ("play", "resume"):
        return Media(action="resume" if action == "resume" else "play", source=_actor(args))
    if action == "pause":
        return Media(action="pause", source=_actor(args))
    raise ValueError("media action must be play|pause|resume")


def command_specs() -> tuple[CommandSpec, ...]:
    return (
        CommandSpec("open", "Show dedicated browser or IDE-internal cover", "low", _parse_open, control_name="browser.open"),
        CommandSpec("navigate", "Navigate browser to url", "medium", _parse_navigate, control_name="browser.navigate"),
        CommandSpec("reload", "Reload current browser page", "low", _parse_reload, control_name="browser.reload"),
        CommandSpec("back", "Browser history back", "low", _parse_back, control_name="browser.back"),
        CommandSpec("forward", "Browser history forward", "low", _parse_forward, control_name="browser.forward"),
        CommandSpec(
            "search",
            "Web search then open results (engine=web|google|youtube, play?)",
            "medium",
            _parse_search,
            control_name="browser.search",
        ),
        CommandSpec("click", "Click ref from the last PAGE TEXT", "medium", _parse_click, control_name="browser.click"),
        CommandSpec("type", "Type into ref from the last PAGE TEXT", "medium", _parse_type, control_name="browser.type"),
        CommandSpec("scroll", "Scroll current page", "low", _parse_scroll, control_name="browser.scroll"),
        CommandSpec("snapshot", "Refresh browser observation", "low", _parse_snapshot, control_name="browser.snapshot"),
        CommandSpec(
            "extract",
            "Read article or document text on the current page",
            "low",
            _parse_extract,
            control_name="browser.extract",
        ),
        CommandSpec(
            "mini_player",
            "Detach or restore browser view as mini player",
            "low",
            _parse_mini_player,
            control_name="browser.mini_player",
        ),
        CommandSpec(
            "media",
            "Play, pause, or resume the current page media element",
            "medium",
            _parse_media,
            control_name="browser.media",
        ),
    )


@dataclass(frozen=True)
class Recipe:
    when: str
    text: str
    control_names: tuple[str, ...]
    success: str


def command_recipes() -> tuple[Recipe, ...]:
    return (
        Recipe(
            when="youtube_play",
            text=(
                "Play YouTube: iris_invoke browser.search {engine:youtube, play:true}. "
                "Empty leftover query becomes 음악. Success is media.playing. "
                "Do not claim speakers. Do not claim the video was analyzed."
            ),
            control_names=("browser.search", "browser.media"),
            success="media.playing",
        ),
        Recipe(
            when="news",
            text=(
                "Read news: iris_invoke browser.search or browser.navigate, then "
                "browser.click {ref}, then browser.extract. Success is extract text in PAGE TEXT plus trusted url."
            ),
            control_names=("browser.search", "browser.navigate", "browser.click", "browser.extract"),
            success="page_text",
        ),
        Recipe(
            when="paper",
            text=(
                "Read a paper: browser.navigate or browser.search then browser.click {ref}, then browser.extract. "
                "Cite PAGE TEXT. Do not claim figures or PDF layout were read."
            ),
            control_names=("browser.search", "browser.navigate", "browser.click", "browser.extract"),
            success="page_text",
        ),
        Recipe(
            when="not_browser",
            text="Pause/resume: browser.media {action:pause|resume}.",
            control_names=("browser.media",),
            success="none",
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
