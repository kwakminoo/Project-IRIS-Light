# Phase A frame. General-purpose IRIS browser agent

## Predicate (done when this is true)

On a live Hermes + IRIS GUI run, each of the ten user utterances in the request is labeled PASS, FAIL, or SKIP, with artifacts a reviewer can rerun.

PASS requires all of:

1. `iris.log` shows the `browser.*` commands that the reply claims.
2. The visible QWebEngine URL after the turn matches those commands.
3. The assistant reply cites URLs and text that those commands actually returned. If only title and description were read, the reply does not claim the video was analyzed.
4. No `pythonw` `0xC0000409`. No assistant claim that Iris Control MCP is disconnected while `control_port` exists under `~/.iris-light`.

SKIP is allowed only when the Hermes gateway or the shipped model is down, recorded by `python -m iris.system._check_browser_hermes_play` style skip text. A skip is not a pass. Regex intercept stays gone.

Unit and integration checks that do not need the gateway must be green before live runs.

## What is already true on HEAD (measured)

- Regex intercept is deleted. `_check_intent.py` asserts `_try_local_browser_control` and `match_browser_intent` stay gone. Commit `2a0b718`.
- One process-wide `BrowserSession`. Dedicated screen and IDE-internal cover reparent the same `QWebEngineView`.
- Hermes POSTs teaching + packed observation on every turn. MCP is `iris_invoke`, not a `tools` array in the Iris HTTP body.
- `command_specs()` verbs: open, navigate, reload, back, forward, search, click, type, scroll, snapshot, mini_player, media. No extract, no PDF, no tabs command.
- `_bridge.js` landmarks are the first 40 `a, button, h1, h2, input, textarea` names. No accessibility refs. No article body.
- `pack_browser_observation` sends Iris-owned phase/playing/last_action/url, then untrusted title plus landmark names. No body text.
- Teaching is YouTube-first. "Success is media.playing." Questions including weather are taught as not a browser action.
- `browser.search` with `engine=youtube, play=true` clicks the first watch result and waits for `media.playing`. Web search only navigates to DuckDuckGo or Google.

## Failure evidence (measured tonight)

| When (KST) | User | What ran | Reply |
|---|---|---|---|
| 22:47:43 | 최신 뉴스 보여줘 | Hermes POST. No `iris.browser cmd=` | 최신 뉴스를 검색하거나 제공할 도구가 없다 |
| 22:50:11 | 최신 뉴스 네이버에서 켜줘 | Hermes POST. No `iris.browser cmd=` | 네이버에 직접 접속하는 기능이 없다 |
| 21:43:01 | 아무 노래나 유튜브에서 틀어줘 | Hermes POST. No `cmd=search` | Iris Control MCP가 응답하지 않는다 |
| 22:26:20 | head-verify script, not chat | `cmd=search` youtube play=True | `playing=True` on a watch URL |

So the WebEngine can search and play. Chat-driven Hermes often never invokes. News is refused as if tools do not exist. That matches a teaching and observation gap, not a missing Chromium.

Older chats (2026-10-19 Naver, 2026-10-21 YouTube) also show `cannot unpack non-iterable NoneType object` and "I cannot play YouTube." Those are prior incident classes. `7ec6656` waits for WebEngine create instead of a 3s timeout. Do not treat them as the current news miss unless they reproduce after the packer/teaching fix.

## Public approaches (cited, not guessed)

- Playwright MCP. Accessibility snapshot with `ref=eN`. Actions take that ref. Fresh snapshot after each tool. Docs: https://playwright.dev/mcp/snapshots
- browser-use. Observe-decide-act loop. Indexed interactive elements plus optional screenshot. https://github.com/browser-use/browser-use
- Stagehand. `observe()` then `act()` then `extract()` with a schema. Hybrid a11y snapshot. https://docs.stagehand.dev/v4/basics/observe

ChatGPT and Cursor private internals are out of scope.

## Design door (architect next)

Do not add a second browser process unless live QWebEngine extract plus a11y refs fail the predicate.

The one-way door is the observation the next Hermes step sees:

- Candidate A. Enrich the existing snapshot (refs + body excerpt) and keep the same 12 verbs plus one `extract`.
- Candidate B. Split observe / act / extract as separate commands in the Playwright MCP or Stagehand shape, still on QWebEngine.

Regex compiler, vision-only, and Playwright MCP sidecar are rejected unless the chosen QWebEngine path fails live.

## Scope

Roughly 15-25 files under `iris/browser`, `iris/ui/control_actions/browser.py`, observation packing, `_check_*`, `tests/browser`. No new GUI chrome. No Hermes gateway fork. HUD approval for send/purchase stays.

Rigor is high. Observation format and live tool calling are one-way for local-model token budget. Mechanical wiring is lower rigor once the sketch exists.

## Blockers

- Live Hermes must be up for E2E. Skip is recorded, not hidden.
- MCP disconnect replies while `control_port` exists need a separate root-cause if they reproduce.
- Page text stays wrapped as untrusted input.

## Workflow after this frame

1. How explainer (wait for the four explorers plus public survey).
2. Architect arena, two whole-shape candidates, then graft.
3. Harness first. Failing tests for extract, teaching that news is a browser job, packed body in PAGE TEXT.
4. Implement against the sketch in verifiable units.
5. Live 10-scenario matrix. Fix until the predicate holds or a skip is justified.
6. Conventional commit.
