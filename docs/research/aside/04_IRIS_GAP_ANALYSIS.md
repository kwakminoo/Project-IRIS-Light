# Gap between Aside and the IRIS browser

This file compares published Aside behavior with the IRIS code in this workspace. Aside rows that need the installed app stay `unconfirmed`. IRIS rows are measured from source unless labeled otherwise.

Constraint from the request: keep `BrowserSession`, Qt WebEngine, `ViewHost`, `browser.*`, the mini player, and the Hermes internal integration. Do not replace that control plane with a Playwright REPL. This pass does not change feature code.

Aside public facts come from `docs/research/aside/01_ASIDE_FEATURES.md` through `03_REA_EVIDENCE.md` (through commit `e8cdb2a` plus later folds). Aside.exe is not on this machine.

## Structure

IRIS does not ship a Chromium-fork daily browser. It embeds one process-wide session that drives one `QWebEngineView`. Hermes never talks to Chromium or CDP. It calls three MCP names (`iris_get_state`, `iris_get_catalog`, `iris_invoke`). Page driving is the Control Surface action string inside `iris_invoke`, such as `browser.click`.

```text
ChatPanel send
  → MainWindow._execute_user_turn_body
      → Hermes POST
          teaching: iris/browser/observation.py::browser_teaching_block
          state:    pack_browser_observation(get_browser_session())
      → Hermes MCP tools (only three names)
          iris_get_state | iris_get_catalog | iris_invoke
      → iris_invoke {action: browser.*}   # Control Surface name, not an MCP tool
          → iris/mcp/iris_control_stdio.py   # execution errors keep isError=false
          → POST /v1/invoke                  # urlopen timeout 120s
          → ActionRegistry.invoke
              browser.* skips the 15s HTTP UI marshal (`runs_off_ui_thread`)
          → iris/ui/control_actions/browser.py::_handle
              parse_command (iris/browser/registry.py)
              looks_sensitive_browser_act  (optional HUD ask_human)
              BrowserSession.execute       (iris/browser/session.py)
                  _ensure_driver_locked
                  WebEnginePageDriver      (iris/browser/_driver.py)
                    Qt hops use `_call_on_ui_unbounded` (timeout=None)
                    HUD `_call_on_ui` is 3s and is not this path
                    navigate waits loadFinished up to 45s
                    JS eval waits 8s (play 16s)
                  QWebEngineView + _bridge.js
                  ViewHost apply           (PanelHost | MiniHost)
```

Where this investigation splits:

- Left branch is IRIS source, verified.
- Right branch is Aside public docs plus REA capture of aside.com. No Aside.exe.

Hermes built-in `browser` and `terminal` toolsets are disabled so the model cannot drive a second Chromium. `iris/system/hermes_iris_control_sync.py` `_IRIS_DISABLED_TOOLSETS = ("terminal", "browser")`. The skill `integrations/hermes-skills/iris-control/iris-browser/SKILL.md` forbids a sibling Playwright MCP for the same clicks.

`iris/browser/intent.py` is gone. `_check_intent.py` asserts `match_browser_intent` and `_try_local_browser_control` stay absent. A 2026-10-22 note in `docs/code-review/completed/브라우저-명령-미실행-원인과-개선.md` still describes that router. Treat that file as historical. Current contract is teaching plus `iris_invoke` only.

Key types:

- `BrowserSession` is the command bus. It is not a widget.
- `ViewHost` is `PanelHost(site=dedicated|ide_internal)` or `MiniHost`. The same `QWebEngineView` is reparented. String `"panel"` raises.
- Tabs are extra `QWebEnginePage`s on that one view. `target_id` is `tab:{index}`.
- Snapshot is JS landmarks plus excerpt, not a screenshot.

## Code review

| Point | What it does on this symptom | Why it does not already match Aside / why load can look broken |
| --- | --- | --- |
| `BrowserSession` in `iris/browser/session.py` | One process-wide command bus. Holds driver, `ViewHost`, last snapshot, last result. Exceptions set `BrowserPhase.FAULTED`. No auto-reconnect. | One visible page. Aside Agent Tabs are many agent-owned Chromium tabs that do not steal focus. |
| `ViewHost` in `iris/browser/types.py` | `PanelHost` or `MiniHost`. Reparent, not a second engine. | Does not isolate agent work from the tab the person is looking at. |
| `WebEnginePageDriver` + `_bridge.js` | Injected script snapshot, click-by-ref, type, extract, media. `navigate` waits `loadFinished` 45s then `TimeoutError`. JS eval 8s. Bridge is injected twice: profile `DocumentReady` MainWorld, and `_ensure_bridge` `runJavaScript`. `setRunsOnSubFrames(False)`. | Asidewright claims no injected scripts and a CDP wrapper. Qt WebEngine has no first-class CDP for the agent. A hung site looks like "connection failed". Iframes never see the bridge. |
| `command_specs()` in `iris/browser/registry.py` | Thirteen `browser.*` names: open, navigate, reload, back, forward, search, click, type, scroll, snapshot, extract, mini_player, media. Registry also registers catch-all `browser.invoke`. | Dedicated toolset. Aside's blog names this family (and Hermes) as the design they rejected. |
| `PageNode` + `NODE_CAP = 40` | `_bridge.js` stops at 40 named elements and skips nodes with empty `textOf`. No iframe walk. | Aside markets a packed a11y tree with iframe id. Icon-only buttons never enter PAGE TEXT. |
| `looks_sensitive_browser_act` | Token list: purchase, send, checkout, 결제, 구매, buy, pay. Search/media/open never sensitive. | Keyword heuristic, not a vault. |
| `pack_browser_observation` | Trusted Iris-owned block plus untrusted `BEGIN PAGE TEXT`. | No episodic browser memory. |
| `shared_browser_profile` in `iris/ui/browser/webengine_setup.py` | Named Qt profile under `~/.iris-light/browser-profile`. Chrome-like UA (QtWebEngine token stripped). Cookies persist. | Not the system Chrome profile. A site that "won't stay logged in" is a different cookie jar, not a dead engine. |
| `register_browser_actions` | Wires session to MainWindow. | Must stay. |
| MCP in `iris/mcp/iris_control_stdio.py` | Three tools. `browser.*` is the `action` string. Execution failures keep `isError` false. `urlopen` timeout 120s. | Navigate 45s fits inside 120s. A 45s timeout still returns as a tool result, not a transport error. |
| `_call_on_ui_unbounded` in `iris/ui/control_bindings.py` | Browser Qt hops wait until the UI thread returns. | `_call_on_ui` (3s, swallows to `None`) is HUD only. Mixing them up would make clicks vanish. |
| `BrowserPanel` tabs | Human chrome only. No `browser.tab_*`. Last tab close navigates home. | Aside Agent Tabs are agent-owned. |
| `BrowserSession.snapshot()` | Live URL/title overlay. Keeps previous `gen` and `nodes`. `_on_tab_changed` calls this. | Click after a human tab switch can hit `stale_ref` or the old `lastEls`. |
| `IrisWebEnginePage.certificateError` | `acceptCertificate()`. | Trust trade. Can also hide a real TLS failure. |
| `_wire_page_logging` `renderProcessTerminated` | Logs `status` and `code`. Does not set `FAULTED` and does not recreate the page. | The 2026-10-22 review already said there is no render-process recovery. A blank view can still show READY from the last snapshot. |
| `WebEnginePageDriver.reload` | Waits `loadFinished` 30s, then sets `READY` even if the wait expired. | Chip can read READY on a still-blank document. |
| `ensure_qt_webengine_ready` in `iris/ui/qt_bootstrap.py` | Before `QApplication`. Default `--disable-gpu-compositing`. Honors `QTWEBENGINE_CHROMIUM_FLAGS` if set. Does not import `QtWebEngineWidgets`. | Missing `AA_ShareOpenGLContexts` before first WebEngine import is 0xC0000409. `--disable-gpu` used to add `kFatalFailure` without stopping the GPU process. `.cursor/rules/qt-webengine-bootstrap.mdc` still says this function pre-imports widgets. Source does not. Black IDE screen is item 19 in `docs/code-review/조치-소요-사항-총괄표.md`, observation still open. |
| `BrowserMiniPlayer` | `Qt.Tool` because parenting Chromium into translucent `ChatPanel` access-violates. | Keep. Do not reparent the view into chat. |

Not reviewed for this gap: Theia `IrisIdeWindow._view`, ShowUI/Aloha desktop Computer Use, email/calendar workspaces.

## Implementation status

Status is measured from source. `partial` means a path exists but a documented hole remains.

| Capability | Status | Owner | Hole |
| --- | --- | --- | --- |
| Open dedicated or IDE-internal surface | done | `BrowserSession._execute_body` `Open`, `MainWindow.show_browser_workspace` | First `ensure_view` is lazy. Init-time construct is forbidden (UI freeze). |
| Navigate / reload / back / forward | partial | `WebEnginePageDriver.navigate` / `reload` / `history_step`, `parse_page_url` | Navigate 45s timeout → FAULTED. Reload 30s then forces READY. `javascript:`/`data:` rejected. Human URL bar swallows that `ValueError`. `loadFinished(False)` accepted if URL left `about:blank`. |
| Web / Google / YouTube search | done | `iris/browser/search.py` `search_url`, `Search` | Home is Google. System Chrome search is not this profile. |
| DOM landmark snapshot | partial | `_bridge.js` snapshot, `BrowserSession._stamp`, `NODE_CAP=40` | Skips nameless nodes. No iframe. No a11y tree. Cap 40. |
| Click by ref | partial | `Click` → `_resolve_ref` → `__irisBrowser.click` | Agent wire is `ByRef` only. CSS/text/role exist on the driver for YouTube play internals. Stale gen after human tab switch. |
| Type into ref | partial | `TypeText` → `__irisBrowser.type` | Sets `value`/`textContent` and fires `input`/`change`. Not key events. React-controlled fields can miss. inferred. No secret fill that hides the value from PAGE TEXT. |
| Scroll | partial | `Scroll` → `window.scrollBy` | Page deltas or `page=up\|down` (800px). `_parse_scroll` has no `ref`. No element scroll. |
| Extract article/document | done | `Extract` → `__irisBrowser.extract` | innerText only. Skill says do not claim PDF layout. |
| Media play/pause/resume | partial | `Media`, `__irisBrowser.tryPlay`, `QTest.mouseClick` fallback | Consent/signin/age/captcha returned as `detail`, not bypassed. Speaker output unconfirmed. |
| Mini player | partial | `MiniPlayer` → `MainWindow.apply_browser_view_host` → `BrowserMiniPlayer` | Command restore in non-companion can leave the view in the Tool window (`.tmp/browser-unify-how/EXPLANATION.md`; verify before treating as current). Explicit mini works. |
| Cookies / session persist | done | `shared_browser_profile`, `AllowPersistentCookies` | Isolated from system Chrome. No incognito session flag. |
| Human tabs | partial | `BrowserPanel` `_on_tab_changed`, `_adopt_popup` | Create/switch/close are human. Agent sees `browser_tab_index` in `iris_get_state` but cannot switch. |
| Agent tab control | missing | no `browser.tab_*` | Aside Agent Tabs are out of scope without a Chromium fork. |
| Popups | partial | `IrisWebEnginePage.createWindow` → `_adopt_popup` | New page is appended. Agent `target_id` after popup unconfirmed. |
| Downloads / file picker | missing | no `downloadRequested` / file dialog handler under `iris/ui/browser` | unconfirmed Qt default. |
| Screenshot / CUA | missing | no `grab()` in browser driver | Snapshot teaching forbids claiming figures were read. |
| iframe | missing | `setRunsOnSubFrames(False)`, no iframe in `_bridge.js` | Aside a11y claims iframe id. Same-origin walk would still need the flag flipped. |
| Password vault | missing | no vault on `BrowserSession` | |
| Browser episodic memory | missing | chat/wiki memory is a different subsystem | |
| Render-process recovery | missing | `_on_crash` logs only | |
| Local phrase router | removed | `_check_intent.py` forbids `intent.py` | Small models that do not `iris_invoke` still look "disconnected". Historical cause in the 2026-10-22 review. |

Hermes link, measured:

1. `sync_iris_control()` writes MCP `iris-control`, copies `iris-browser` skill, disables Hermes `browser` toolset.
2. Every chat POST includes `browser_teaching_block()` and `pack_browser_observation()`.
3. Tool loop runs inside the Hermes gateway, not in Iris (`HermesChatWorker._run_external`).
4. Success depends on the model emitting `iris_invoke`. Iris does not fall back to a local browser phrase path.

## Feature gap

| Capability | Aside (public) | IRIS (source) | Kind |
| --- | --- | --- | --- |
| Daily Chromium browser with logged-in sites | Whole-app Chromium fork | Qt WebEngine panel in the Iris window | different product shape, keep |
| Agent lives in the same visible page the person watches | Official | Skill: "the user watches the same page" | already aligned |
| Control language | Playwright-shaped REPL + bash | Named `browser.*` via `iris_invoke` | keep IRIS |
| Snapshot | Trimmed a11y + CUA fallback | 40 named DOM nodes from injected JS | IRIS weaker |
| Background agent tabs that do not steal focus | Blink patch | Extra pages, human tab bar, `FocusOnNavigationEnabled=True` | IRIS weaker, Blink out of scope |
| Locked agent viewport 1440×900 | Blink patch | View follows the Qt widget | out of scope unless faked in the widget |
| Credential autofill hidden from the model | Aside Vault | No vault on `BrowserSession` | IRIS missing |
| Human approval at payments/posts | Product claim | Keyword `ask_human` on click/type | IRIS weaker |
| On-device task memory | Markdown episodic + local embeddings | Not on this path | IRIS missing |
| Side panel from current page | Help center | Chat already beside the page in companion 80:20 and dedicated 820:420 | IRIS has side chat. No page-attachment chip |
| Split tabs | Help center | Layout shells, not two web pages | IRIS missing |
| Incognito agent task | Help center | One persistent profile | IRIS missing |
| MCP/CLI into the same browser | `aside mcp` | `iris_invoke` | different names, same idea |
| Desktop Computer Use | Changelog, Max plan | Separate ShowUI path | do not merge |
| Bot-detection Chromium patches | Official blog | UA token strip only | IRIS weaker, fork out of scope |
| Hosted-model privacy | Policy: providers get prompts and selected snapshots | PAGE TEXT is already sent to Hermes/the model | similar trust boundary, different product copy |

## Architecture gap

Aside rebuilt Chromium so an agent can work in the user's real browser without looking like a bot and without yanking focus. IRIS embedded Qt WebEngine so Hermes and the human share one panel inside an existing desktop shell.

The hard limit is the engine. Qt WebEngine will not grow Blink patches, Chrome Web Store extensions, or Asidewright. Work that still pays off stays on `BrowserSession`, `_bridge.js`, and FAULTED recovery.

Aside's blog argues that dedicated `browser.*` tools fight the model's training data. IRIS already taught those tools, disabled Hermes' own browser toolset, and packed observations on every POST. Throwing that away to add a JS REPL would violate the keep-Hermes-integration constraint.

## Problems and causes

"접속이 불안정하다" in this codebase is several failures that share one user-visible symptom. They are not one bug.

| Symptom | First wrong place | Evidence | Kind |
| --- | --- | --- | --- |
| Agent says it cannot browse while the panel is open | Model never emits `iris_invoke`. Local phrase router was removed on purpose. | `_check_intent.py` forbids `intent.py`. 2026-10-22 review: gemma4 answered in text only. | measured contract, runtime depends on the model |
| Navigate hangs then dies | `WebEnginePageDriver.navigate` 45s `loadFinished` wait | `_driver.py` raises `TimeoutError("navigate timeout")`, session sets FAULTED | measured |
| Click continues on a page that is still navigating | `settle_after_act` waits 45s and does not raise | `_driver.py` | measured. Snapshot after the wait can still be the old document. |
| Page looks dead after a Chromium crash | `renderProcessTerminated` only logs. Does not set FAULTED. | `webengine_setup.py` `_on_crash` | measured, no restore. Chip can stay READY. |
| Reload looks done while blank | `reload` 30s wait then `_phase = READY` | `_driver.py` `reload` | measured |
| YouTube play hangs then MCP drops | Stacked waits: navigate 45s + click loop 15s + watch 12s + tryPlay 16s, plus a second navigate | `_play_first_result`, `try_play`, MCP `urlopen` 120s | measured in source. Live 120s race unconfirmed. Worker is not cancelled when the MCP client leaves. |
| Human `javascript:` URL does nothing | `_on_url_submitted` `except ValueError: return` | `panel.py` | measured. Agent path returns `disallowed url scheme`. |
| Black or frozen first paint | WebEngine imported after `QApplication`, or GPU flags | `ensure_qt_webengine_ready`, 총괄표 item 19 | measured bootstrap, black screen recurrence unconfirmed |
| Site blocks the embed | Residual Qt/WebEngine fingerprint after UA strip | `chrome_like_user_agent` | remaining blocks unconfirmed |
| "I am not logged in" | Different cookie jar from system Chrome | `~/.iris-light/browser-profile` | measured isolation |
| Click misses after changing tabs | `snapshot()` keeps old `gen`/`nodes` | `session.py` `snapshot`, `panel.py` `_on_tab_changed` | measured |
| Click misses on icon-only or iframe controls | Bridge skips empty names, cap 40, no iframe | `_bridge.js` | measured |
| TLS looks fine on a bad cert | `acceptCertificate()` | `webengine_setup.py` | measured |
| Mini player / companion glitch | Reparent of one view, not a second engine | `BrowserMiniPlayer` `Qt.Tool` | keep this shape |
| Click or snapshot returns `None` with no error | Wrong marshal: `_call_on_ui` 3s instead of unbounded | Browser path uses `_call_on_ui_unbounded` | measured wiring, regression if swapped |

There is no automatic reconnect after FAULTED. The completed review already recorded that.

## Keep vs redesign

Keep, improve in place:

- `BrowserSession` + `command_specs` + `iris_invoke`
- Qt WebEngine + `shared_browser_profile` + `_bridge.js`
- `ViewHost` reparent and `BrowserMiniPlayer` as `Qt.Tool`
- Hermes `browser` toolset stays disabled
- PAGE TEXT trust wrap

Redesign only if the product goal becomes "IRIS is a daily Chromium-fork browser":

- Blink focus patches, locked 1440×900 agent viewport, bot-detection internals
- Asidewright / JS REPL as the agent API
- Agent Tabs that do not steal the person's tab
- Chrome Web Store extension host

That redesign is out of scope for this plan. It would break the 80:20 shell and the current mini player.

## Improvements

Ranked for the person using Iris chat plus the in-window page. Each item stays on the current bus.

1. Stamp a new `gen` on human tab switch. `BrowserSession.snapshot()` currently overlays URL and keeps old nodes. `_on_tab_changed` calls it. Clicks then resolve against the previous document. Smallest correctness fix. Files: `iris/browser/session.py` `snapshot`, `iris/ui/browser/panel.py` `_on_tab_changed`.
2. Packed snapshot. Stop dropping nameless controls. Raise or replace `NODE_CAP`. Walk same-origin iframes if Qt JS can reach them. Keep `g{gen}e{index}`. Files: `iris/browser/_bridge.js`, `iris/browser/types.py` `NODE_CAP`, `PageNode`.
3. Recreate the page after `renderProcessTerminated`, set FAULTED from that slot, and stop `reload` from forcing READY after a 30s miss. Today the log line is the whole recovery. Files: `iris/ui/browser/webengine_setup.py` `_on_crash`, `WebEnginePageDriver.reload`, `BrowserSession.execute` FAULTED branch.
4. Screenshot fallback when `nodes` is empty or `stale_ref` hits a canvas. Do not add a second click API until this miss is real on YouTube/canvas. Files: `WebEnginePageDriver`, observation packer.
5. Secret fill that never copies the password into PAGE TEXT, plus a wider `looks_sensitive_browser_act`. Files: `observation.py`, type path in `session.py`.

Later, still in place: Qt download signal, incognito `QWebEngineProfile` flag, origin markdown notes, popup `target_id` after `_adopt_popup`, `setRunsOnSubFrames` if iframe snapshot is in scope, cap YouTube play so stacked waits stay under the 120s MCP client.

Do not: fork Chromium, add Asidewright, add `aside repl`, enable Hermes built-in `browser_*`, drive Theia with `BrowserSession`, parent the view into `ChatPanel`.

## Where things live

| File | Functions | Role |
| --- | --- | --- |
| `iris/browser/types.py` | `ViewHost`, `BrowserCommand`, `BrowserSnapshot`, `make_page_ref` | Domain types |
| `iris/browser/registry.py` | `command_specs`, `parse_command` | Wire dict → command |
| `iris/browser/session.py` | `get_browser_session`, `execute`, `_execute_body`, `snapshot`, `_resolve_ref`, `_stamp` | Command bus |
| `iris/browser/_driver.py` | `WebEnginePageDriver.navigate`, `_eval_js`, `settle_after_act`, `try_play` | Qt I/O |
| `iris/browser/_bridge.js` | `snapshot`, `click`, `type`, `scrollBy`, `extract`, `tryPlay` | In-page API |
| `iris/browser/observation.py` | `pack_hermes_result`, `pack_browser_observation`, `browser_teaching_block`, `looks_sensitive_browser_act` | Hermes POST |
| `iris/browser/search.py` | `search_url` | DDG / Google / YouTube URLs |
| `iris/browser/youtube.py` | `page_block_reason`, `is_youtube_watch_url` | Consent/signin/age, no bypass |
| `iris/ui/control_actions/browser.py` | `register_browser_actions`, `_handle` | Registry wiring |
| `iris/ui/browser/webengine_setup.py` | `shared_browser_profile`, `configure_browser_view`, `_wire_page_logging` | Profile, UA, certs, crash log |
| `iris/ui/browser/panel.py` | `ensure_view`, `_on_tab_changed`, `_adopt_popup` | Human chrome, tabs |
| `iris/ui/browser/mini_player.py` | `attach_view`, `release_view` | `Qt.Tool` host |
| `iris/ui/qt_bootstrap.py` | `ensure_qt_webengine_ready`, `_apply_chromium_flags` | Process-wide Chromium flags |
| `iris/ui/window/main_window.py` | `show_browser_workspace`, `apply_browser_view_host`, `_chat_messages_with_project_context` | Shell + packing |
| `iris/ui/workspaces/iris_ide_window.py` | `apply_browser_view_host` | `ide_internal` / mini only |
| `iris/mcp/iris_control_stdio.py` | `_handle_tool`, `TOOLS` | Three MCP names |
| `iris/system/control_surface.py` | `ActionRegistry.invoke`, `runs_off_ui_thread` | HTTP control plane |
| `iris/system/hermes_iris_control_sync.py` | `_merge_disabled_toolsets`, `sync_iris_control` | Disable Hermes browser toolset |
| `iris/runtime/agent_local_gate.py` | `hermes_owns_local_intents` | Skip new local intercepts when Hermes is on |
| `integrations/hermes-skills/iris-control/iris-browser/SKILL.md` | n/a | Agent instructions |
| `iris/browser/_check_intent.py` | `main` | Intercept-gone + packer |

Modules that import `iris.browser` or `iris.ui.browser` (product, not tests): `iris/ui/window/main_window.py`, `iris/ui/workspaces/iris_ide_window.py`, `iris/ui/control_actions/browser.py`, `iris/ui/control_bindings.py`, `iris/mcp/iris_control_stdio.py` (teaching block only), `iris/system/hermes_memory_nudge.py`, plus the browser packages themselves. `iris/ui/qt_bootstrap.py` does not import `iris.browser`. It sets Chromium flags before `QApplication`.

## Borrowing

| Source | What to take | Why not this round |
| --- | --- | --- |
| Asidewright / Aside binary | Nothing. Closed. Not installed. | Need approval to install before REA inventory |
| Playwright a11y snapshot (open) | Node-role + name + ref packing | Adapt inside `_bridge.js` |
| [Playwriter](https://github.com/remorses/playwriter) | Same visible browser, explicit tab, a11y locators | Iris already owns in-process WebEngine. No CDP relay |
| [pi-mono/core](https://github.com/badlogic/pi-mono) | Runtime Aside names in public docs | IRIS already runs Hermes |
| Moss local embeddings | Retrieval idea only | Markdown grep first |
| Chromium fork / Blink patches | Focus and stealth | Out of scope for Qt WebEngine |
| `aside mcp` | One MCP into the live user browser | IRIS already has `iris_invoke` |

## Tradeoffs if IRIS copied Aside's control language

| Choice | For the person using Iris | For the next engineer | Verdict |
| --- | --- | --- | --- |
| Keep `browser.*` | Same skill, same HUD, same refs | One bus, tests already exist | Keep |
| Restore a local phrase router | Small models browse without `iris_invoke` | Conflicts with `_check_intent.py` and Hermes-owns-intents | Do not restore unless the product asks |
| Add a JS REPL beside `browser.*` | Longer automations | Two ways to click | Do not add |
| Switch engine to a Chromium fork | Closer to Aside stealth and Agent Tabs | Breaks Qt panel and 80:20 | Do not |
| Packed a11y + crash restore + tab gen on Qt | Fewer missed clicks, fewer dead panels | Localized to session, bridge, webengine_setup | Do |

`.tmp/browser-unify-how/EXPLANATION.md` still describes `ViewHost` as `Literal["panel", "mini"]`. Source is `PanelHost` / `MiniHost`. Treat that note as stale.

Earlier explorers: [IRIS browser stack](ac4a82f3-993a-4d6b-9acb-1eaddac5bdf0), [IRIS Hermes browser](414be7e4-7cbc-4c99-939c-acc34156d197). This rewrite folded [IRIS browser instability](bc02a582-59d5-47b4-8832-eae86527973c) and [IRIS browser feature status](0232bdad-1f4b-49fc-91e1-951778aca95f) after they finished: dual bridge inject, `setRunsOnSubFrames(False)`, reload-forces-READY, renderer death leaving READY, YouTube wait stack vs 120s MCP, human URL-bar swallow, type as value events not keydown. Source re-checked those paths.
