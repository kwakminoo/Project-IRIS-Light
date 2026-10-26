# Synthesized sketch. IRIS browser agent

Base: candidate-1 (generation-stamped PageIndex, extract, packer-only Hermes read).
Cross-judge [Arena cross-judge](f6dfb647-0630-4ce0-a0ce-1587899c2a3c): 28 vs 24, pick C1.
Parent scores: 28 vs 25, same C1 win, then leaned C2 if the packer and gen refs were grafted in.
That lean inverts the graft. Packer and `g{gen}e{n}` are the load-bearing invariants. They stay the base.

## Grafts from candidate-2

1. Viewport-first node ranking, then `article`/`main`, then document order.
2. Typed `command_recipes()` with a per-recipe `success` field. YouTube `media.playing` is that recipe only.
3. Tighter browse regex: `뉴스|속보|논문|arxiv`. Keep `today` for weather/stocks. Do not classify `열어줘` as browse.

## Rejected from candidate-2

- Unwrapped `to_control_dict` next to `ok`
- `n0` refs without generation
- Wire `Locator` union (`by=text|css|role`) beside `by=ref`
- 2500-char prose on every snapshot
- 12s click timeout separate from navigate `loadFinished`

## Domain

Hermes plans through `iris_invoke`. One `QWebEngineView`. `command_specs()` is the verb list. Page strings are untrusted. Click on the wire is `ByRef` only. Driver CSS locators stay for YouTube play internals.

```text
classify_turn
  browse  → no today_search → Hermes iris_invoke
  today   → weather/stocks may SerpAPI
  stored / action / other unchanged

iris_invoke browser.*
  parse_command
  HUD looks_sensitive_browser_act (ignore args.confirm)
  BrowserSession.execute
    settle_after_act on click/type/scroll/history
    stamp gen, rewrite node.ref = g{gen}e{index}
  pack_hermes_result  ← only Hermes read of the page
```

News: search or navigate → click `{ref}` → extract `{scope:article}` → cite PAGE TEXT plus trusted url.
Paper: same. Empty extract is a miss, not a figure claim.
YouTube: `browser.search {engine:youtube, play:true}`. Success is `playing=true` on that recipe.
Weather: not a browser action.

## Types (fill-in)

- `PageNode(ref, role, name, interactive)`
- `PageRef` = `g{gen}e{n}`. Stale gen → `ok=false`, `detail=stale_ref`
- `Click`/`TypeText`.target = `ByRef`
- `Extract(scope=article|document, ref=None, max_chars)`
- `BrowserSnapshot.nodes` + `excerpt` + `gen`. `Landmark` deleted
- `BrowserResult.read_text`
- `TurnKind` str enum: browse, today, stored, action, other
- Caps: NODE 40, NAME 80, EXCERPT 800, EXTRACT default 4000 max 8000
- `pack_hermes_result` keys: ok, command_kind, detail, trusted, page_text, url, phase, playing, gen
- Trusted: phase, playing, last_*, url, gen. Never title, names, excerpt, extract
- PAGE TEXT: title, `g4e0 link Name`, excerpt=, extract= if present
- GUI `to_gui_dict` / `iris_get_state` stay chrome. Hermes is taught `page_text`

## Settle

Same `loadFinished` family as navigate (45s) if the click started a load. Else quiet 0.3s. No `wait` verb. No 0.1s return.

## Teaching / SKILL

Derived from `command_specs()` + `command_recipes()`. `_check_intent.py` fails if a spec name, recipe `when`, or recipe `control_names` is missing from teaching or SKILL. Click rows are `{ref}`. Extract row exists. No `by=text`. No global "success is media.playing".

## Verification of this sketch

- One planner. One view. One packer. One click channel. One node list.
- News cannot become SerpAPI `search_failure_reply`.
- Stale refs fail closed because gen is inside the ref.
- Viewport ranking is inside the bridge, not a second verb.
- Playwright stays out until live QWebEngine refs+body fail the ten-utterance predicate.
