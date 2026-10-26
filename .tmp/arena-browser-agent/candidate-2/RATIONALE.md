# Rationale. Page ledger plus browse kind

## Problem

Hermes can already drive the visible QWebEngine through `iris_invoke` and `BrowserSession.execute`. Live news turns never used that path. `classify_turn("뉴스")` is `"today"`. `PastChatsWorker` then runs `today_search` (SerpAPI `google_news`). A missing key injects `search_failure_reply` into the POST. Teaching still says success is `media.playing` and lists weather as not a browser action. Snapshot landmarks are 40 nameless strings with no article body. Click sleeps 0.1s and does not wait for navigation. The model therefore refuses ("뉴스 도구가 없다") even though Google search through the same WebEngine worked at 22:26. Adding `extract()` would still leave the turn steal, the YouTube-only success line, and a click that returns before the article exists. Grounding keeps Hermes as the planner, one view, `command_specs()` as the verb list, untrusted page strings, HUD for send/purchase, no regex intercept, and no screenshots by default. Playwright is out unless this bus cannot carry refs plus body.

## Usage (caller's view)

Hermes keeps calling `iris_invoke`. After `browser.search` or `browser.navigate` it reads `PAGE TEXT` for `n3 link …` and a capped `body:`. It clicks `{by:ref, ref:n3}`. The session settles, then returns a new view. The reply cites that body and the trusted url. Python callers keep `parse_command` + `session.execute` on the same session the GUI shows. `classify_turn("최신 뉴스 보여줘")` returns `"browse"`, so `PastChatsWorker` does not run `today_search`. Weather stays `"today"`. YouTube play stays `browser.search {engine:youtube, play:true}` with success `media.playing`. Teaching and SKILL are generated from `command_specs()` plus `command_recipes()`. There is no `browser.extract`.

## Shape

The domain object is the current `PageView` (`BrowserSnapshot` with `nodes`, `prose`, `view_seq`). Commands are reducers. Playwright MCP treats a snapshot as the read channel. This design copies that contract into QWebEngine and does not copy their process. `per model-the-domain`

Validation stays at `parse_command` and the packer wrap. Inside the session, `ByRef` either hits a node or fails closed. Title, names, hrefs, and prose never enter the trusted block. `url` stays trusted as it does today. `per boundary-discipline`

Settle after click and type lives in the driver. Hermes does not learn a `wait` verb. Viewport-first ranking and article `innerText` live in `_bridge.js`. The public names barely grow (`by=ref`, `browse`). `per laziness-protocol`

`Landmark` is removed instead of grown. If refs and body had been day-one, the snapshot would have been this view. `classify_turn` splits page jobs (`뉴스|속보|논문`) from live quotes (weather, stocks, scores). `per redesign-from-first-principles`

Interface depth. One extra locator form and one extra grounding kind. Hidden work is node ranking, prose cap, settle, stale-ref, and recipe drift checks. Hermes still picks the next verb. That loop is required.

The design does not default to screenshots, merge iframes, add a second planner, or honor `args.confirm`. A video title is not content analysis.

## Synthesis decision

parent fills after arena

## Tradeoffs accepted

- We accept CSS/text/role remaining on `Locator` for YouTube internals, in exchange for not rewriting `_play_first_result`. Teaching lists only `by=ref`, so Hermes has one documented click form.
- We accept a 2500-character prose cap (and `prose_truncated` in the trusted block) in exchange for local-model token budget. Long papers need scroll plus another snapshot.
- We accept main-frame nodes only, in exchange for not opening a CDP a11y tree. Iframe-only articles will fail the live predicate and that failure is the Playwright door.
- We accept `classify_turn` still using regex for grounding kind, in exchange for not adding a new intercept. It does not emit `browser.*`.
- We accept chat news going through the WebEngine while `routine.create` may still set `search=` for scheduled facts, in exchange for leaving the routine path alone.
- We accept click on a live link not being idempotent, in exchange for correct navigation. Retry after settle uses new refs.

## Alternatives considered

- **Thirteenth verb `browser.extract`.** Callers would search, extract, then click, then extract again. That is a shallow module. It leaves the today-steal and the click race. Reading belongs on the view every command already returns.
- **Stagehand-style observe / act / extract as three command families.** The public list grows and splits ownership of one page. Hermes would coordinate stages the session can finish inside `execute`. Extra names without extra capability.
- **Playwright or Chrome DevTools MCP sidecar.** A second Chromium and a second toolset. Grounding forbids this until live refs+prose fail the predicate. The current command bus can carry nodes and body in `BrowserResult.to_control_dict`.
- **browser-use inner `Agent.run` plus screenshots.** A second planner and vision tokens. Rejected by grounding.
- **Indexed click (`n` as a raw integer with no snapshot identity).** Cheaper to type, but a scroll silently retargets the number. `ByRef` as a string from the current view fails closed instead.

## Open questions and risks

- Does QWebEngine `innerText` on `article|main` actually contain Naver and Google News bodies on the live sites in the ten-utterance matrix, or only chrome?
- For arXiv PDF in the Qt viewer, is `document.body.innerText` nonempty? If it is empty, should the reply say "no readable text" and stop, or should that measured miss open the Playwright door?
- Should "오늘 날씨 네이버에서 켜줘" stay `"today"` (weather token wins) or become `"browse"` because a site was named?
- Is 2500 characters enough for a paper abstract plus first sections, or will gemma-class models drown before they click?
- Viewport-first nodes can hide off-screen headlines. Is a follow-up `browser.scroll` then implicit new view enough, or do we need a later `query` on snapshot?
- False-positive HUD on a news headline that contains "buy". Prefer a missed HUD or a blocked click?

## Next implementation step

Extend `classify_turn` with `"browse"` and a failing `_check_intent.py` / unit test that `"최신 뉴스 보여줘"` is not `"today"` and that packed PAGE TEXT requires `n0` plus a `body:` line.
