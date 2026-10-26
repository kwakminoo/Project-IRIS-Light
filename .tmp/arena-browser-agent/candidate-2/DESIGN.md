# DESIGN. Page ledger plus browse kind (candidate 2)

Organizing structure. The session owns one current `PageView`. Every command reduces that view. Reading is a field on the view, not a thirteenth verb. Chat routing grows a `browse` kind so "뉴스 보여줘" reaches Hermes instead of SerpAPI.

Hermes stays the planner through `iris_invoke`. One `QWebEngineView`. One `BrowserSession`. Dedicated and IDE-internal still reparent that view. `command_specs()` stays the only verb list. Teaching and `iris-browser/SKILL.md` derive from that list plus `command_recipes()`.

Article text and click targets live on the same view the driver already returns. A new extract verb is not the structure.

---

## Usage (caller's view)

### README

The user asks to see news, open a paper, or play YouTube. Iris does not regex the sentence into a browser command. `classify_turn` only decides optional grounding. Hermes calls `iris_invoke`. Each result already contains the next page view. The model cites `PAGE TEXT`. It does not invent body from a title.

```text
News, no SerpAPI key
  "최신 뉴스 보여줘"
    classify_turn → browse
    PastChatsWorker does not call today_search
    Hermes POST teaching includes the news recipe
    → iris_invoke browser.search {query, engine:google|web}
    → PAGE TEXT lists n0..nK links plus a capped body
    → iris_invoke browser.click {by:ref, ref:n3}
    → session settles (loadFinished if the click navigated)
    → PAGE TEXT has the article. Reply cites that body and the url.

News on a named site
  "최신 뉴스 네이버에서 켜줘"
    classify_turn → browse
    → iris_invoke browser.navigate {url:"https://news.naver.com"}
    → click a ref from PAGE TEXT. Same settle. Same cite.

Paper
  "이 논문 열어줘" with a URL, or search then click
    → browser.navigate or browser.search then browser.click
    → cite PAGE TEXT. If body is empty, last_detail says so.
    → do not claim figures or PDF layout were read.

YouTube (unchanged one-shot)
  "아무 노래나 유튜브에서 틀어줘"
    classify_turn → other
    → iris_invoke browser.search {engine:youtube, play:true}
    → success is media.playing. Do not claim speakers.
    → do not claim the video was analyzed from title or description.

Weather question (not a page job)
  "오늘 날씨 어때"
    classify_turn → today
    today_search may attach SerpAPI evidence
    teaching still lists this phrase as not a browser action
```

Sensitive send or purchase still hits the existing HUD. The model cannot pass `args.confirm`. Catalog `confirm_required` stays false for browser actions.

### Call site 1. Hermes MCP, news then click then cite

```python
# integrations/hermes-skills/iris-control/iris-browser/SKILL.md
# derived from command_specs() + command_recipes(), asserted by _check_intent.py
#
# iris/mcp/iris_control_stdio.py  (unchanged hop)
# iris/ui/control_actions/browser.py  _handle
# iris/ui/window/main_window.py  _chat_messages_with_project_context

# Turn 1 tool call (Hermes inner MCP loop, one SSE may contain many)
iris_invoke(
    action="browser.search",
    args={"query": "한국 주요 뉴스", "engine": "google"},
)
# Control Surface returns BrowserResult.to_control_dict()
#   ok, url, nodes=[{ref, role, name, href}], prose, prose_truncated
# Next Hermes POST (and this tool JSON) also carry packed strings
#   trusted: phase, playing, last_action, last_ok, last_detail, url, view_seq, prose_truncated
#   PAGE TEXT: title, "n3 link …", then "body:" + capped prose

iris_invoke(
    action="browser.click",
    args={"by": "ref", "ref": "n3"},
)
# Stale ref (not in the current view) → ok=false, detail="stale ref n3; snapshot first"
# Click that follows a link waits for loadFinished, then a fresh view.
# Hermes cites PAGE TEXT. It does not claim the article from the search-result title.
```

### Call site 2. Python execute, same session the GUI shows

```python
from iris.browser.registry import parse_command
from iris.browser.session import get_browser_session
from iris.browser.observation import pack_browser_observation

session = get_browser_session()
cmd = parse_command(
    {"action": "browser.click", "by": "ref", "ref": "n3"}
)
result = session.execute(cmd)
assert result.snapshot.nodes  # refs valid only until the next mutating command
trusted, page_text = pack_browser_observation(session)
# packer is a pure formatter. It does not scrape. It does not invoke.

# Human chrome still uses execute. Actor.HUMAN skips HUD.
session.execute(Navigate(url=parse_page_url("https://news.naver.com"), source=Actor.HUMAN))
```

Driver internals for YouTube `Search(play=True)` still click CSS locators. That path never goes through `by=ref`. Hermes teaching lists only ref for click and type.

### Call site 3. Turn kind, the news steal

```python
# iris/knowledge/answer_grounding.py
# iris/ui/window/main_window.py  _with_past_chats
# iris/ui/workers/past_chats_worker.py

from iris.knowledge.answer_grounding import classify_turn

assert classify_turn("최신 뉴스 보여줘") == "browse"
assert classify_turn("최신 뉴스 네이버에서 켜줘") == "browse"
assert classify_turn("오늘 뉴스 3개") == "browse"
assert classify_turn("오늘 날씨 알려줘") == "today"
assert classify_turn("주가 알려줘") == "today"

# _with_past_chats
kind = classify_turn(text)
search_today = kind == "today"  # browse does not run today_search
# SerpAPI miss must not become the assistant's only context for a browse turn.
# Weather today_search failure may still attach search_failure_reply.
```

Checks that must stay green before live Hermes.

```python
# iris/browser/_check_intent.py  (extend, do not replace intercept assertions)

def main() -> int:
    teach = browser_teaching_block()
    for spec in command_specs():
        assert spec.control_name in teach
    for recipe in command_recipes():
        assert recipe.when in teach
        for name in recipe.control_names:
            assert name in teach
    skill = Path("integrations/hermes-skills/iris-control/iris-browser/SKILL.md").read_text()
    for spec in command_specs():
        assert spec.control_name in skill
    assert "extract" not in {s.kind for s in command_specs()}
    assert "browser.extract" not in teach
    assert classify_turn("최신 뉴스 보여줘") == "browse"
    # "오늘 날씨 어때" remains in the not-a-browser-action list
    return 0
```

---

## Shape

```text
UserTurn
  → classify_turn                    # browse | today | stored | action | other
  → PastChatsWorker(search_today iff today)
  → HermesChatWorker POST
      teaching ← command_specs + command_recipes
      trusted + PAGE TEXT ← pack_browser_observation(session)
      → MCP iris_invoke browser.*
          → parse_command            # wire ends here
          → looks_sensitive_browser_act + HUD
          → BrowserSession.execute
              → PageDriver click/type/navigate
              → settle after click/type
              → read_snapshot → PageView (nodes+prose)
              → publish. last_result is this view
```

Three hops after MCP. `iris_invoke` calls `_handle`, which calls `session.execute`. No Python `Agent.run`. No Playwright process.

**Invariants in types.**

1. Interactive targets are `Node.ref` values on the current `PageView`. A ref that is missing is a failed click, not a CSS guess. `per model-the-domain`
2. Title, node names, hrefs, and prose are untrusted. The packer wraps them. Trusted fields stay Iris-owned (`phase`, `playing`, `last_*`, `url`, `view_seq`, `prose_truncated`). `per boundary-discipline`
3. `ByRef` is the Hermes locator. `ByCss` / `ByText` / `ByRole` remain for Python helpers such as `_play_first_result`. Teaching lists only `by=ref`. `per laziness-protocol`
4. Click and type are not finished at `el.click()`. The driver settles. Hermes has no `wait` verb. `per interface depth, complexity in the callee`
5. `command_specs()` is the verb list. Recipes are teaching rows, not verbs. `_check_intent.py` fails if SKILL or teaching omit a spec name. `per encode-lessons-in-structure`
6. `classify_turn == "browse"` never calls `today_search`. News is a page job. Weather stays `"today"`. `per redesign-from-first-principles`

**What the public interface hides.**

Callers see the same `iris_invoke` names, plus `by=ref` on click and type, plus a `browse` kind from `classify_turn`. Hidden behind `execute` and `pack_browser_observation`: viewport-first node ranking, article/main/PDF `innerText`, 2500-char prose cap, ref map in `_bridge.js`, loadFinished-or-500ms settle, stale-ref detail, HUD token scan including the resolved node name.

Callers still choose the next verb. The loop stays Hermes. That is required.

**What this system does not do.**

- No `browser.extract`, `browser.observe`, `browser.wait`, or tabs command.
- No screenshots in the default view.
- No Playwright, CDP debug port, or second Chromium unless a live QWebEngine run proves refs+prose cannot satisfy the ten-utterance predicate.
- No regex intercept. `classify_turn` is grounding kind, not a command compiler.
- No honor of `args.confirm`.
- No claim of video analysis from title or description.
- No iframe merge. Nodes are the main frame.

---

## Types

Fill-in replaces `raise NotImplementedError`. Existing `BrowserCommand` kinds stay. `Landmark` is deleted. `BrowserSnapshot` carries `nodes` and `prose` instead of nameless landmarks.

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Union

PROSE_CAP = 2500
NODE_CAP = 40
SETTLE_MS = 500
NAV_SETTLE_S = 12.0


@dataclass(frozen=True)
class Node:
    """Interactive or heading target in the current view. ref is snapshot-local."""

    ref: str  # "n0" .. "n39"
    role: str
    name: str
    bbox: tuple[int, int, int, int] | None = None
    href: str | None = None


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
    nodes: tuple[Node, ...] = ()
    prose: str = ""
    prose_truncated: bool = False
    view_seq: int = 0
    mini_player: bool = False
    media: MediaState | None = None
    tab_index: int = 0
    tab_count: int = 1
    target_id: str = ""

    def to_control_dict(self) -> dict[str, Any]:
        raise NotImplementedError  # include nodes[{ref,role,name,href,bbox}], prose, prose_truncated, view_seq


@dataclass(frozen=True)
class ByRef:
    ref: str


Locator = Union[ByCss, ByText, ByRole, ByRef]


@dataclass(frozen=True)
class PackedBrowserObservation:
    url: str
    title: str
    phase: str
    playing: bool
    last_action: str
    last_ok: bool | None
    last_detail: str
    view_seq: int
    prose_truncated: bool
    node_lines: tuple[str, ...]  # "n3 link headline"
    prose: str

    def trusted_block(self) -> str:
        raise NotImplementedError
        # TODO: Iris-owned lines only. url stays. title/prose/names stay out.

    def page_text_block(self) -> str:
        raise NotImplementedError
        # TODO: PAGE_TEXT_BEGIN, title, node_lines, "body:", capped prose, PAGE_TEXT_END


@dataclass(frozen=True)
class Recipe:
    when: str  # "news", "paper", "youtube_play", "not_browser"
    text: str
    control_names: tuple[str, ...]
    success: str  # "page_text" | "media.playing" | "none"


def command_recipes() -> tuple[Recipe, ...]:
    raise NotImplementedError
    # TODO: news = search then click ref, cite PAGE TEXT
    # TODO: paper = navigate or search then click, cite PAGE TEXT, no figure claims
    # TODO: youtube_play = search engine=youtube play=true, success media.playing
    # TODO: not_browser = the four veto chats including 오늘 날씨 어때


def browser_teaching_block() -> str:
    raise NotImplementedError
    # TODO: join spec.control_name then each recipe.text and recipe.success
    # TODO: PAGE TEXT untrusted. No Hermes browser_*. HUD for send/purchase.
    # TODO: no global "success is media.playing" line. That line is youtube_play only.


def pack_browser_observation(session: Any) -> tuple[str, str]:
    raise NotImplementedError  # format snapshot.nodes and snapshot.prose. No Qt.


def classify_turn(text: str) -> str:
    raise NotImplementedError
    # TODO: 뉴스|속보|논문|arxiv → browse (unless _NOT_TODAY)
    # TODO: 날씨|기온|미세먼지|환율|주가|시세|코스피|코스닥|비트코인|경기 결과|스코어 → today
    # TODO: stored / action / other unchanged
```

### Parse and result

```python
def _parse_locator(args: dict[str, Any]) -> Locator:
    raise NotImplementedError
    # TODO: by=ref or args["ref"] → ByRef(ref)
    # TODO: existing css/text/role branches stay for Python helpers and old callers


def parse_command(args: dict[str, Any]) -> BrowserCommand:
    """Wire dict → BrowserCommand. Validation only at this boundary."""
    raise NotImplementedError


class BrowserResult:
    def to_control_dict(self) -> dict[str, Any]:
        raise NotImplementedError  # snapshot.to_control_dict plus ok, command_kind, detail
```

`Click` and `TypeText` keep `target: Locator`. No new command dataclass.

### Session and driver

```python
class BrowserSession:
    def execute(self, cmd: BrowserCommand) -> BrowserResult:
        raise NotImplementedError
        # TODO: Click/TypeText with ByRef. Resolve against current snapshot.nodes.
        # TODO: missing ref → BrowserResult(False, kind, snap, detail="stale ref …; snapshot first")
        # TODO: after Click and TypeText, driver.settle() then read_snapshot
        # TODO: increment view_seq on every published snapshot
        # TODO: YouTube Search(play=True) unchanged, still CSS internals

    def snapshot(self) -> BrowserSnapshot:
        raise NotImplementedError


class PageDriver:  # Protocol
    def read_snapshot(self) -> BrowserSnapshot: ...
    def settle(self) -> None: ...
    def click(self, target: Locator) -> None: ...
    def type_text(self, target: Locator, text: str, *, clear: bool) -> None: ...
    # navigate/reload already wait loadFinished


class WebEnginePageDriver:
    def settle(self) -> None:
        raise NotImplementedError
        # TODO: if loadStarted since the last click/type, wait loadFinished up to NAV_SETTLE_S
        # TODO: else sleep SETTLE_MS. Idempotent if called twice.

    def click(self, target: Locator) -> None:
        raise NotImplementedError
        # TODO: ByRef payload {kind:"ref", ref}. JS uses the map from the last snapshot()
        # TODO: do not rebuild the map before click. Rebuilding would renumber refs.

    def read_snapshot(self) -> BrowserSnapshot:
        raise NotImplementedError
        # TODO: JS snapshot() returns nodes+prose. Cap prose in Python to PROSE_CAP.
```

### Bridge (page, untrusted)

```javascript
// iris/browser/_bridge.js  window.__irisBrowser
//
// snapshot() {
//   TODO: collect interactive nodes, viewport first, then inside article|main, cap NODE_CAP
//   TODO: assign ref n0..nK and keep an array of elements for click({kind:"ref"})
//   TODO: prose = innerText of article|[role=main]|main, else body, whitespace-collapsed
//   TODO: headings h1/h2 may appear as nodes so Hermes can see section names
// }
// click(target) {
//   TODO: kind==="ref" → element from last snapshot map. Missing → {ok:false, error:"stale ref"}
// }
```

Why viewport-first. Naver and Google put chrome links before headlines in document order. The current 40-name list is that chrome. Hermes cannot choose a story.

### HUD

```python
def looks_sensitive_browser_act(action: str, args: dict[str, Any], snapshot: BrowserSnapshot) -> bool:
    raise NotImplementedError
    # TODO: if args has ref, include that node's name from snapshot.nodes in the scan blob
    # TODO: still ignore Actor.HUMAN and _NEVER_SENSITIVE. Do not read args.confirm.
```

### Worker

```python
# iris/ui/workers/past_chats_worker.py
# search_today remains a constructor flag. MainWindow passes kind == "today" only.
# Early return on SerpAPI failure stays for today. Browse never sets the flag.
```

---

## Module map

| Module | Owns | Does not own |
| --- | --- | --- |
| `iris/browser/types.py` | `Node`, `ByRef`, snapshot fields `nodes`/`prose`/`view_seq` | HUD, teaching text |
| `iris/browser/registry.py` | `command_specs`, `command_recipes`, `parse_command`, `ByRef` parse | page scrape |
| `iris/browser/observation.py` | packer, teaching from specs+recipes, HUD token scan | execute |
| `iris/browser/_bridge.js` | ref map, node ranking, prose `innerText` | Python types |
| `iris/browser/_driver.py` | `settle`, locator payload including ref, snapshot parse | recipes |
| `iris/browser/session.py` | stale-ref fail, publish view_seq, one session | SerpAPI |
| `iris/knowledge/answer_grounding.py` | `browse` vs `today` | browser verbs |
| `iris/ui/workers/past_chats_worker.py` | `today_search` only when asked | page driving |
| `iris/ui/window/main_window.py` | pass `search_today=(kind=="today")` | node scrape |
| `iris/ui/control_actions/browser.py` | parse → HUD → execute (unchanged hop) | new verbs |
| `iris/system/hermes_memory_nudge.py` | inserts `browser_teaching_block()` | recipes content |
| `integrations/.../iris-browser/SKILL.md` | human-readable table. Must match specs+recipes | runtime |
| `iris/browser/_check_intent.py` | intercept gone, teaching/SKILL drift, browse kind | live gateway |
| `tests/browser/*` | settle, stale ref, prose wrap, classify browse | Playwright |

Do not add `iris/browser/extract.py`, `observe.py`, or `agent.py`.

---

## Red-flag screen

- Shallow module. Callers do not orchestrate scrape then extract then wait. They call `execute` and read the view.
- Information leakage. Wire dicts stop at `parse_command`. DOM nodes stop at `_bridge.js`. Hermes sees domain `ref` and wrapped text.
- Temporal decomposition. No observe/act/extract packages named after steps.
- Pass-through. `_handle` still adds HUD policy. Do not add a forwarding `read()` on the session.
- Split ownership. Only `BrowserSession` writes the current view. The packer reads it.
- Two ways. Hermes teaching lists one click form (`by=ref`). CSS/text/role stay off that list. YouTube play stays a search flag, not a second click recipe.
- Importable internals. `_bridge.js` and `_driver.py` stay private as they are today.
- Hand-synced list. Verb names come from `command_specs()`. Teaching, SKILL, and MCP checks must include those names or fail.
