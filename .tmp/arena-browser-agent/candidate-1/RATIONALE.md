# Rationale. Generation-stamped page index

## Problem

Hermes already drives one QWebEngine through `iris_invoke` into `BrowserSession.execute`. The command bus has click, type, search, snapshot. Live logs still never show those clicks. Snapshot sends forty landmark names and no article body. Click sleeps 0.1s and does not wait for navigation. `classify_turn` maps `뉴스` to `today`, and `PastChatsWorker.today_search` injects a SerpAPI failure before Hermes can invoke. Teaching says success is `media.playing` and treats weather-like questions as not a browser job. The next step must read a page and choose a click on this process, without a second planner or a second Chromium.

Load-bearing constraints from grounding. Hermes stays the planner. One session, one view. `command_specs()` is the verb list. Page strings untrusted. HUD for send/purchase. Local-model tokens, no screenshots by default. Do not claim video analysis from title. Playwright/CDP only if this bus cannot carry extract plus refs.

## Usage (caller's view)

Hermes copies `ref` values from the packed `page_text` of the last `iris_invoke` (or the turn-start POST, which uses the same packer). Search or navigate, click `g4e3`, extract article, cite extract plus trusted `url`. Python tests call `parse_command`, then `execute`, then `pack_hermes_result`. `classify_turn("최신 뉴스 보여줘")` is `TurnKind.BROWSE`, so the worker never runs `today_search`. Full call sites are in `DESIGN.md`.

## Shape

The page is a `PageIndex` (nodes + excerpt + gen), not a media player with leftover names. Per `principle-model-the-domain`. Per `principle-redesign-from-first-principles` this is the day-one type if news and papers had been in scope with YouTube.

`Click`/`TypeText` take `ByRef` only. Refs embed gen (`g{gen}e{n}`), so a copied stale id fails closed. Driver `ByCss`/`ByText` remain for YouTube play internals and are not taught. One targeting channel on the wire.

Settle is execute policy for click/type/scroll/history, sharing the navigate `loadFinished` wait when a load starts. Not a `wait` verb. Per `principle-laziness-protocol`.

`Extract` is a scoped read of the same document. Snapshot excerpt is 800 characters so the model can skip extract on a search page. Extract default 4000, max 8000. No screenshot path.

The packer is the Hermes boundary. Per `principle-boundary-discipline`. Turn-start POST and mid-loop tool JSON both call it. Trusted block is Iris-owned (`phase`, `playing`, `last_*`, `url`, `gen`). Title, node names, excerpt, extract body stay in `BEGIN PAGE TEXT`. GUI `to_gui_dict` / `iris_get_state` stay a separate dict so chrome fields do not leak into the model as instructions.

`TurnKind.BROWSE` vs `FACTS` stops the news steal without deleting SerpAPI for weather. `command_specs()` remains the only verb list. Teaching and SKILL are checked against it.

Interface depth. Callers import `command_specs`, `parse_command`, `execute`, `pack_hermes_result`, and `classify_turn`. Article CSS, gen stamp, stale-ref, settle, HUD tokens, and recipe text stay inside those functions. Callers do not orchestrate snapshot, wait, and read as three policies.

## Synthesis decision

parent fills after arena

## Tradeoffs accepted

- We accept a new `browser.extract` verb in exchange for keeping snapshot cheap enough for a local model. Dumping full body on every act would blow the token budget.
- We accept deleting `Landmark` and wire `by=text` click in exchange for one targeting channel. YouTube play still clicks CSS inside `_play_first_result`, not through Hermes locators.
- We accept gen bump on every published snapshot, including `browser.snapshot`, in exchange for fail-closed refs. Hermes must copy refs from the last result, not from earlier in the same turn.
- We accept leaving weather on SerpAPI (`FACTS`) in exchange for not fighting the existing veto that `오늘 날씨 어때` is not a browser action.
- We accept QWebEngine JS click without Playwright actionability in exchange for staying on the visible view. If live extract+refs fail the predicate, that is the door to a sidecar, not this sketch.
- We accept not adding `browser.wait` or tabs. Multi-step is multiple `iris_invoke`s in the Hermes MCP loop.

## Alternatives considered

Per `principle-exhaust-the-design-space`, these were whole shapes, not flavor tweaks. Detail in `REJECTED.md`.

- Enrich landmarks in place and keep `by=text` plus a body field. Lost. Two click languages, and mid-loop tool JSON would still leak unwrapped page strings. Callers would keep coordinating snapshot then guess-text-click.
- Stagehand-style observe / act / extract as three planner-facing verbs with a second model call per act. Lost. Extra inference fights local tokens and splits ownership of "what is on the page" away from `execute`.
- `browser.wait` plus click-as-now. Lost. Hermes would have to remember to wait. The miss today is that Python does not wait. Encode it in execute.
- Keep `classify_turn == "today"` for 뉴스 and only change teaching. Lost. Measured 22:47 is a SerpAPI failure blob in context, not a missing recipe. Teaching cannot win while that steal runs.
- Playwright MCP sidecar. Rejected unless this bus fails live, per grounding.

## Open questions and risks

- Does QWebEngine `article`/`main` innerText cover Naver news and arXiv well enough for the ten-utterance predicate, or do we need site-specific extract CSS after the first live fail?
- Should `iris_get_state` stop returning `browser_title` so Hermes cannot treat it as a trusted read, or is chrome state allowed there because teaching points at `page_text`?
- When Hermes is offline, browse asks get no SerpAPI and no `browser.*`. Is a silent skip to the local model acceptable, or should FACTS-style search remain a fallback only in that mode?
- Followthrough cap 8 is wiki-shaped. If a news browse needs more than one SSE's MCP calls, does the gateway already loop enough, or does a live run stall after the first click?

## Next implementation step

Add `PageNode`/`ByRef`/`Extract` and a fake-driver packer test that proves extract body is only inside `page_text` and news classifies as `BROWSE`.
