# How to close the useful Aside gaps in IRIS

Goal: make Hermes better at the existing in-window browser without replacing `BrowserSession`, Qt WebEngine, `ViewHost`, or `iris_invoke` → `browser.*`.

Do not install Aside, fork Chromium, or add a Playwright REPL unless a later brief says so.

Each phase ends in one check you can run. Stop if that check fails.

## Preconditions

- Read `04_IRIS_GAP_ANALYSIS.md` for the keep/drop list.
- Keep `integrations/hermes-skills/iris-control/iris-browser/SKILL.md` true: one visible page, refs from PAGE TEXT, no sibling Playwright MCP.
- Keep Hermes `browser` and `terminal` toolsets disabled (`iris/system/hermes_iris_control_sync.py`).

## Phase 0. Live Aside only if you want binary evidence

This investigation did not install Aside. REA could only capture `https://aside.com/`.

If you want install-directory inventory:

1. Approve a Windows install from [aside.com/download](https://aside.com/download).
2. Re-run a read-only REA inventory of that folder. Prefer package listing over a native decompile.
3. Append findings to `03_REA_EVIDENCE.md`.

Skip this phase to start IRIS work now.

## Phase 1. Packed snapshot (shipped)

Shipped in `ef4cbc3` (PAGE TEXT) and `ee68fce` (idle snapshot restamp).

`PageNode` now carries role, acc name, true-only flags, `ctx=` on colliding `(role, name)`, and iframe id. The packer uses `PAGE_TEXT_BUDGET = 4000` and never drops a stamped ref. Ref format stays `g{gen}e{index}`.

`BrowserSession.snapshot()` restamps when `live.url` or `tab_index` changes. Same-page idle snapshot keeps refs. Extract and media still skip stamp.

Check: `python -m iris.browser._check_intent`, `_check_bridge_snapshot`, and the idle-snapshot tests in `tests/browser/test_browser_session_unit.py`.

## Hermes multi-step (do not implement)

Hermes already plans, runs, and checks a chain of `iris_invoke` → `browser.*` calls. IRIS must not add a second planner, loop, or agent framework.

The path is:

1. Hermes `AIAgent` tool loop (`turn_tool_round.py`) posts each tool result back into the conversation and starts the next iteration.
2. The only page-driving tools are MCP `iris_get_state`, `iris_get_catalog`, and `iris_invoke`. Hermes built-in `browser` and `terminal` toolsets stay disabled (`hermes_iris_control_sync.py`).
3. `iris_invoke` POSTs to Control Surface `/v1/invoke`. `_handle` in `iris/ui/control_actions/browser.py` parses, optionally asks the human, then calls `session.execute`.
4. `pack_hermes_result` returns `ok, command_kind, detail, trusted, page_text, url, phase, playing, gen`. PAGE TEXT is untrusted input.
5. Teaching and recipes already say search then click then extract, copy `{ref}` from the last PAGE TEXT, and snapshot on `stale_ref`.

Loop caps and cancel live in Hermes:

- Main-agent `max_iterations` defaults to `sys.maxsize`. `IterationBudget` stops the turn when that budget is spent.
- `HermesChatWorker.request_cancel` stops the SSE stream. It does not abort an in-flight `session.execute`.
- IRIS already times out navigate (45s), reload (30s), play (90s), and MCP `urlopen` (120s).

Do not add an IRIS Observe-Act-Verify class, a per-turn browser command counter, or a second cancel path. Those would reimplement Hermes.

If a later brief needs abort of an in-flight execute, add one cancel flag on `BrowserSession.execute`, not a planner.

## Phase 2. Screenshot fallback

When `snap.nodes` is empty, or `browser.click` returns `stale_ref` on a canvas/video, attach a small screenshot in the untrusted PAGE TEXT (or a trusted "image present" flag plus a bounded image the model already knows how to read). Click-by-coordinate is a new command. Add it only if Phase 1 still fails on a real YouTube or canvas page.

Prefer a `browser.click` that accepts an existing ref. Add `browser.click {x,y}` only as a documented last resort, still through `parse_command`.

Check: one canvas fixture where Phase 1 emits zero interactive nodes and Phase 2 still lets the agent click.

## Phase 3. Result events

Fold popup, download, and navigation-finished into `BrowserResult.detail` or a small `events` tuple on `BrowserSnapshot`. Qt WebEngine already has load-finished and download signals. Do not open a CDP port.

Check: a page that opens a popup or starts a download. The next packed observation names that event. No new `browser.*` verb required.

## Phase 4. Approval and secrets

Extend `looks_sensitive_browser_act` in `iris/browser/observation.py` so post, message, and pay intents hit the existing `ask_human` HUD. Keep search, snapshot, extract, media, mini_player off that list.

For login: add a fill path that reads a secret from the OS or an existing Iris store and types it in the page without putting the value in PAGE TEXT or `last_detail`. Do not build Aside Vault, audit log, or Secure Enclave in this phase.

Check: `_check_intent.py` assertions for the new tokens. A live login page test that the model output does not contain the password.

## Phase 5. Optional task profile

Add an incognito (or ephemeral) `QWebEngineProfile` selected by a session flag, defaulting to today's `iris-browser` profile. Wire it through `shared_browser_profile` / `new_browser_page`, not through a second `BrowserSession`.

Check: cookies set in the ephemeral profile are gone after close. The default profile still has its cookies.

## Phase 6. Site notes, not a memory product

After a successful `browser.extract` or a recovered click path, append a short markdown note under `~/.iris-light/browser-memory/` keyed by origin. Inject a few lines into `pack_browser_observation`'s trusted block on the next visit.

Do not add local embedding models until that file is actually used.

Check: two turns on the same origin. The second POST contains the note. The note is Iris-owned text, not PAGE TEXT.

## Explicit non-goals

- Chromium fork, Blink focus patches, locked 1440×900 agent viewport.
- Asidewright or `aside repl`.
- Enabling Hermes built-in `browser_*`.
- Driving Theia `IrisIdeWindow._view` with `BrowserSession`.
- Desktop Computer Use inside `browser.*` (keep ShowUI separate).
- Split-tab chrome, Lasso, Ultrabrowse, Channels, Cloud handoff.

## Suggested order

1 → 3 can ship independently. 2 depends on a Phase 1 miss. 4 is the trust boundary. 5 and 6 are product extras.

Phase 1 is done. Next useful IRIS work, if any, is Phase 3 or Phase 4. Do not start a Hermes planner.

## Verification after any phase

- `python -m iris.browser._check_intent`
- `python -m iris.ui.browser._check_mini_player` if `ViewHost` code moved
- Confirm workspace and install bundles still contain the IDE markers only if `iris/**` UI that the IDE loads also changed. Browser-only Python does not need an iris-ide rebundle.

The 2026-10-27 Hermes multi-step review changed only this plan and `06_TEST_RESULTS.md`. No IRIS product code.

## Hermes tool visibility (2026-10-27)

`sync_iris_control` now writes `tools.tool_search.enabled: off` so MCP `iris_invoke` stays on the visible tool list. MEMORY v23 teaches those exact names, not `mcp__iris_control__*`. Sidecar child env forces UTF-8. Unknown chat errors keep the raw cause.

Do not add a planner. Restart the running Hermes process after sync. Details: `07_BROWSER_RUNTIME_DEBUG.md`.
