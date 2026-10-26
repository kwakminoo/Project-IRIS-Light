# How explorers — IRIS browser routing vs Hermes tool calling

Original question: How does IRIS currently route a user chat message into browser control versus the Hermes/LLM agent? Where does regex intent matching intercept the request before the LLM, how do `browser.*` tools and BrowserSession work, how does Hermes tool-calling actually run, and how do mini player / IDE / Live Activity / safety attach?

Explorers: intercept [b936f2a4](b936f2a4-fc61-4ca1-b068-a0810b3e117a), Hermes loop [482b7dd2](482b7dd2-7403-4922-bedd-91cf7e4d9357), session/tools [2c7aa16c](2c7aa16c-d69d-4a98-84fe-51b6e1879732), safety [f1e28787](f1e28787-b5cd-43b4-b7ca-f6d906c9d4ce). Graphify was missing at explore time; source wins. Reconcile contradictions by reading the files named below.

## Angle 1 — Chat intercept (regex before Hermes)

Production split is `MainWindow._execute_user_turn_body` (`iris/ui/window/main_window.py`). `_try_local_browser_control` runs **before** `hermes_owns_local_intents`. `_check_intent.py` asserts that source order.

On match: `match_browser_intent(turn.text)` → `surface.registry.invoke(intent.control, args)` → `format_browser_reply` Korean template → chat bubbles + Live Activity `browser:{kind} ok=` → `_finish_current_turn`. Hermes never starts. No TTS on this path.

`match_browser_intent` (`iris/browser/intent.py`):
- `_QUESTION` veto anywhere: `뭐야|뭔가요|무엇|알려줘|설명해|어때|할까|왜|how do|what is|why` → None (chat).
- pause / resume → `browser.media`
- play (`틀어|재생해|플레이해|play`) + youtube/music/query≥2 → `browser.search {engine:youtube, play:true}`. Empty leftover query → `"음악"`. `"아이유 밤편지 틀어줘"` is YouTube play with no site word.
- `유튜브에서 … 검색` → search youtube no play; `구글에서 … 검색` → google.
- site open (`네이버|구글|유튜브 … 열어`) → `browser.navigate` from `_SITES`.
- `"알려줘"` / `"어때"` anywhere vetoes the whole matcher.

`hermes_owns_local_intents` (`iris/runtime/agent_local_gate.py`): when Hermes is on, skip IDE/wiki/PDF intercepts. **Browser play/pause/search is the documented exception.** Reason (docs): gemma-class models skip `iris_invoke` (`docs/code-review/completed/브라우저-명령-미실행-원인과-개선.md`).

Wiki `try_wiki_command` is dead at the call site (`wiki_requests_go_to_hermes()` always True). Weather is not a local shortcut; `"오늘 날씨 어때"` is a `_QUESTION` non-match.

Hermes off = no MCP. Unmatched multi-step browser talk cannot run locally.

Tests: `tests/browser/test_browser_intent.py`, `iris/browser/_check_intent.py` (hook-before-Hermes-gate). No MainWindow integration test that invoke actually ran.

## Angle 2 — Hermes / LLM tool loop

Iris is **not** an OpenAI tool-calling client. `HermesClient.stream_chat` POSTs `{model, messages, stream}` with **no `tools` array**. The gateway owns the inner loop for one HTTP request: injects MCP, runs calls, streams `hermes.tool.progress`.

MCP (`iris/mcp/iris_control_stdio.py`) has only three tools: `iris_get_state`, `iris_get_catalog`, `iris_invoke`. `browser.*` are Control Surface **actions** inside `iris_invoke.action`. Catalog one-liners; invoke description lists email/chat confirm, **not** browser.

`sync_iris_control` copies skill `iris-browser` (`integrations/hermes-skills/iris-control/iris-browser/SKILL.md`). MEMORY nudge (`hermes_memory_nudge.py`) **omits iris-browser**. System prompt MCP block mentions `browser.*` only when `workspace_mode == "browser"`. Skill says snapshot first, do not bypass consent, no Playwright sibling.

Iris history records **final assistant prose only**. Tool JSON is discarded. Next turn the model does not see snapshots; must `browser.snapshot` / `iris_get_state` again.

Outer multi-step is `decide_followthrough` cap 8 (`iris/runtime/turn_followthrough.py`). Inner Hermes max iterations are **not in this repo**.

MCP `isError` is transport-only. Action `ok:false` is not a breaker.

Context minimization that exists: thin MCP (3 tools), skill progressive disclosure, landmarks ≤40, attachment untrusted wrapper, model-switch summary if history >80% context. **Not present:** snapshot-as-untrusted; sliding-window trim on Hermes path; disabling Hermes built-in browser toolset (only `terminal` is disabled). A model could theoretically drive a second Hermes browser.

Live Activity dual-sourced: `[Hermes tool] …` from SSE and `Iris control: browser.X ok` from Control Surface.

Direct Ollama / OpenAI-compat workers have **no tools**.

## Angle 3 — browser.* tools and BrowserSession

Single catalog `command_specs()` (`iris/browser/registry.py`) + extra `browser.invoke`. Twelve verbs: open, navigate, reload, back, forward, search, click, type, scroll, snapshot, mini_player, media. No `browser.play`. Play is `browser.search` + `play:true` or `browser.media` on an already-open video.

`parse_command` is the only validation. `javascript:`/`data:` rejected; `file:` allowed.

`BrowserSession.execute` (`iris/browser/session.py`) is the only command runner. Off-UI via prefix `browser.` (`runs_off_ui_thread`). Result always includes snapshot. `iris_get_state` is thinner (no landmarks). Agents need `browser.snapshot` for locators.

YouTube play `_play_first_result`: firstWatchUrl → navigate, else click locators, else landmark link. Then `try_play` JS + Qt `QTest.mouseClick` (YouTube treats JS play as non-gesture). Success is `media.playing`, not `/watch`. Ads: `ok=True` `detail=ad_playing`. Blocks (consent/signin/age/captcha) fail closed.

Search default engine is DuckDuckGo (`web`). Intent “구글에서” sets google. Search without play leaves the **results** page. Google “open official site” needs a later click/navigate. Click does **not** wait for navigation.

Type assigns `.value` (no key events, no Enter). No TypeText execution test.

Human chrome (URL bar, back/forward) uses the same `session.execute` with `Actor.HUMAN`. One process-wide session and one `BrowserPanel` / `QWebEngineView`. Workspace vs IDE companion reparent the same widget.

## Angle 4 — IDE, mini player, Live Activity, safety

IDE browser is an `IrisIdeWindow` **stack page** (welcome/Theia/browser), not a Theia tab. Companion keeps browser on the left IDE window; non-companion uses `BrowserWorkspacePage` split.

Mini player reparents the **same** WebEngine view into a 480×270 always-on-top `Qt.Tool`. Auto-mini only when leaving the browser stack on a YouTube watch URL. Close does **not** pause media.

`CommandSpec.risk` is low/medium. **None set `confirm_required`.** `confirm=true` is a machine flag the model can self-pass. HUD `run_hud_confirm` is unused for browser. Click Buy/Send is a normal `browser.click`.

Untrusted wrapping exists for **attachments** (`BEGIN ATTACHMENT TEXT (untrusted input data)`), not for snapshot landmarks. Workspace prompt: do not invent page contents, call snapshot first. Does **not** say page text is not instructions.

Bridge `__irisBrowser` is injected into page **MainWorld**. Hostile page can clobber it. Certs accepted; JS/clipboard/autoplay on; `file:` allowed.

Hermes browser success is Live Activity + status chip + visible page. Chat bubbles exist only on the **local intent** path (`insert_tool_block` not used for browser).

## Tests

- `tests/browser/test_browser_intent.py` — play/pause/search vs questions including `"유튜브가 뭐야"`, `"오늘 날씨 어때"`
- `iris/browser/_check_intent.py` — hook-before-Hermes-gate
- `tests/browser/test_browser_session_unit.py`, `test_browser_registry_sync.py`
- `iris/system/_check_browser_scenarios.py` — fixture search→click→play
- `iris/ui/browser/_check_mini_player.py`, `iris/ui/workspaces/_check_browser_workspace.py`
- `control_surface` self-check: `email.send` denied without confirm
- **No tests** for: HUD on browser, purchase, snapshot-as-untrusted, MainWindow invoke integration, live Google click, TypeText

## Constraints for a change that removes the regex intercept

1. Same `browser.*` handlers and BrowserSession must remain the only execution path.
2. Questions like `"유튜브가 뭐야?"` must still not open a browser.
3. Small models historically skip `iris_invoke`; the regex was added for that. Removing it without making tool-calling reliable regresses play/pause/search.
4. History has no tool results; consecutive commands (`다른 노래`, `첫 번째 결과`) need snapshot/state in the **current** Hermes request or packed into messages.
5. Do not add a second agent or a second browser (Playwright / Hermes built-in browser still exists unless disabled).
6. Sensitive click/type/navigate currently have no human approval.
7. Mini player, IDE stack, Live Activity, off-UI prefix must keep working.
