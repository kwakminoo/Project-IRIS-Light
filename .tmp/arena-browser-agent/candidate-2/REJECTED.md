# Rejected shapes

Whole shapes, not flavors of the ledger.

## Add `browser.extract` on the current 12 verbs

The obvious patch. Keep landmarks as names. Add one command that returns innerText. Teaching mentions extract after navigate.

Why it lost. Callers must sequence snapshot, extract, click, extract. That is a shallow module. The today-steal still injects SerpAPI failure before Hermes runs. Click still returns before navigation. YouTube `success is media.playing` still poisons news. Playwright MCP has no dedicated extract. The snapshot is the read. IRIS should do the same on QWebEngine. Hermes would still have to learn when to extract. The session already returns a view after every command.

## Observe / act / extract command families (Stagehand, FRAME candidate B)

Three verbs or three groups. `observe` returns actions. `act` performs one. `extract` takes a schema.

Why it lost. IRIS already has act verbs. Observe is `snapshot` plus the packed view. Extract is prose on that view. Splitting them duplicates the page across modules named after execution order (temporal decomposition). Stagehand's NL `act()` also calls an extra model. That fights Hermes-as-planner. Interface grows. Capability per name shrinks.

## Playwright MCP or Chrome DevTools MCP as a process

A11y YAML refs, auto-snapshot, `browser_wait_for`. Second Chromium or a debug port on system Chrome.

Why it lost. Copy the snapshot/ref contract into `_bridge.js` first. Only if live QWebEngine refs plus body fail the ten-utterance predicate does a sidecar earn its place. The command bus already returns a snapshot on every `execute`. It can carry nodes and prose without a new process. A sidecar would hide Playwright actionability and iframe merge, and it would expose a competing MCP toolset next to `iris_invoke`.

## browser-use inner `Agent.run` with screenshots

Python owns the observe-decide-act loop. Screenshot every step. Click by index.

Why it lost. Second planner. Vision tokens on a local model. Index clicks drift after scroll. Grounding rejects this.

## Indexed landmarks without refs (`click nth=3` on the packed list)

Reuse today's `0: name` lines. Hermes echoes an integer.

Why it lost. After a settle or a scroll the integer points at a different element. Playwright and Chrome DevTools MCP both bind a snapshot-local id and fail stale. `ByRef` is that contract. An integer looks simpler and is two ways to click once `nth` on `ByText` already exists.

## Typed `UntrustedText` plus `ByLandmark(observation_id, landmark_id)` as the center (prior YouTube arena candidate 1)

Policy in NewTypes. Observation moves to `iris_get_state`. POST packer removed. ConfirmGate for HUD. No article body. No browse/today split.

Why it lost for this predicate. News fails because the turn is stolen and the view has no body, not because landmark names lack a NewType envelope. HEAD already wraps PAGE TEXT in the POST. Dual ids on every click cost local-model tokens. HUD already exists as `looks_sensitive_browser_act`. Rebuilding it does not open Naver. Keep the wrap. Put refs and prose on the view. Fix `classify_turn`.

## Snapshot modes as public options (`focus=interactive|prose|find`)

One snapshot command with a stage argument. Hermes picks a lens.

Why it lost. Public options that name internal stages. Callers learn the implementation. Always packing capped prose plus 40 nodes is one default. If tokens blow up on the live matrix, shrink the cap. Do not ask the model to choose a pipeline.

## Keep `"today"` for 뉴스 and only soften SerpAPI failure

Leave `classify_turn`. Stop early-return. Teach "if search fails, use the browser".

Why it lost. The POST still leads with "SerpApi 키가 없습니다". Teaching still says weather is not a browser action. A gemma-class model copies the failure evidence. Kind must change so the worker never calls `today_search` for a show-me-news utterance. Softening the error string is a prompt patch on a routing bug.

## Regex intercept for news only

Match `뉴스|네이버` in `_execute_user_turn_body` and call `browser.search` without Hermes.

Why it lost. `_check_intent.py` asserts intercept gone. Grounding forbids it. It cannot do multi-step papers. It would relearn the 2026-10 YouTube matcher.

## `browser.wait` as a verb Hermes must call after click

This would name the click-vs-navigation race in the verb list.

Why it lost. Every click path would need two invokes. Settle is the same policy for every caller, including YouTube internals. Put it in the driver. If 12s is wrong, change one timeout, not the skill.
