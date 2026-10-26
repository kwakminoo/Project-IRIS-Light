# Grounding. IRIS general-purpose browser agent (HEAD 2026-10-26)

Source-checked this session. Graph first, source wins. Public survey is cited, not ChatGPT/Cursor internals.

## Predicate

Ten live Hermes+GUI utterances PASS/FAIL/SKIP. PASS needs `iris.log` `browser.*` matching the reply, visible URL matching, cited text from extract/snapshot, no `0xC0000409`, no MCP-down lie while `control_port` exists. Regex intercept stays gone.

## How a turn reaches the page

User chat → `_execute_user_turn_body` → if Hermes on, no IDE/wiki regex. **No browser intercept** (`intent.py` deleted). `HermesChatWorker` POSTs `{model, messages, stream}` with **no tools array**. Hermes gateway loops MCP. Only MCP tools: `iris_get_state`, `iris_get_catalog`, `iris_invoke({action, args})`. `iris_invoke` HTTP POSTs Control Surface. `register_browser_actions._handle` → `parse_command` → `BrowserSession.execute`. Tool JSON is `BrowserResult.to_control_dict()`. Iris Python is **not** a tool loop. One SSE can contain many MCP calls. Followthrough cap 8 is wiki-shaped, not browser.

Dedicated GUI and IDE-internal browser **reparent the same QWebEngineView**. One `get_browser_session()`.

Hermes built-in `browser` and `terminal` toolsets are disabled. Hermes `web` (`web_search`/`web_extract`) stays enabled.

## What Hermes sees

`pack_browser_observation`: trusted `phase/playing/last_action/last_ok/last_detail/url`. PAGE TEXT wrap: title + ≤40 landmark **names**. No article body, no PDF text, no captions, no a11y refs. Landmarks from `_bridge.js` `querySelectorAll("a[href], button, [role=button], h1, h2, input, textarea")`, name cap 120.

`command_specs()` verbs: open, navigate, reload, back, forward, search, click, type, scroll, snapshot, mini_player, media. **No extract/read/tabs/wait.** Locators: `ByCss` | `ByText` | `ByRole`.

Teaching (`browser_teaching_block`): YouTube play recipe, leftover query → 음악, questions including weather are not a browser action, success is `media.playing`, PAGE TEXT untrusted, no Hermes `browser_*`, HUD for send/purchase.

`iris-browser` SKILL.md: YouTube one-shot and Google-then-click. No news/paper/read recipe.

Navigate/search wait `loadFinished` (45s). **Click sleeps 0.1s and does not wait for navigation.**

## Measured failures (not inferred)

| When | User | What ran | Reply |
|---|---|---|---|
| 22:47 KST | 최신 뉴스 보여줘 | `classify_turn` → `today` → SerpAPI fail. iris.log system `chars: 67` = `search_failure_reply` "SerpApi 키가 없습니다". **No `iris.browser cmd=`** | 뉴스 도구가 없다 |
| 22:50 | 최신 뉴스 네이버에서 켜줘 | Same steal, chars 72 | 네이버 접속 기능이 없다 |
| 21:43 | 아무 노래나 유튜브에서 틀어줘 | Hermes POST, no `cmd=search` | MCP가 응답하지 않는다 |
| 22:26 | HTTP live_invoke, not chat | `search` google + youtube `play=true` | watch URL `playing=True` |
| 10-22 12:36 | 유튜브 노래 아무거나 | `cmd=search` youtube play=True same second | 재생 시작. 스피커는 확인 안 함 |

`classify_turn` matches `뉴스|날씨|…` → `today` → `PastChatsWorker` `today_search` → `google_news` via SerpAPI. On missing key it **returns early** with failure evidence and never reaches `browser.*`. That is the news miss. WebEngine can search Google (measured 22:26).

Live logs never show `cmd=click|type|scroll|snapshot`. Compound browse did not run.

## Public pattern to copy (not a process)

Playwright MCP / Chrome DevTools MCP: compact a11y snapshot + ref/uid, snapshot after act, click by ref. Stagehand: observe/act/extract. browser-use: inner Agent.run + screenshot every step — **reject** (second planner, vision tokens). Playwright/CDP sidecar — **reject unless** live QWebEngine extract+refs fail the predicate.

Survey: `.tmp/browser-llm-agent-how/PUBLIC_SURVEY.md`

## Constraints

- Hermes `iris_invoke` stays the planner. No Python `Agent.run`.
- One QWebEngine. No new GUI chrome.
- `command_specs()` is the one verb list. Teaching and SKILL derive from it.
- Page strings untrusted (`BEGIN PAGE TEXT`). Title/body/landmark names never in the trusted block. `url` today is trusted; do not silently expand trust.
- HUD via `looks_sensitive_browser_act` for send/purchase. Do not honor `args.confirm`. Catalog `confirm_required` stays false for browser.
- No regex intercept (`_check_intent.py` asserts gone).
- Local-model tokens: cap body, no screenshots by default.
- Sensitive: do not bypass consent/signin/age/captcha.
- Do not claim video analysis from title/description only.

## Files that will change (expected)

`iris/browser/types.py`, `registry.py`, `observation.py`, `_bridge.js`, `_driver.py`, `session.py`, `_check_intent.py`, `iris/ui/control_actions/browser.py`, `iris/system/hermes_memory_nudge.py` (if teaching), `integrations/hermes-skills/iris-control/iris-browser/SKILL.md`, `iris/knowledge/answer_grounding.py` / `past_chats_worker.py` (today steal), `tests/browser/*`, live `_check_*`.

## Design door

How the next Hermes step **reads** a page and **chooses a click**, without a second browser.

Whole-shape alternatives, not a patch list. At least two structurally distinct candidates.
