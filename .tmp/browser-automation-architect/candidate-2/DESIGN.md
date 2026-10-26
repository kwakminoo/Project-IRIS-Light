# DESIGN — Playwright CDP on Theia-sole browser surface

Structurally distinct from a Python-QWebEngine panel: **Theia owns the only visible browser chrome and document surface**; **Playwright owns automation by CDP-attaching to that same target**; Control Surface owns the agent contract.

---

## Usage (caller's view) — write this first

### Agent / Hermes (thin MCP)

Discover and drive through existing `iris-control` only. No new MCP tool names for click/type/scroll.

```text
iris_get_state
  → browser_open: true/false
  → browser_url, browser_title, browser_phase

iris_get_catalog
  → browser.open | browser.navigate | browser.reload
  → browser.back | browser.forward
  → browser.search | browser.click | browser.type | browser.scroll
  → browser.snapshot

iris_invoke action=browser.open
iris_invoke action=browser.search args={"query":"IU night letter youtube"}
iris_invoke action=browser.click args={"by":"role","name":"IU - 밤편지"}
iris_invoke action=browser.navigate args={"url":"https://react.dev"}
iris_invoke action=browser.scroll args={"dy":800}
```

Skill routing (same split as emulator / mobile-mcp): lifecycle + Iris-visible chrome via `browser.*`; do not register a sibling Playwright MCP with dozens of tools.

### Human in IRIS IDE

File → Browser (or agent `browser.open`) opens **one** Theia tab:

- Address bar (URL)
- Reload / Back / Forward
- Live page (webview) — same document the agent drives

Typing a URL and pressing Enter, or clicking Back, goes through the same `BrowserSession` owner the agent uses (bridge → Python), so chrome and agent cannot diverge.

### Realistic call sites

**1. Control action registration (pattern: `emulator.py`)**

```python
# iris/ui/control_actions/browser.py
def register_browser_actions(window: BrowserHost, reg: ActionRegistry) -> None:
    reg.register("browser.open", ..., lambda a: window.browser_session.ensure_open())
    reg.register("browser.navigate", ..., lambda a: window.browser_session.navigate(PageUrl.parse(a["url"])))
    # ... reload / back / forward / search / click / type / scroll / snapshot
```

**2. Agent turn (Hermes → HTTP Control Surface)**

```python
# conceptual — Hermes already does this for emulator.*
result = control.invoke("browser.search", {"query": "IU 밤편지 공식 뮤직비디오"})
# result is domain snapshot dict, not Playwright Page / CDP wire
assert result["phase"] == "ready"
assert "youtube.com" in result["url"]
```

**3. Theia chrome → same owner**

```typescript
// integrations/iris-ide/.../iris-browser-widget.ts
onAddressCommit(url: string) {
  // enqueueFrontend is wrong direction for mutation ownership —
  // chrome posts bridge command; Python BrowserSession mutates; poller pushes snapshot back.
  this.poller.enqueueToPython('browser.navigate', { url });
}
```

---

## Shape

### Ownership boundary (load-bearing)

| Concern | Owner | Does not own |
|--------|--------|--------------|
| Visible tab, URL bar, nav buttons, webview document | **Theia `IrisBrowserWidget`** | Playwright process lifecycle policy |
| Navigate / click / type / scroll / search / history | **Python `BrowserSession`** (sole mutator) | Qt `QWebEngineView` for this feature |
| CDP attach, locators, waits | **private `browser_cdp` (Playwright)** | Public Control Surface API |
| Agent contract names + off-UI dispatch | **Control Surface `browser.*`** | Raw Playwright MCP tools |

Invariant: there is **one** browsing target. Playwright never launches a second Chromium window for the agent. Theia never embeds a second independent engine that agents cannot see.

### Domain state (encoded in types)

```python
# iris/system/browser_session.py  — public domain (sketch)

from enum import Enum
from typing import NewType, Literal
from dataclasses import dataclass

BrowserSessionId = NewType("BrowserSessionId", str)
PageUrl = NewType("PageUrl", str)  # only via PageUrl.parse / PageUrl.about_blank

class BrowserPhase(Enum):
    CLOSED = "closed"
    OPENING = "opening"
    READY = "ready"
    BUSY = "busy"       # in-flight navigate/click/type/scroll
    FAULTED = "faulted"

@dataclass(frozen=True)
class ScrollDelta:
    dx: int = 0
    dy: int = 0
    # constructed via ScrollDelta.page_down() / .by_pixels(dx, dy) — not raw tuples

@dataclass(frozen=True)
class TargetRef:
    """Agent-facing locator. Parsed at Control Surface boundary; never a CSS string on the wire from Hermes without strategy."""
    strategy: Literal["role", "text", "test_id", "css", "url_host"]
    value: str
    exact: bool = False

    @staticmethod
    def parse(args: dict) -> "TargetRef":
        raise NotImplementedError

@dataclass(frozen=True)
class Landmark:
    role: str
    name: str
    bbox: tuple[int, int, int, int] | None

@dataclass(frozen=True)
class BrowserSnapshot:
    session_id: BrowserSessionId
    phase: BrowserPhase
    url: PageUrl
    title: str
    can_go_back: bool
    can_go_forward: bool
    landmarks: tuple[Landmark, ...]  # bounded a11y summary for agents
    fault: str | None = None

    def to_control_dict(self) -> dict:
        """Single serializer for iris_invoke results + iris_get_state fields."""
        raise NotImplementedError

@dataclass(frozen=True)
class SearchQuery:
    text: str
    # SearchQuery.parse strips; empty → error at boundary

class BrowserSession:
    """Deep module: chrome + agent + CDP hide behind this.

    Invariants:
    - At most one live session per Iris process (session_id stable until close).
    - phase transitions are idempotent: ensure_open on READY is no-op; navigate to same url short-circuits.
    - Only this type mutates navigation/DOM; Theia chrome and MCP both call in.
    - Playwright Page / CDP session are never returned.
    """

    def ensure_open(self) -> BrowserSnapshot:
        """Open Theia browser tab + CDP-attach if needed. Idempotent."""
        raise NotImplementedError

    def close(self) -> BrowserSnapshot:
        raise NotImplementedError

    def snapshot(self) -> BrowserSnapshot:
        raise NotImplementedError

    def navigate(self, url: PageUrl) -> BrowserSnapshot:
        raise NotImplementedError

    def reload(self) -> BrowserSnapshot:
        raise NotImplementedError

    def back(self) -> BrowserSnapshot:
        raise NotImplementedError

    def forward(self) -> BrowserSnapshot:
        raise NotImplementedError

    def search(self, query: SearchQuery) -> BrowserSnapshot:
        """Policy: navigate to configured search entry URL with encoded q=; wait READY."""
        raise NotImplementedError

    def click(self, target: TargetRef) -> BrowserSnapshot:
        raise NotImplementedError

    def type_text(self, target: TargetRef, text: str, *, submit: bool = False) -> BrowserSnapshot:
        raise NotImplementedError

    def scroll(self, delta: ScrollDelta) -> BrowserSnapshot:
        raise NotImplementedError
```

Validation at boundaries (`PageUrl.parse`, `TargetRef.parse`, `SearchQuery.parse`); trust types inside `BrowserSession` and `browser_cdp` (per boundary-discipline).

### Module map

```text
iris/
  system/
    browser_session.py     # domain types + BrowserSession (public)
    browser_cdp.py         # Playwright connect_over_cdp + ops (PRIVATE — not imported by UI)
    control_surface.py     # add "browser." to _OFF_UI_PREFIXES
  ui/
    control_actions/
      browser.py           # register browser.* → BrowserSession only
      hosts.py             # BrowserHost protocol: .browser_session
    control_bindings.py    # wire register_browser_actions + state fields
  infrastructure/
    iris_ide_client.py     # bridge cmds: browserEnsureOpen, browserApplyChrome, browserCdpEndpoint
integrations/
  iris-ide/src/browser/
    iris-browser-widget.ts       # sole surface: URL + back/forward/reload + webview
    iris-browser-contribution.ts # command / tab factory
    iris-ide-bridge-poller.ts    # handle browser* cmds; publish cdp websocket URL
  hermes-skills/iris-control/
    iris-browser/SKILL.md        # routing table like iris-mobile-mcp
tests/
  test_browser_session.py        # pure phase machine + parse
  test_browser_actions_contract.py
iris/system/_check_browser_scenarios.py  # three user scenarios (verifiable)
```

Internals (`browser_cdp`, widget CDP wiring) must not be importable as a supported API from skills or random UI code — package layout + `__all__` + check that control_actions never import Playwright.

### Control Surface signatures

```python
# runs_off_ui_thread: any action starting with "browser."
# Handlers return BrowserSnapshot.to_control_dict()

browser.open      {} -> snapshot
browser.close     {} -> snapshot
browser.snapshot  {} -> snapshot
browser.navigate  {url: str} -> snapshot
browser.reload    {} -> snapshot
browser.back      {} -> snapshot
browser.forward   {} -> snapshot
browser.search    {query: str} -> snapshot
browser.click     {by: str, name|value: str, exact?: bool} -> snapshot
browser.type      {by: str, name|value: str, text: str, submit?: bool} -> snapshot
browser.scroll    {dx?: int, dy?: int} | {page: "down"|"up"} -> snapshot
```

`iris_get_state` derives `browser_*` fields from `BrowserSession.snapshot()` — single source of truth; no parallel flags in MainWindow.

### Bridge / Theia flow (short call chain)

```text
Hermes iris_invoke
  → Control Surface HTTP (worker, off-UI)
    → BrowserSession.method
      → browser_cdp (Playwright over CDP)           # mutate page
      → IrisIdeClient.browser_apply_chrome(...)     # sync URL bar / button enablement
        → IrisIdeBridgePoller
          → IrisBrowserWidget.applySnapshot(chrome) # paint chrome only; document already shared

Human chrome click
  → Widget → bridge → Control Surface browser.*
    → same BrowserSession path
```

Max three hops for readers: MCP → Session → (CDP | bridge). No separate “mirror browser” sync loop.

### OSS choice

**Playwright** (`playwright` Python package, `connect_over_cdp`).

Why this and not Puppeteer-only / selenium / raw websocket CDP:

- First-class `connect_over_cdp` to an **existing** Chromium target (Theia webview / Electron debugger URL) — matches “attach, don’t launch a second window”
- Auto-wait + role/text locators map cleanly onto `TargetRef` (deeper than raw CDP `Input.dispatchMouseEvent`)
- Same ecosystem already cited in grounding; used as sibling depth for mobile via MCP precedent, here **folded behind** `browser.*` instead of tool explosion
- Wiki-capture rejection of Playwright (QWebEngine already present) does **not** apply: this feature’s surface is Theia-internal, not a new Qt WebEngine panel

Theia side may use the webview’s `getWebContents().debugger` / CDP endpoint exposure only to hand a URL to Python — no second automation stack in TS.

### IDE-visible chrome behavior

- `browser.open` / first navigate: ensure IDE companion up if needed, open `IrisBrowserWidget` tab, expose CDP endpoint, Playwright attaches, returns snapshot
- URL bar commit → `browser.navigate`
- Reload / Back / Forward → same named actions
- Agent actions update chrome via `browserApplyChrome` snapshot push (url, can_go_back/forward) so the user watches the same tab

### Intentionally out of scope

- Python `QWebEngineView` agent panel (other candidate)
- Sibling `playwright-mcp` tool surface for Iris Hermes (two ways to click)
- Headless-only Chromium the user cannot see
- Replacing wiki / email / diagram WebEngine hosts

---

## Verifiable tests — three user scenarios

Harness: `python -m iris.system._check_browser_scenarios` (pattern: `_check_emulator_adb`, `_check_iris_ide_bridge`). Uses fixture HTML server + real Playwright against a **test Chromium** when IDE is unavailable; against live CDP endpoint when `IRIS_BROWSER_LIVE=1`.

### Scenario A — YouTube “IU night letter”

```text
given: BrowserSession closed
when:  open → search("IU 밤편지") → click(TargetRef(role, name matching IU/night letter/밤편지))
then:  snapshot.url host contains youtube.com
       snapshot.title or landmarks mention IU or 밤편지 or night letter
       phase == READY
```

Assert on domain snapshot only (not pixel OCR). Fixture mode: local page with search box + result link labelled “IU - 밤편지 (Night Letter)” → same action sequence → URL ends at `/watch?v=fixture-iu`.

### Scenario B — Open React docs

```text
when:  open → navigate(PageUrl.parse("https://react.dev"))
then:  snapshot.url host == "react.dev"
       phase == READY
       can_go_back == True after a prior page (open blank first)
```

Fixture mode: `navigate` to fixture `/react-docs` with `<title>React</title>`.

### Scenario C — Scroll current page

```text
given: page open with tall fixture (scrollHeight >> viewport)
when:  scroll(ScrollDelta.by_pixels(0, 800))
then:  snapshot succeeds phase READY
       browser_cdp test double / live evaluate records scrollY increased by ~800
```

Public test asserts via `BrowserSession` test seam `last_scroll_delta` or evaluate hook behind `browser_cdp` — not by importing Playwright in the check module.

### Contract tests (always, no network)

- `TargetRef.parse` / `PageUrl.parse` reject empty and `javascript:`
- `ensure_open` twice → same `session_id`, one bridge open call (idempotent)
- `runs_off_ui_thread("browser.click")` is True
- catalog lists exactly the `browser.*` set above (derive list from registration, don’t hand-sync)
- control_actions/browser.py AST/import check: no `playwright` import

---

## Red-flag self-screen

| Flag | Status |
|------|--------|
| Shallow module | Avoided: callers use `BrowserSession` / `iris_invoke` only; CDP waits/locators hidden |
| Information leakage | Playwright `Page`, CDP wire, Theia webview APIs stay private |
| Temporal decomposition | Not load→validate→transform modules; knowledge grouped in Session |
| Pass-through | control_actions parse args then call Session (policy at boundary), not naked forward of Playwright API |
| Split ownership | Sole mutator = Session; widget is chrome projection + document host, not a second navigator |
| Two ways | No playwright-mcp sibling for the same clicks |
| Importable internals | `browser_cdp` not part of public package surface |
| Hand-synced list | Action names one registration; catalog + skill + state fields derived or checked in `_check_*` |

---

## Next implementation step (for fill-in after synthesis)

Scaffold `BrowserSession` + `PageUrl`/`TargetRef`/`BrowserSnapshot` with `NotImplementedError` bodies and register no-op `browser.*` actions behind `runs_off_ui_thread`, then wire Theia widget CDP endpoint exposure.
