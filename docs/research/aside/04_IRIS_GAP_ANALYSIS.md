# Gap between Aside and the IRIS browser

This file compares published Aside behavior with the IRIS code that is in this workspace. Aside rows that need the installed app stay `unconfirmed`. IRIS rows are measured from source.

Constraint carried from the request: keep `BrowserSession`, Qt WebEngine, `ViewHost`, `browser.*`, and the Hermes internal integration. Do not replace that control plane with a Playwright REPL.

## Structure

Request path on the IRIS side, from a chat turn to a painted page:

```text
ChatPanel send
  → MainWindow._execute_user_turn_body
      → Hermes POST
          teaching: iris/browser/observation.py::browser_teaching_block
          state:    pack_browser_observation(get_browser_session())
      → model emits iris_invoke {action: browser.*}
          → iris/mcp/iris_control_stdio.py
          → POST /v1/invoke
          → ActionRegistry.invoke
          → iris/ui/control_actions/browser.py::_handle
              parse_command (iris/browser/registry.py)
              looks_sensitive_browser_act  (optional HUD ask_human)
              BrowserSession.execute       (iris/browser/session.py)
                  _ensure_driver_locked
                  WebEnginePageDriver      (iris/browser/_driver.py)
                  QWebEngineView + _bridge.js
                  ViewHost apply           (PanelHost | MiniHost)
```

Where this investigation splits:

- Left branch is IRIS source, verified.
- Right branch is Aside public docs plus one REA capture of aside.com. No Aside.exe.

Hermes built-in `browser` and `terminal` toolsets are disabled so the model cannot drive a second Chromium. `iris/system/hermes_iris_control_sync.py` `_IRIS_DISABLED_TOOLSETS = ("terminal", "browser")`. The Hermes skill `integrations/hermes-skills/iris-control/iris-browser/SKILL.md` says the same: do not register Playwright MCP for the same clicks.

## Code review

| Point | What it does on this symptom | Why it does not already match Aside |
| --- | --- | --- |
| `BrowserSession` in `iris/browser/session.py` | One process-wide command bus. Holds driver, `ViewHost`, last snapshot, last result. | One visible page by design. Aside's Agent Tabs are many agent-owned Chromium tabs that do not steal focus. IRIS has extra `QWebEnginePage`s on one view (`BrowserPanel`), not a background agent tab that keeps a locked 1440×900 viewport. |
| `ViewHost` in `iris/browser/types.py` | `PanelHost(site=dedicated\|ide_internal)` or `MiniHost`. Reparent, not a second engine. | Hosts the human chrome. It does not isolate agent work from the tab the person is looking at. |
| `WebEnginePageDriver` + `_bridge.js` | Injected script snapshot, click-by-ref, type, extract, media. | This is the injected-script path Asidewright claims to avoid. Qt WebEngine also does not expose a first-class CDP server to the agent. |
| `command_specs()` in `iris/browser/registry.py` | Thirteen `browser.*` names: open, navigate, reload, back, forward, search, click, type, scroll, snapshot, extract, mini_player, media. | Dedicated toolset. Aside's blog names this family (and Hermes) as the design they rejected in favor of REPL + bash. |
| `PageNode` + `NODE_CAP = 40` | Snapshot truncates to 40 nodes, names capped at 80 chars. `session.py` slices `snap.nodes[:NODE_CAP]`. | Aside markets a packed a11y tree with focus, iframe id, and clickable state. IRIS's cap is small and easy to miss controls on dense pages. |
| `looks_sensitive_browser_act` | Token list: purchase, send, checkout, 결제, 구매, buy, pay. Search/media/open never sensitive. | Keyword heuristic on the act, not a vault plus "payments, posts, messages always wait". No credential object that the model never sees. |
| `pack_browser_observation` | Trusted Iris-owned block plus untrusted `BEGIN PAGE TEXT`. | Correct trust boundary for page text. No episodic memory, no site-path memory, no local embedding index. |
| `shared_browser_profile` in `iris/ui/browser/webengine_setup.py` | One named Qt profile under `~/.iris-light/browser-profile`. Chrome-like UA (QtWebEngine token stripped). Injected bridge in MainWorld. | Persistent cookies exist. There is no agent password vault, no Windows Hello gate, no incognito task mode on this session object. |
| `register_browser_actions` | Wires session to MainWindow. `browser.invoke` plus every `control_name`. | This is the integration that must stay. Adding Aside-like REPL here would bypass it. |

Not reviewed for this gap: Theia `IrisIdeWindow._view`, ShowUI/Aloha desktop Computer Use, email/calendar workspaces. Those are other surfaces.

`.tmp/browser-unify-how/EXPLANATION.md` still describes `ViewHost` as `Literal["panel", "mini"]`. Source now uses `PanelHost` / `MiniHost`. Treat that note as stale.

## Feature gap

| Capability | Aside (public) | IRIS (source) | Kind |
| --- | --- | --- | --- |
| Daily Chromium browser with logged-in sites | Whole-app Chromium fork | Qt WebEngine panel in the Iris window | different product shape, keep |
| Agent lives in the same visible page the person watches | Official | Official IRIS skill: "the user watches the same page" | already aligned |
| Control language | Playwright-shaped REPL + bash | Named `browser.*` via `iris_invoke` | keep IRIS |
| Snapshot | Trimmed a11y + CUA fallback | 40 `PageNode`s from injected JS | IRIS weaker |
| Background agent tabs that do not steal focus | Blink patch, official blog | One view. Extra pages exist but focus policy is unconfirmed | IRIS weaker, Blink patch is out of scope |
| Locked agent viewport 1440×900 | Blink patch | View follows the Qt widget | out of scope unless faked in the widget |
| Credential autofill hidden from the model | Aside Vault | No vault on `BrowserSession` | IRIS missing |
| Human approval at payments/posts | Product claim | Keyword `ask_human` on click/type | IRIS weaker |
| On-device task memory | Markdown episodic + local embeddings | Chat/wiki memory is a different subsystem. Browser has none | IRIS missing in this path |
| Side panel from current page | Help center | Chat is already beside the page in companion 80:20 and dedicated 820:420 | IRIS already has a side chat. No page-attachment chip |
| Split tabs | Help center | Companion vs dedicated layouts, not two web pages side by side | IRIS missing |
| Incognito agent task | Help center | One persistent profile | IRIS missing |
| MCP/CLI into the same browser | `aside mcp` | `iris_invoke` is already that MCP | different names, same idea |
| Desktop Computer Use | Changelog, Max plan | Separate ShowUI path, not BrowserSession | do not merge in this plan |
| Bot-detection Chromium patches | Official blog | UA token strip only | IRIS weaker, fork is out of scope |

## Architecture gap

Aside rebuilt Chromium so an agent can work in the user's real browser without looking like a bot and without yanking focus. IRIS embedded Qt WebEngine so Hermes and the human share one panel inside an existing desktop shell.

The hard limit is the engine. Qt WebEngine will not grow Blink patches, Chrome Web Store extensions, or Asidewright. The useful work is on the harness that already exists: snapshot quality, events, secrets, memory, and approval.

Aside's blog argues that dedicated `browser.*` tools fight the model's training data. IRIS already taught those tools, disabled Hermes' own browser toolset, and packed observations on every POST. Throwing that away to add a JS REPL would violate the keep-Hermes-integration constraint and would reopen a second automation stack. The skill file forbids Playwright MCP for the same clicks.

## Improvements

Only empty seats on the IRIS path:

1. Packed snapshot. Raise signal in `PageNode` / `_bridge.js` / `NODE_CAP`. Keep refs `g{gen}e{index}`.
2. Screenshot fallback when the node list is empty or a canvas/video has no role.
3. Coarse async notes in `BrowserResult.detail` (popup, download, tab closed) without a CDP client.
4. Secret fill that never puts the password in PAGE TEXT. Reuse whatever password store Iris already has, or add a tiny OS-backed fill. Do not invent a second vault product in the first cut.
5. Expand `looks_sensitive_browser_act` from buy/pay tokens to post/message/payment intents, still on the existing HUD confirm.
6. Optional incognito profile for one task. Qt can make a second `QWebEngineProfile`. Wire it as a session flag, not a new command bus.
7. On-device "this site worked" notes after `browser.extract` / failed click. Markdown under `~/.iris-light/` is enough. Do not import Moss.

Do not: fork Chromium, add Asidewright, add `aside repl`, enable Hermes' built-in browser toolset, or drive Theia with `BrowserSession`.

## Borrowing

| Source | What to take | Why not this round |
| --- | --- | --- |
| Asidewright / Aside binary | Nothing. Closed. Not installed. | Need approval to install before REA inventory |
| Playwright a11y snapshot (open) | Node-role + name + ref packing ideas | Adapt inside `_bridge.js`, do not add Playwright as the agent API |
| [pi-mono/core](https://github.com/badlogic/pi-mono) | Aside's named harness base | IRIS already runs Hermes |
| Moss local embeddings ([third-party article](https://www.moss.dev/blog/aside-persistent-ai-memory)) | Retrieval idea only | Browser memory can start as markdown grep |
| Chromium fork / Blink patches | Focus and stealth | Out of scope for Qt WebEngine |
| `aside mcp` | Pattern: one MCP into the live user browser | IRIS already has `iris_invoke` |
| REA `capture_browser_scenario` | How to keep Evidence labels on later live checks | Analysis tool, not a product feature |

## Tradeoffs if IRIS copied Aside's control language

| Choice | For the person using Iris | For the next engineer | Verdict |
| --- | --- | --- | --- |
| Keep `browser.*` | Same skill, same HUD, same refs | One bus, tests already exist | Keep |
| Add a JS REPL beside it | Model may write longer automations | Two ways to click. Skill forbids the second | Do not add |
| Switch engine to a Chromium fork | Closer to Aside stealth and Agent Tabs | New runtime, breaks Qt panel and 80:20 | Do not |
| Packed a11y + CUA fallback on Qt | Fewer missed clicks on dense pages | Localized to `_bridge.js` and snapshot caps | Do |
