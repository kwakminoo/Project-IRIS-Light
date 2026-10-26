# DESIGN — BrowserSession command bus (candidate-1)

OSS choice: **Qt WebEngine (Chromium) as the sole live page**, automated via a private `PageDriver` (QWebChannel + injected locator helpers). Playwright is not the visible session; see [REJECTED.md](REJECTED.md).

Invariant: one `BrowserSession` owns domain state. Human chrome and agent tools both submit `BrowserCommand` values through `session.execute`. No parallel “is_loading / can_go_back” booleans outside the session snapshot.

---

## Usage (call sites first)

### README / quickstart (consumer view)

```text
Agent or UI wants the IDE browser to do something.
→ Build a BrowserCommand (navigate, click, type, scroll, search, history).
→ Call BrowserSession.execute(cmd)  [or Control Surface browser.invoke].
→ Read BrowserSnapshot from the result; the same QWebEngine panel the user
  already sees updates. No second invisible browser.
```

Hermes / Agent path stays thin MCP: one `iris_invoke` action family, not a tool explosion.

### Call site 1 — Agent via Control Surface (Hermes MCP)

```python
# iris/ui/control_actions/browser.py  (registration shell)
# Agent: iris_invoke("browser.invoke", {"command": "search", "query": "IU night letter live"})
#        iris_invoke("browser.invoke", {"command": "click", "selector": "text=IU"})
#        iris_invoke("browser.invoke", {"command": "navigate", "url": "https://react.dev"})

from iris.browser.session import get_browser_session
from iris.browser.commands import parse_command

def handle_browser_invoke(args: dict) -> dict:
    session = get_browser_session()  # process singleton; lazy panel
    cmd = parse_command(args)        # wire dict → BrowserCommand (boundary)
    result = session.execute(cmd)    # off-UI worker; marshals UI touches
    return result.to_control_dict()  # ok_result / err_result shape
```

### Call site 2 — Human chrome (URL bar / reload / back / forward)

```python
# iris/ui/browser/panel.py  — toolbar slots; no separate nav logic

class BrowserPanel:
    def on_url_submitted(self, text: str) -> None:
        self._session.execute(Navigate(url=normalize_url(text), source="human"))

    def on_reload(self) -> None:
        self._session.execute(Reload(source="human"))

    def on_back(self) -> None:
        self._session.execute(HistoryStep(delta=-1, source="human"))

    def on_forward(self) -> None:
        self._session.execute(HistoryStep(delta=+1, source="human"))

    def on_snapshot_changed(self, snap: BrowserSnapshot) -> None:
        # UI binds to snapshot only — never reads QWebEngine history flags itself
        self._url_bar.setText(snap.url)
        self._back.setEnabled(snap.can_go_back)
        self._forward.setEnabled(snap.can_go_forward)
        self._reload.setEnabled(snap.ready != ReadyState.LOADING)
```

### Call site 3 — Scenario tests (verifiable)

```python
# tests/browser/test_browser_scenarios.py

def test_youtube_iu_night_letter(session: BrowserSession, panel: BrowserPanel):
    r = session.execute(Search(query="IU night letter", engine="web"))
    assert r.ok and "youtube" in r.snapshot.url.lower() or r.snapshot.title
    # click first meaningful result (locator from snapshot.a11y or CSS)
    r = session.execute(Click(target=ByText("IU", nth=0)))
    assert r.ok
    assert panel.isVisible() and panel.shows_same_url(r.snapshot.url)

def test_open_react_docs(session: BrowserSession):
    r = session.execute(Navigate(url="https://react.dev"))
    assert r.ok
    assert "react.dev" in r.snapshot.url
    assert r.snapshot.ready == ReadyState.COMPLETE

def test_scroll_current_page(session: BrowserSession):
    session.execute(Navigate(url="https://react.dev/learn"))
    before = session.snapshot().scroll_y
    r = session.execute(Scroll(delta_y=800))
    assert r.ok and r.snapshot.scroll_y > before
```

---

## Type sketch

```python
# iris/browser/types.py
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Literal, Union

class ReadyState(str, Enum):
    IDLE = "idle"          # no page yet
    LOADING = "loading"
    COMPLETE = "complete"
    ERROR = "error"

class Actor(str, Enum):
    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"

@dataclass(frozen=True)
class BrowserSnapshot:
    """Single source of truth for UI + agent observations.
    Derived from the live page; never hand-synced with toolbar flags.
    """
    url: str
    title: str
    ready: ReadyState
    can_go_back: bool
    can_go_forward: bool
    scroll_x: int
    scroll_y: int
    last_error: str | None
    # Compact a11y / text extract for agent targeting (not full DOM dump)
    landmarks: tuple[str, ...]

@dataclass(frozen=True)
class ByCss:
    css: str

@dataclass(frozen=True)
class ByText:
    text: str
    nth: int = 0

@dataclass(frozen=True)
class ByRole:
    role: str
    name: str | None = None

Locator = Union[ByCss, ByText, ByRole]

# --- Commands (closed set; registry derives ActionSpecs + parsers) ---

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
    """No-op mutation; refresh observation for the agent."""
    source: Actor = Actor.AGENT
    kind: Literal["snapshot"] = "snapshot"

BrowserCommand = Union[
    Navigate, Reload, HistoryStep, Search, Click, TypeText, Scroll, Snapshot
]

@dataclass(frozen=True)
class BrowserResult:
    ok: bool
    command_kind: str
    snapshot: BrowserSnapshot
    detail: str = ""

    def to_control_dict(self) -> dict:
        raise NotImplementedError("not implemented")
```

```python
# iris/browser/registry.py
"""Single command table. ActionSpecs, parsers, and off-UI policy derive from this."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable

from iris.browser.types import BrowserCommand

@dataclass(frozen=True)
class CommandSpec:
    kind: str
    summary: str
    risk: str  # low | medium | high
    parse: Callable[[dict[str, Any]], BrowserCommand]
    # True → runs_off_ui_thread prefix / membership (like emulator.*)
    off_ui: bool = True

def command_specs() -> tuple[CommandSpec, ...]:
    raise NotImplementedError("not implemented")
    # TODO: return Navigate, Reload, History, Search, Click, Type, Scroll, Snapshot specs

def parse_command(args: dict[str, Any]) -> BrowserCommand:
    raise NotImplementedError("not implemented")
    # TODO: read args["command"] → dispatch to CommandSpec.parse; validate at boundary

def control_action_names() -> tuple[str, ...]:
    """Derived: ('browser.invoke',) only — or per-kind aliases derived from specs."""
    raise NotImplementedError("not implemented")
```

```python
# iris/browser/session.py
from __future__ import annotations
import threading
from iris.browser.types import BrowserCommand, BrowserResult, BrowserSnapshot

class BrowserSession:
    """Deep module: owns readiness, history flags, scroll, last error, panel lifetime.

    Public surface intentionally small: execute + snapshot + ensure_visible.
    Driver and QWebEngine types stay private.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snap: BrowserSnapshot | None = None
        self._driver = None  # private PageDriver; created lazily on UI thread
        raise NotImplementedError("not implemented")

    def snapshot(self) -> BrowserSnapshot:
        raise NotImplementedError("not implemented")

    def ensure_visible(self) -> None:
        """Show/focus the Iris browser panel (lazy QWebEngine create)."""
        raise NotImplementedError("not implemented")
        # TODO: ensure_qt_webengine_ready already called at app start;
        #       marshal panel create to UI thread; never block HTTP worker on show()

    def execute(self, cmd: BrowserCommand) -> BrowserResult:
        raise NotImplementedError("not implemented")
        # TODO:
        # 1. acquire per-session lock (one writer)
        # 2. ensure_visible if agent/human needs the surface
        # 3. dispatch on cmd.kind → driver method (UI marshal for WebEngine calls)
        # 4. wait for load/settle with timeout off UI thread (QEventLoop forbidden here)
        # 5. refresh snapshot from driver; return BrowserResult
        # Idempotent: Navigate to same URL while COMPLETE → snapshot only;
        #             HistoryStep when !can_go_* → ok=False, unchanged snap

def get_browser_session() -> BrowserSession:
    """Process-wide singleton. Two actors serialize through session lock."""
    raise NotImplementedError("not implemented")
```

```python
# iris/browser/_driver.py  (PRIVATE — not imported outside iris.browser)
from __future__ import annotations
from typing import Protocol
from iris.browser.types import Locator, BrowserSnapshot

class PageDriver(Protocol):
    def read_snapshot(self) -> BrowserSnapshot: ...
    def navigate(self, url: str) -> None: ...
    def reload(self) -> None: ...
    def history_step(self, delta: int) -> None: ...
    def click(self, target: Locator) -> None: ...
    def type_text(self, target: Locator, text: str, *, clear: bool) -> None: ...
    def scroll_by(self, dx: int, dy: int) -> None: ...

class WebEnginePageDriver:
    """QWebEngineView + QWebChannel bridge. Not part of public API."""

    def __init__(self, view: object) -> None:
        raise NotImplementedError("not implemented")

    def read_snapshot(self) -> BrowserSnapshot:
        raise NotImplementedError("not implemented")

    def navigate(self, url: str) -> None:
        raise NotImplementedError("not implemented")
        # TODO: view.load(QUrl); completion via loadFinished signal → Future

    def reload(self) -> None:
        raise NotImplementedError("not implemented")

    def history_step(self, delta: int) -> None:
        raise NotImplementedError("not implemented")
        # TODO: history().back()/forward(); snapshot derives can_go_*

    def click(self, target: Locator) -> None:
        raise NotImplementedError("not implemented")
        # TODO: run injected JS locator resolve + element.click(); raise if missing

    def type_text(self, target: Locator, text: str, *, clear: bool) -> None:
        raise NotImplementedError("not implemented")

    def scroll_by(self, dx: int, dy: int) -> None:
        raise NotImplementedError("not implemented")
```

---

## Module map

```text
iris/browser/
  __init__.py          # exports: get_browser_session, BrowserSession, types, parse_command
  types.py             # Snapshot, Commands, Locator, BrowserResult  (domain only)
  registry.py          # CommandSpec table — single list; Control Surface derives from it
  session.py           # BrowserSession deep module
  search.py            # query → search engine URL (pure function)
  _driver.py           # PageDriver + WebEnginePageDriver (private)
  _bridge.js           # injected locator helpers (private asset)

iris/ui/browser/
  panel.py             # BrowserPanel: URL bar, back/forward/reload, embeds view
  host.py              # BrowserHost protocol for control_actions

iris/ui/control_actions/
  browser.py           # register_browser_actions → browser.invoke (+ optional aliases)

iris/system/control_surface.py
  # extend _OFF_UI_PREFIXES with "browser."  (like emulator.)

integrations/ (optional, later)
  # NO Theia browser tab in v1 — human convenience tab is out of scope for this candidate
  # Keeps sync_workspace_build out of the critical path

tests/browser/
  test_browser_session_unit.py    # command parse, idempotent navigate, history edges
  test_browser_scenarios.py       # three user scenarios (Qt offscreen or recorded driver)
  test_browser_registry_sync.py   # ActionSpec names == command_specs() kinds (fail build)
```

Data flow (≤3 hops):

```text
Hermes iris_invoke
  → ControlSurface / ActionRegistry [browser.invoke]
    → BrowserSession.execute(BrowserCommand)
      → WebEnginePageDriver (private)
        → QWebEngineView (user-visible)

Human toolbar
  → BrowserSession.execute(BrowserCommand)
      → same driver / same view
```

---

## Control Surface signatures

```python
# iris/ui/control_actions/browser.py

def register_browser_actions(window: BrowserHost, reg: ActionRegistry) -> None:
    raise NotImplementedError("not implemented")
    # TODO:
    # reg.register(ActionSpec("browser.invoke", "...", risk="medium"), handle)
    # Optional derived aliases: browser.navigate, browser.click, ... from command_specs()
    # but aliases MUST call the same parse_command → session.execute path (one way)


# iris/ui/control_actions/hosts.py — BrowserHost

class BrowserHost(Protocol):
    def browser_session(self) -> BrowserSession: ...
```

```python
# iris/browser/search.py

def search_url(query: str, *, engine: str = "web") -> str:
    raise NotImplementedError("not implemented")
    # TODO: pure; default DuckDuckGo or configured engine; no network I/O here
```

---

## Threading / Qt constraints (encoded in session, not callers)

| Rule | Where enforced |
|------|----------------|
| `ensure_qt_webengine_ready` before `QApplication` | app bootstrap (existing); session refuses create if not ready |
| Never block UI thread on load | `execute` runs on HTTP worker; UI marshals only short slot work |
| Lazy view create | `ensure_visible` |
| Companion / frameless | panel is Iris workspace page, not a child HWND of IDE Theia view |
| One writer | `BrowserSession._lock` |

---

## Verifiable tests for three scenarios

| Scenario | Commands | Assertions |
|----------|----------|------------|
| YouTube IU night letter | `Search` → `Click` | snapshot URL/title relates to IU/night letter; panel URL matches snapshot |
| Open React docs | `Navigate("https://react.dev")` | host `react.dev`, `ready==COMPLETE` |
| Scroll current page | `Navigate` + `Scroll` | `scroll_y` increases; same URL |

Fake `PageDriver` for unit tests; one integration module marked `@pytest.mark.webengine` for real Chromium.

---

## Red-flag screen (self-check)

| Flag | Status |
|------|--------|
| Shallow module | Pass — callers use `execute` + `snapshot`; policy/settle/locator inside session |
| Information leakage | Pass — no QWebEngine/QUrl on public types; wire dicts parsed at boundary |
| Temporal decomposition | Pass — not load/validate/save modules; knowledge lives in session + registry |
| Pass-through method | Pass — control handler adds parse + result shaping; session owns work |
| Split ownership | Pass — only session writes snapshot; panel reads |
| Two ways to do one task | Pass — human + agent both `execute`; aliases share path |
| Importable internals | Pass — `_driver.py` / `_bridge.js` underscore-private |
| Hand-synced list | Pass — ActionSpecs derived from `command_specs()`; sync test fails CI |
