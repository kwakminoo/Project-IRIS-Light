# Rejected shapes (candidate 1)

Whole shapes this runner considered. Not other arena candidates.

## Landmark patch

Keep `Landmark`, append `ref` and `body` fields, add `extract` to `command_specs`, sleep longer after click, add a news sentence to teaching.

Lost because it is a patch list. Mid-loop `to_control_dict` would still publish title and names next to `ok`. Hermes would still be taught `by=text` and `ref` together (two ways to click). `classify_turn("뉴스")` would still steal the turn. The type would still say the page is a media snapshot with leftover names.

## Observe / act / extract split

Three commands that match Stagehand. `observe` returns actions. `act` takes one. `extract` takes a schema.

Lost because Hermes is already the planner. A second observe model call spends local tokens to produce a selector the bridge already has. Schema extract pulls Pydantic into the command bus. Callers would coordinate three verbs to read a headline. Interface gets wider. Capability per verb gets shallower.

## Wait verb plus current click

Add `browser.wait` (`text` or `load`). Leave click as 0.1s.

Lost because the measured miss is Python returning before navigation, not Hermes forgetting a wait. A wait verb is a second way to settle. Teaching would have to say "always wait after click". Execute should settle. Per laziness, no extra verb.

## Inner Python loop

`BrowserSession.run_read(goal)` that clicks the first result and extracts, then returns one blob to Hermes.

Lost because it is a small `Agent.run`. Grounding forbids a second planner. News sites disagree on "first result". Hermes must pick the ref it can see.

## Dual locators on the wire

Keep `by=text|role|css` and add `ref`.

Lost. Two ways to do one click. An agent copies whichever SKILL row it opens. Refs then rot. Wire click is `ref` only. Driver CSS stays inside `_play_first_result`.

## Snapshot dumps the full article every time

Skip `extract`. Put body in every packed observation.

Lost on local-model tokens. Search result pages would ship tens of kilobytes per click. Excerpt (800) plus on-demand extract (4000/8000) is the budget split.

## Keep `today` and skip SerpAPI only when Hermes is online

`classify_turn` still returns `"today"` for 뉴스. MainWindow skips `search_today` if `_hermes_online`.

Lost. The kind still means "facts search". Offline Ollama would keep the steal. A browse ask is a page job even when the gateway is down. `TurnKind.BROWSE` vs `FACTS` names that. Weather stays FACTS.

## Playwright or CDP sidecar

Copy Playwright MCP as a process.

Lost unless live QWebEngine extract plus refs fail the predicate. The command bus already has the verbs. The gap is the document index and the steal, not a missing Chromium.

## Screenshots as the read channel

Lost. Grounding. Public MCP docs treat screenshots as layout, not the click channel. Vision tokens are wrong for the shipped local model.

## Tabs command

Lost. One `QWebEngineView` is reparented. `tab_index` is chrome. A tabs verb would pretend there is a tab runtime Hermes owns.
