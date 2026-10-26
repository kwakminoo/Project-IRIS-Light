# Public survey: AI browser-agent implementations

Survey date: 2026-10-26. Only public docs, public source, or observed public behavior. URLs below were fetched in this session. **This document does not guess unpublished ChatGPT or Cursor internals.** Cursor is cited only from `https://cursor.com/docs/agent/tools/browser`.

IRIS comparison uses only these files as read in this session: `iris/browser/types.py`, `iris/browser/session.py`, `iris/browser/observation.py`, and `iris/browser/_bridge.js` (landmarks). No IRIS code was invented or changed.

---

## Method

Fetched with WebFetch / GitHub raw / official docs:

| Source | URLs fetched |
|--------|----------------|
| Playwright MCP | https://playwright.dev/mcp/introduction · https://playwright.dev/mcp/snapshots · https://playwright.dev/mcp/capabilities · https://raw.githubusercontent.com/microsoft/playwright-mcp/main/README.md |
| Playwright core | https://playwright.dev/docs/aria-snapshots · https://playwright.dev/docs/input · https://playwright.dev/docs/api/class-cdpsession |
| browser-use | https://github.com/browser-use/browser-use README (raw) · https://docs.browser-use.com/ · https://docs.browser-use.com/llms.txt · https://docs.browser-use.com/open-source/introduction · https://docs.browser-use.com/open-source/customize/tools/available · https://docs.browser-use.com/open-source/customize/tools/basics · https://docs.browser-use.com/open-source/customize/agent/basics · https://docs.browser-use.com/open-source/examples/templates/sensitive-data · https://browser-use.com/posts/production-architecture-browser-use · https://raw.githubusercontent.com/browser-use/browser-use/main/browser_use/dom/service.py · https://raw.githubusercontent.com/browser-use/browser-use/HEAD/browser_use/browser/watchdogs/dom_watchdog.py |
| Stagehand | https://docs.stagehand.dev/v4/basics/observe · https://docs.stagehand.dev/v4/basics/act · https://docs.stagehand.dev/v4/basics/extract · https://raw.githubusercontent.com/browserbase/stagehand/main/README.md |
| CDP | https://raw.githubusercontent.com/aslushnikov/getting-started-with-cdp/master/README.md · https://playwright.dev/docs/api/class-cdpsession · https://raw.githubusercontent.com/ChromeDevTools/chrome-devtools-mcp/main/README.md · https://raw.githubusercontent.com/ChromeDevTools/chrome-devtools-mcp/main/docs/tool-reference.md · https://developer.chrome.com/docs/devtools/agents |
| Nova Act | https://docs.aws.amazon.com/nova-act/latest/userguide/what-is-nova-act.html · https://docs.aws.amazon.com/nova-act/latest/userguide/glos-chap.html · https://github.com/aws/nova-act README |
| Open Interpreter | https://www.openinterpreter.com/docs/desktop/browser-workflows |
| Cursor (public docs only) | https://cursor.com/docs/agent/tools/browser |
| Skyvern | https://github.com/skyvern-ai/skyvern README · https://github.com/Skyvern-AI/skyvern/blob/main/skyvern/cli/skills/skyvern/SKILL.md (search/fetch of public GitHub) |

The Chromium protocol viewer page `https://chromedevtools.github.io/devtools-protocol/tot/Accessibility/` failed to initialize in this session. CDP claims below use the aslushnikov getting-started README, Playwright `CDPSession` docs, Chrome DevTools MCP source docs, and browser-use source that calls `DOMSnapshot.captureSnapshot` / `Page.captureScreenshot`.

---

## 1. Playwright and Playwright MCP

Public repo: [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp). Docs: [playwright.dev/mcp/introduction](https://playwright.dev/mcp/introduction). Package: `@playwright/mcp`.

### 1. Perception

Playwright MCP **operates on the accessibility tree, not pixels**. Docs: “structured accessibility snapshots — no vision models required.” ([introduction](https://playwright.dev/mcp/introduction), [snapshots](https://playwright.dev/mcp/snapshots), [README](https://raw.githubusercontent.com/microsoft/playwright-mcp/main/README.md))

Snapshot format is YAML-like ARIA, matching Playwright’s `page.ariaSnapshot()` / `toMatchAriaSnapshot` ([aria-snapshots](https://playwright.dev/docs/aria-snapshots)):

```
- heading "todos" [level=1] [ref=e3]
- textbox "What needs to be done?" [ref=e5]
- list [ref=e8]:
  - listitem [ref=e9]:
    - checkbox "Toggle Todo" [ref=e10]
```

Each node gets a **ref** (`e5`, or `f1e12` inside iframe 1). Refs are unique within one snapshot, valid until the page changes, assigned to every a11y node (not only interactive ones). Stale refs fail with `Ref not found in the current page snapshot. Try capturing new snapshot.` ([snapshots](https://playwright.dev/mcp/snapshots))

`browser_snapshot` can limit `target` (subtree), `depth`, `boxes` (`[box=x,y,width,height]`, viewport CSS pixels), or write to a file. `--snapshot-mode=none` stops attaching snapshots to tool responses. `browser_find` searches the current snapshot by text or regex and returns matching subtrees — cheaper than a full dump. ([snapshots](https://playwright.dev/mcp/snapshots), [README](https://raw.githubusercontent.com/microsoft/playwright-mcp/main/README.md))

Screenshots exist (`browser_take_screenshot`) but the README says: **“You can't perform actions based on the screenshot, use browser_snapshot for actions.”** Vision-mode coordinate tools are opt-in (`--caps=vision`). ([README](https://raw.githubusercontent.com/microsoft/playwright-mcp/main/README.md), [capabilities](https://playwright.dev/mcp/capabilities))

### 2. Click / scroll / type / tab

Core tools (always on): `browser_click`, `browser_type`, `browser_press_key`, `browser_fill_form`, `browser_select_option`, `browser_hover`, `browser_drag`, `browser_drop`, `browser_tabs`, `browser_navigate`, `browser_navigate_back`, `browser_wait_for`. ([introduction](https://playwright.dev/mcp/introduction), [capabilities](https://playwright.dev/mcp/capabilities))

- **Click:** `target` = ref or Playwright locator string (`getByRole('button', { name: 'Submit' })`, `#submit`, `text=Sign in`). Optional `element` (human-readable description “used to obtain permission”), `doubleClick`, `button`, `modifiers`. ([README](https://raw.githubusercontent.com/microsoft/playwright-mcp/main/README.md))
- **Type:** `target` + `text`; `submit` presses Enter; `slowly` types character-by-character. Default is fill-all-at-once. ([README](https://raw.githubusercontent.com/microsoft/playwright-mcp/main/README.md))
- **Keys:** `browser_press_key` (`Enter`, `Tab`, `ArrowLeft`, …).
- **Scroll:** **not a core tool.** Wheel scroll is `browser_mouse_wheel` under `--caps=vision`. Core path is `browser_press_key` or clicking an in-view target. Playwright itself auto-scrolls before click (`locator.click` waits, displays, stops moving, scrolls into view). ([input](https://playwright.dev/docs/input), [capabilities](https://playwright.dev/mcp/capabilities), [README](https://raw.githubusercontent.com/microsoft/playwright-mcp/main/README.md) `browser_mouse_wheel`)
- **Tabs:** `browser_tabs` list/create/close/select.

Under the hood these are Playwright locators, which for Chromium talk CDP (`page.context().newCDPSession`). ([CDPSession](https://playwright.dev/docs/api/class-cdpsession))

### 3. Page body extraction

There is **no dedicated “read article text” tool** in the core MCP set. Reading is:

- the accessibility snapshot itself (roles + names + text nodes);
- `browser_find` snippets;
- `browser_evaluate` JS;
- `browser_take_screenshot` for layout;
- `--caps=testing` `browser_verify_text_visible`.

Playwright test APIs also expose `page.ariaSnapshot()` and DOM `page.content()` / `innerText` outside MCP; MCP’s documented agent path is the a11y snapshot. ([aria-snapshots](https://playwright.dev/docs/aria-snapshots), [snapshots](https://playwright.dev/mcp/snapshots))

### 4. Observe → Plan → Act → Verify

Documented as an **MCP tool loop owned by the client**, not an inner `Agent.run()`:

1. Navigate / act.
2. **Most tools return a fresh snapshot automatically** after the action.
3. LLM reads refs, plans the next `target`.
4. Optional `browser_wait_for` (text appear/disappear, or time ≤30s).
5. Optional `--caps=testing` verify tools.

Docs contrast MCP vs Playwright CLI+SKILLS: MCP is for “specialized agentic loops… iterative reasoning over page structure”; CLI is cheaper on tokens because it avoids dumping large tool schemas and a11y trees. ([introduction](https://playwright.dev/mcp/introduction), [README](https://raw.githubusercontent.com/microsoft/playwright-mcp/main/README.md))

`--timeout-settle` (default 500ms) waits after each action for triggered work to settle. `--timeout-action` default 5000ms. ([README](https://raw.githubusercontent.com/microsoft/playwright-mcp/main/README.md))

### 5. Multi-step and error recovery

- Stale ref → fail closed, recapture snapshot. ([snapshots](https://playwright.dev/mcp/snapshots))
- `browser_handle_dialog` for JS dialogs.
- `browser_wait_for` for flaky load.
- `browser_run_code_unsafe` is explicitly **RCE-equivalent** (arbitrary JS in the Playwright server). ([README](https://raw.githubusercontent.com/microsoft/playwright-mcp/main/README.md))
- No built-in “replan after N consecutive failures” like browser-use; recovery is the host LLM retrying tools.

### 6. Session / context

- Default: **persistent profile** (cookies/login survive). Path includes workspace hash so projects isolate. One profile → one browser instance. ([README](https://raw.githubusercontent.com/microsoft/playwright-mcp/main/README.md))
- `--isolated`: in-memory; close loses storage. `--storage-state` can seed cookies.
- `--extension` / `--endpoint`: attach to an already-running Chrome/Edge.
- `--shared-browser-context` for HTTP clients.
- `--idle-timeout`: close headed never by default; headless 1 hour.
- Storage tools (`--caps=storage`): cookies, localStorage, sessionStorage, save/restore state.

### 7. Explicitly not claimed

- Screenshots are **not** the action targeting channel. ([README](https://raw.githubusercontent.com/microsoft/playwright-mcp/main/README.md))
- MCP is **not** the cheapest path for coding agents with large codebases (CLI+SKILLS is). ([introduction](https://playwright.dev/mcp/introduction))
- Core MCP does **not** expose a first-class `browser_scroll`.
- `browser_run_code_unsafe` is labeled unsafe / RCE.

---

## 2. browser-use (`browser-use/browser-use`)

Public: [github.com/browser-use/browser-use](https://github.com/browser-use/browser-use) (MIT), docs [docs.browser-use.com](https://docs.browser-use.com/), production post [browser-use.com/posts/production-architecture-browser-use](https://browser-use.com/posts/production-architecture-browser-use).

### 1. Perception

The open-source `Agent` **on each step takes a screenshot and extracts the DOM in parallel**, then sends both to the LLM. ([production architecture](https://browser-use.com/posts/production-architecture-browser-use))

Source: `DOMWatchdog` builds DOM state and captures a “clean screenshot” (base64); empty `about:` pages skip both. (`dom_watchdog.py` fetched). DOM extraction uses CDP `DOMSnapshot.captureSnapshot` with computed styles, paint order, DOM rects (`dom/service.py` fetched). Actor `page.screenshot` calls CDP `Page.captureScreenshot`.

Agent actions click **indexed interactive elements**, not a11y YAML refs. Tools: `click` “by their index”. ([available tools](https://docs.browser-use.com/open-source/customize/tools/available))

Vision is optional; sensitive-data docs say `use_vision=False` to prevent the LLM seeing secrets in screenshots. ([sensitive-data](https://docs.browser-use.com/open-source/examples/templates/sensitive-data))

### 2. Click / scroll / type / tab

Built-in actions ([available tools](https://docs.browser-use.com/open-source/customize/tools/available)):

| Group | Tools |
|-------|--------|
| Nav | `search` (DuckDuckGo/Google/Bing), `navigate`, `go_back`, `wait` |
| Interact | `click` (index), `input`, `upload_file`, `scroll` up/down, `find_text`, `send_keys` |
| JS | `evaluate` |
| Tabs | `switch`, `close` |
| Forms | `dropdown_options`, `select_dropdown` |
| Done | `done` |

Lower-level Actor API (legacy docs): CSS selectors, CDP `backend_node_id`, `page.mouse.click(x,y)`, `mouse.scroll`. ([search result pages under docs.browser-use.com/open-source/legacy/actor/](https://docs.browser-use.com/llms.txt))

Local MCP server exposes `browser_click` (index), `browser_type`, `browser_scroll`, `browser_get_state`, `browser_extract_content`, `browser_get_html`, `browser_screenshot`, plus `retry_with_browser_use_agent` as last resort. (listed in docs.browser-use.com MCP page via search; index: [llms.txt](https://docs.browser-use.com/llms.txt) → MCP Server)

### 3. Page body extraction

- `extract` — LLM extraction of webpage data (default agent tool).
- Actor `page.extract_content(prompt, schema, llm)`.
- MCP `browser_get_html` — full HTML or CSS-selected element.
- `evaluate` JS.
- Screenshot on request (`screenshot` tool asks for a screenshot in the **next** browser state).

Docs warn: **`is_done` only reports a terminal done action; `is_successful` is agent-reported; verify important external actions independently.** ([llms.txt agent instructions](https://docs.browser-use.com/llms.txt))

### 4. Observe → Plan → Act → Verify

Documented inner loop ([production architecture](https://browser-use.com/posts/production-architecture-browser-use), [agent basics](https://docs.browser-use.com/open-source/customize/agent/basics)):

```
task → get browser state (DOM + screenshot) → LLM decision → execute actions → evaluate → repeat until done
```

`Agent.run(max_steps=100)` default. Cloud V4 is a hosted version of the same idea with sessions/workspaces; OSS and Cloud APIs are **not interchangeable**. ([docs index](https://docs.browser-use.com/llms.txt))

### 5. Multi-step and error recovery

- `max_steps` cap.
- Production post: checkpoints after every step, Lambda continuation, SQS retries, DLQ. That is **their** infra, not required by the library.
- README: `save_history` / `load_and_rerun` replays clicks/typing without a model per step; extract + summary still call the model; page change raises `RuntimeError`. ([README](https://raw.githubusercontent.com/browser-use/browser-use/main/README.md))
- CAPTCHA: Cloud “stealth + proxies”; **“no browser configuration guarantees that every CAPTCHA can be avoided or solved.”** ([README](https://raw.githubusercontent.com/browser-use/browser-use/main/README.md))
- Custom `@tools.action` can implement human-in-the-loop (`input(...)`). ([tools basics](https://docs.browser-use.com/open-source/customize/tools/basics))

### 6. Session / context

- `BrowserSession` / `Browser`; local Chrome, `Browser.from_system_chrome()`, or `Browser(use_cloud=True)` over CDP. ([README](https://raw.githubusercontent.com/browser-use/browser-use/main/README.md))
- Cloud: session = conversation; workspace = files; profile = cookies. Closing CDP does **not** stop a managed browser. ([llms.txt](https://docs.browser-use.com/llms.txt))
- `sensitive_data` placeholders so the LLM never sees passwords; real values injected into DOM after the LLM call. Domain-scoped secrets. ([sensitive-data](https://docs.browser-use.com/open-source/examples/templates/sensitive-data))
- Follow-up tasks can reuse the same browser (docs index: follow-up-tasks template).

### 7. Explicitly not claimed

- OSS `is_successful` is not an independent verification. ([llms.txt](https://docs.browser-use.com/llms.txt))
- CAPTCHA solving is not guaranteed. ([README](https://raw.githubusercontent.com/browser-use/browser-use/main/README.md))
- Cloud vs OSS APIs differ; do not mix V2/V3/V4 IDs. ([llms.txt](https://docs.browser-use.com/llms.txt))
- Connecting over CDP to Cloud does not stop billing; must `browsers.stop`. ([docs.browser-use.com](https://docs.browser-use.com/))

---

## 3. Stagehand (`browserbase/stagehand`)

Public: [github.com/browserbase/stagehand](https://github.com/browserbase/stagehand) (MIT), docs [docs.stagehand.dev](https://docs.stagehand.dev/v4/basics/observe). Playwright-style `page`/`locator` plus `observe` / `act` / `extract`.

### 1. Perception

README: **“Hybrid accessibility-tree trimming gives agents exactly the page context they need.”** Observe/act/extract use an a11y-centric snapshot; `act` maps LLM choices onto **XPath/CSS selectors**. Page snapshots **merge every frame’s accessibility tree by default**; iframe and shadow DOM are handled without extra config. ([README](https://raw.githubusercontent.com/browserbase/stagehand/main/README.md), [act](https://docs.stagehand.dev/v4/basics/act), [observe](https://docs.stagehand.dev/v4/basics/observe))

`observe()` returns `Action` objects: `{ description, method, arguments, selector }` where `selector` is typically `xpath=/html[1]/...`. ([observe](https://docs.stagehand.dev/v4/basics/observe))

`extract()` can add `screenshot: true` (viewport only, bypasses cache) when visual info is needed **in addition to** the page accessibility tree. ([extract](https://docs.stagehand.dev/v4/basics/extract))

### 2. Click / scroll / type / tab

`act()` is **one action**. Suggested methods ([act](https://docs.stagehand.dev/v4/basics/act)):

| method | example |
|--------|---------|
| `click` / `doubleClick` | click the button |
| `fill` / `type` | fill the field |
| `press` | press Enter |
| `hover` | hover menu |
| `scrollTo` / `nextChunk` / `prevChunk` | scroll |
| `selectOptionFromDropdown` | select from dropdown |
| `dragAndDrop` | drag card |

Pass NL instruction (runs model inference) **or** pass an `Action` from `observe()` (**deterministic, no inference**). `selfHeal` re-infers when a recorded selector breaks. Caching can skip LLM on repeats. ([act](https://docs.stagehand.dev/v4/basics/act), [README](https://raw.githubusercontent.com/browserbase/stagehand/main/README.md))

Tabs/pages: Playwright-style `browser.context.pages()`, `page.goto`. Hosted MCP: `navigate`, `act`, `observe`, `extract`. ([README](https://raw.githubusercontent.com/browserbase/stagehand/main/README.md))

### 3. Page body extraction

`extract(instruction, schema)` — Zod / Pydantic / Go type; result is schema-validated. Scope with `observe()` then `extract(..., { locator })` so the model sees a subtree (token savings). Optional screenshot. Fetch/Search add-ons get markdown **without** a browser. ([extract](https://docs.stagehand.dev/v4/basics/extract), [README](https://raw.githubusercontent.com/browserbase/stagehand/main/README.md))

### 4. Observe → Plan → Act → Verify

Documented composition, not a hidden inner loop:

1. `observe("find the login button")` → actions.
2. Validate (`if (action.method === "click")`).
3. `act(action)` deterministic, or `act("click …")` with inference.
4. `extract` for reading.

Docs: **“Chain single-step calls”**; multi-step = multiple `act`s. Observe can map a workflow upfront and cache. ([observe](https://docs.stagehand.dev/v4/basics/observe), [act](https://docs.stagehand.dev/v4/basics/act))

### 5. Multi-step and error recovery

- Self-heal when selectors break. ([README](https://raw.githubusercontent.com/browserbase/stagehand/main/README.md))
- Cache hit/miss in `metadata.cache`.
- Validate-before-act for destructive buttons. ([observe](https://docs.stagehand.dev/v4/basics/observe))
- Credentials: `observe` to get selectors, then `page.locator(selector).fill(env password)` so **secrets never reach the model**. ([README](https://raw.githubusercontent.com/browserbase/stagehand/main/README.md))

### 6. Session / context

- `localBrowser.launch({ userDataDir })` persists cookies. ([README](https://raw.githubusercontent.com/browserbase/stagehand/main/README.md))
- Browserbase cloud: persistent contexts, session recordings, proxies.
- Runs as an **extension next to the browser** (latency claim). ([README](https://raw.githubusercontent.com/browserbase/stagehand/main/README.md))

### 7. Explicitly not claimed

- `act` is **one** action; it does not orchestrate a whole checkout in one NL string (docs tell you to chain). ([act](https://docs.stagehand.dev/v4/basics/act))
- `text=` locators “not yet supported for extract snapshot scoping.” ([stagehand reference via observe/extract docs](https://docs.stagehand.dev/v4/basics/extract))
- Screenshot extract is viewport-only, not full page. ([extract](https://docs.stagehand.dev/v4/basics/extract))

---

## 4. Chrome DevTools Protocol as used by these tools

### Official stance

[aslushnikov/getting-started-with-cdp](https://raw.githubusercontent.com/aslushnikov/getting-started-with-cdp/master/README.md): **“Think twice before using CDP directly… You'll be better off with Playwright.”** Prefer Puppeteer `CDPSession`. Chromium `--remote-debugging-port` exposes a WebSocket JSON-RPC. Clients attach to **targets** (page, browser, worker) and send `{id, method, params, sessionId}`. Experimental methods change often.

Playwright wraps this: `const client = await page.context().newCDPSession(page); await client.send('Animation.enable')`. ([CDPSession](https://playwright.dev/docs/api/class-cdpsession))

### How the surveyed tools use it

| Tool | Public evidence |
|------|-----------------|
| Playwright / Playwright MCP | Playwright locators + optional `CDPSession`. MCP does not ask the LLM to send raw CDP. |
| browser-use | Direct CDP: `DOMSnapshot.captureSnapshot`, `Page.captureScreenshot`, `get_or_create_cdp_session`. Cloud browsers expose `cdp_url` for Playwright `connect_over_cdp`. ([dom/service.py](https://raw.githubusercontent.com/browser-use/browser-use/main/browser_use/dom/service.py), [docs.browser-use.com](https://docs.browser-use.com/)) |
| Stagehand | Playwright-style driver; a11y snapshot + XPath. Not advertised as a raw-CDP agent API. |
| Nova Act | Glossary: “browser actuator … using Playwright”. SDK `cdp_endpoint_url` to attach. CLI `session trace-start` is CDP tracing. ([glossary](https://docs.aws.amazon.com/nova-act/latest/userguide/glos-chap.html), [aws/nova-act README](https://github.com/aws/nova-act)) |
| Chrome DevTools MCP | Puppeteer + Chrome DevTools frontend capabilities. Tools: `take_snapshot` (a11y tree + uid), `click`/`fill` by uid, optional `click_at` coordinates (`--experimentalVision`). ([tool-reference](https://raw.githubusercontent.com/ChromeDevTools/chrome-devtools-mcp/main/docs/tool-reference.md), [README](https://raw.githubusercontent.com/ChromeDevTools/chrome-devtools-mcp/main/README.md)) |

### Common CDP methods (from those sources, not guessed)

- **Page:** `Page.navigate`, `Page.captureScreenshot` (browser-use actor; getting-started pattern).
- **DOM:** `DOMSnapshot.captureSnapshot` (browser-use).
- **Input:** Playwright/Puppeteer hide `Input.dispatchMouseEvent` / `Input.dispatchKeyEvent`; Chrome DevTools MCP `click_at` is coordinate click (flagged experimental).
- **Accessibility:** Chrome DevTools MCP `take_snapshot` is “text snapshot … based on the a11y tree” with `uid`; Playwright MCP is the same idea via Playwright’s aria snapshot, not a documented raw `Accessibility.getFullAXTree` call in MCP docs.

### Explicitly not claimed

CDP is **high-privilege**, assumed trusted, **not** a stable public Chrome product API for third parties. Direct CDP is unsupported; Chrome points products at DevTools-for-agents, Puppeteer, ChromeDriver. (Chrome protocol viewer index was not successfully loaded here; the aslushnikov README and Playwright docs are the fetched citable sources.)

Attaching CDP to a user’s live Chrome is a **second control plane** (remote-debugging port). That is how browser-use Cloud, Nova Act `cdp_endpoint_url`, Playwright MCP `--extension`, and Chrome DevTools MCP “connect to running Chrome” work. It is **not** how a single in-process Qt WebEngine view is driven unless that view exposes a debug port.

---

## 5. Other public AI browser agents

### Amazon Nova Act

Fetched: [what-is-nova-act](https://docs.aws.amazon.com/nova-act/latest/userguide/what-is-nova-act.html), [glossary](https://docs.aws.amazon.com/nova-act/latest/userguide/glos-chap.html), [aws/nova-act README](https://github.com/aws/nova-act).

| Topic | Public claim |
|-------|----------------|
| Perception | **Observation loop** includes screenshot analysis and context extraction. Traces are HTML with screenshots per step. Trajectory data: prompt, screenshots, response. |
| Primitives | Playwright actuator: click, type, scroll, navigate. SDK also exposes `nova.page` (Playwright `Page`): `screenshot()`, `content()` (DOM), `keyboard.type`. CLI: `click`/`type` (NL), `snapshot` (a11y tree), `screenshot`, `get-content` (text/HTML/markdown), `extract`, `verify`. |
| Extract | Separate `act_get` / schema; “put a prompt to extract information in its own separate act()”. |
| Loop | Glossary **agentic loop**: observe → reason → act → evaluate, until complete or escalate. One `act()` = many **steps**. Default `max_steps=30`. `observation_delay_ms` waits for animations. |
| Recovery | `ActExceededMaxStepsError`, `ActAgentFailed`. State **guardrails** after each observation (URL allow/block). Human approval (screenshot + Approve/Reject). UI takeover (live stream). |
| Session | Browser instance; sequential `act()`s; Playwright `storage_state` cookies; optional localStorage restore. |
| Not claimed | `act()` cannot drive non-browser apps or the **browser window chrome**; native OS modals need a human. Do not put secrets in the model prompt; Playwright-typed secrets can still appear in screenshots. Playwright `goto` “does not always work well with act”. |

### Open Interpreter (public desktop docs)

Fetched: [browser-workflows](https://www.openinterpreter.com/docs/desktop/browser-workflows).

- Drives a **real browser through Playwright**.
- Human owns login; never paste passwords into instructions.
- Approvals before save/submit/delete/refund/send; screenshot before destructive click.
- Re-read state before retry; do not click blindly.
- Prefer visible text / nearby anchors if a selector breaks twice.

This is a **prompting contract** on Playwright, not a published observe/act engine. Other Open Interpreter surfaces (extension, skills) were not used as primary citations here because the fetched page is the official desktop browser-workflow doc.

### Cursor public Browser docs only

Fetched: [cursor.com/docs/agent/tools/browser](https://cursor.com/docs/agent/tools/browser).

**Cited as published product behavior, not internals.**

- Tools named: Navigate, Click (click/double/right/hover), Type, Scroll, Screenshot, Console Output, Network Traffic.
- Screenshots are “integrated directly with the file reading tool” so the agent “sees the browser state as images rather than relying on text descriptions.”
- Logs go to **files the agent greps**, not a dump after every action (token claim).
- Session persistence per **workspace**: cookies, localStorage, sessionStorage, IndexedDB.
- Browser is a “secure web view” “controlled using an MCP server running as an extension.”
- **Tool approval** default: Manual / Allow-listed / Auto-run. Allow/block is “best-effort”; prompt injection is acknowledged. Origin allowlist for enterprise: `browser_navigate` restricted; link/redirect/JS navigation can still leave the allowlist.
- Recommended models listed (Sonnet 4.5, GPT-5, Auto) — not relevant to IRIS local models.

**Not claimed in that page:** how elements are addressed (a11y ref vs coordinates vs DOM), whether an ARIA snapshot exists, CDP usage, or any mapping to Playwright MCP. Forum posts and in-product MCP tool names are **not** treated as Cursor documentation.

### Chrome DevTools for agents (`chrome-devtools-mcp`)

Fetched: [developer.chrome.com/docs/devtools/agents](https://developer.chrome.com/docs/devtools/agents), [README](https://raw.githubusercontent.com/ChromeDevTools/chrome-devtools-mcp/main/README.md), [tool-reference](https://raw.githubusercontent.com/ChromeDevTools/chrome-devtools-mcp/main/docs/tool-reference.md).

- Puppeteer automation + DevTools (performance traces, Lighthouse, console, network, heap).
- Perception: `take_snapshot` a11y tree + `uid`; prefer snapshot over screenshot. `verbose` dumps full a11y tree.
- Act: `click`/`fill`/`hover`/`fill_form` by `uid`; `type_text` into focused field; `press_key`; `click_at` coordinates (experimental vision flag). `includeSnapshot` optional (default false — opposite of Playwright MCP’s auto-snapshot).
- Pages: `list_pages` / `navigate_page` / `select_page` with `pageId`.
- Disclaimer: exposes browser contents to the MCP client; Chrome/Chrome for Testing only officially.
- `--slim` reduces tools. Usage statistics on by default (`--no-usage-statistics`).

This is the **Google-supported** “don’t speak raw CDP” product. Heavy on debugging; many tools (heap, PWA, WebAuthn) are irrelevant to a local assistant browser.

### Skyvern

Fetched: [Skyvern-AI/skyvern README](https://github.com/skyvern-ai/skyvern), skill [SKILL.md](https://github.com/Skyvern-AI/skyvern/blob/main/skyvern/cli/skills/skyvern/SKILL.md).

- Vision LLMs + Playwright; not “only XPath.”
- Swarm of agents: comprehend, plan, execute.
- CLI/skill: `skyvern browser act` uses an **“economy accessibility tree” and “NO screenshots in its LLM reasoning”** for well-labeled elements; visual targets need hybrid/observe. Deterministic `click`/`type` with selectors = 0 LLM.
- Workflows for multi-page production; `run-task` for throwaway exploration.

Fits “NL act without a prior snapshot ref,” at the cost of extra LLM calls and a Playwright browser.

---

## Cross-cutting comparison

| | Perception | Act targeting | Read body | Loop owner | Extra process |
|--|------------|---------------|-----------|------------|---------------|
| Playwright MCP | A11y YAML + refs | ref or locator | Snapshot / find / evaluate | Host LLM MCP loop; auto-snapshot after act | Playwright Chromium (or attach) |
| browser-use | Indexed DOM + screenshot | element index | `extract` LLM, HTML, JS | Inner `Agent.run` | Chromium via CDP |
| Stagehand | Trimmed a11y + XPath | NL `act` or cached Action | Schema `extract` | Caller chains observe/act | Playwright / Browserbase |
| Nova Act | Screenshot + context | NL `act()` → Playwright | `act_get`, `page.content` | Inner agentic loop | Playwright Chrome |
| Chrome DevTools MCP | A11y + uid | uid; optional xy | Snapshot; evaluate | Host LLM | Puppeteer + Chrome |
| Skyvern | Vision and/or economy a11y | NL `act` or selector | `extract` | Workflow / act | Playwright |
| Cursor public docs | Screenshots (+ unspecified targeting) | Click/type/scroll tools | Screenshot, console files | Agent + MCP extension | Cursor browser webview |
| Open Interpreter docs | Human-visible Playwright | Playwright APIs | Re-read page | Human-prompted | Playwright |

**Token/latency (as those projects claim, not measured here):**

- Playwright MCP: a11y text is cheaper than screenshots/DOM dumps; still heavier than CLI+SKILLS. `browser_find` + snapshot `depth` exist to cut tokens. ([snapshots](https://playwright.dev/mcp/snapshots), [introduction](https://playwright.dev/mcp/introduction))
- browser-use: screenshot **every step** unless vision off — expensive for local/small models.
- Stagehand: extra LLM call per NL `act`/`observe`/`extract`; cache and “pass Action to act” avoid that.
- Chrome DevTools MCP: snapshot **not** attached by default (`includeSnapshot` false) — host must call `take_snapshot` again (more round-trips, fewer automatic tokens).

**Untrusted page content:**

- Playwright/Chrome DevTools snapshots **are page text**. None of the fetched MCP READMEs wrap them as “untrusted input / not instructions.” Chrome DevTools MCP warns the client can see anything in the browser.
- browser-use `sensitive_data` filters **secrets you configured**, not prompt injection from the page.
- Stagehand/Nova: keep passwords off the model; screenshots can still leak them (Nova README caution).
- Cursor public docs: prompt injection named; approval + allowlists are best-effort.

**Sensitive actions / HUD:**

- Cursor: explicit tool approval modes. ([Cursor Browser docs](https://cursor.com/docs/agent/tools/browser))
- Nova Act: human approval + UI takeover. ([glossary](https://docs.aws.amazon.com/nova-act/latest/userguide/glos-chap.html))
- Open Interpreter: require approval before destructive clicks. ([browser-workflows](https://www.openinterpreter.com/docs/desktop/browser-workflows))
- Playwright MCP: optional `element` description “used to obtain permission” on click/type — a hook, not a HUD product.
- browser-use: DIY `@tools.action` human ask; `allowed_domains`.

---

## IRIS constraints (from files read, not invented)

Existing structure:

- One process-wide `BrowserSession.execute` over **one QWebEngine** (`session.py`). Commands already match the public primitive set: open, navigate, reload, history, search, click, type, scroll, snapshot, mini_player, media (`types.py`).
- Locators: `ByCss`, `ByText`, `ByRole` (`types.py`).
- Perception today: `BrowserSnapshot` + `Landmark(role, name, bbox)` from `_bridge.js` `querySelectorAll("a[href], button, [role='button'], h1, h2, input, textarea")` **capped at 40**. Not a full a11y tree, no refs.
- Hermes packing: trusted Iris-owned state vs `BEGIN PAGE TEXT (untrusted input data)` wrapping title + landmark names (`observation.py`). Teaching: do not invent page contents; do not use Hermes built-in `browser_*`; HUD for send/purchase; `looks_sensitive_browser_act`.
- Result of every `execute` includes a snapshot; faults become `BrowserPhase.FAULTED` (`session.py`).

Constraints from the parent request (not new IRIS APIs):

1. Keep Hermes tool calling (`iris_invoke` → `browser.*`).
2. Keep existing IRIS IDE + browser UI.
3. Prefer single QWebEngine; Playwright/CDP only if that structure is **proven insufficient**.
4. No regex command-intercept regression.
5. Page content is untrusted input (already started in `observation.py`).
6. Sensitive actions need HUD approval (`looks_sensitive_browser_act` exists).
7. Minimize new processes/deps; local model token/latency.

---

## Fit vs IRIS (do not adopt whole products)

| Approach | Fits Hermes + existing UI | Single QWebEngine | Token/local model | Untrusted wrap | HUD | New processes |
|----------|---------------------------|-------------------|-------------------|----------------|-----|----------------|
| **Playwright MCP pattern** (a11y snapshot + refs + auto-snapshot after act) | Yes, as **observation/locator shape** on existing `browser.*` | **No** if you run `@playwright/mcp` (second Chromium). **Yes** if you **copy the snapshot/ref contract** into `_bridge.js` | Best public evidence for cheap structured perception | Must add; MCP does not | Map `element` permission / Cursor-style approval onto HUD | Zero if pattern-only; large if npm Playwright |
| **browser-use Agent** | No — inner `Agent.run` bypasses Hermes | No — own Chromium/CDP | Screenshots every step: poor for local/small models | Secrets filter ≠ page-injection wrap | Custom tool only | High |
| **Stagehand observe/act** | Extra LLM round-trip per act fights Hermes-as-planner | No — Playwright | Extra inference per primitive | Credentials-off-model is good; still Playwright | Caller validates | High |
| **Nova Act** | Cloud/AWS model + Playwright actuator | No | Cloud | Guardrails + HITL useful as **policy**, not as runtime | Yes (their HUD) | High |
| **Chrome DevTools MCP / Puppeteer** | Competing MCP toolset vs `iris_invoke` | No — Chrome + debug port | Many tools, heap/perf irrelevant | Disclaimer only | None | High |
| **Cursor public surface** | Navigate/click/type/scroll/screenshot + approval | Their webview, not QWebEngine | File-backed logs; screenshots cost vision tokens | Prompt-injection warning | **Yes — copy approval modes** | N/A |
| **Skyvern NL act** | Bypasses explicit locators | No | Extra LLM; vision optional | Not documented as untrusted wrap | Workflow-level | High |
| **Open Interpreter Playwright** | Second browser | No | Depends on host agent | Human login | Approval prompting | High |

**Playwright/CDP as a sibling process is not justified by a gap in IRIS’s command set.** IRIS already has the same verbs MCP core uses. Public agents that “work” on hard sites do so with **a better page representation and a verify-after-act loop**, not because click exists as a Python function. That representation (compact a11y tree + stable refs + snapshot after every action) is implementable in the existing injected `_bridge.js` + `BrowserSnapshot` without opening a debug port.

When would Playwright/CDP become necessary (public evidence, not speculation)?

- Need Firefox/WebKit, network mocking, tracing, or Playwright’s actionability (wait for stable, non-obscured hit target) that QWebEngine JS click cannot match **and** those failures are measured.
- Need to attach to the user’s **system Chrome** profile (browser-use `from_system_chrome`, Playwright MCP `--extension`). That contradicts “same visible QWebEngine page.”
- Canvas-only / non-a11y UIs: Playwright MCP itself then enables **vision coordinates**, which IRIS also should not take as default (token + HUD).

None of those are proven in the files read for this survey.

---

## Recommendation (most feasible for IRIS)

**Keep Hermes as the planner. Keep `iris_invoke` → existing `browser.*` → `BrowserSession` → one QWebEngine. Do not add Playwright, browser-use, Stagehand, Nova Act, or Chrome DevTools MCP as a runtime.**

Copy these **publicly documented contracts**, not their processes:

1. **Perception = compact accessibility snapshot with refs** (Playwright MCP + Chrome DevTools MCP `take_snapshot`). Upgrade landmarks from a flat 40-name list to a YAML/tree with `ref` (or keep `ByRole`/`ByText` and add `ref` as the thing the model echoes). Cap depth like `browser_snapshot { depth }` and search like `browser_find` so local models are not flooded. Continue wrapping the whole tree in `BEGIN PAGE TEXT (untrusted input data)` (`observation.py`).

2. **Every tool result includes a fresh snapshot + `ok`/`detail`** (Playwright MCP auto-snapshot; IRIS `BrowserResult` already has snapshot — pack it into the Hermes observation every time, including failures). Stale ref → error string asking for snapshot, fail closed.

3. **Primitives stay click/type/scroll/navigate/tabs/wait** on locators. Add a **wait-for-text** only if Hermes currently races loads (Playwright `browser_wait_for`). Prefer Playwright’s distinction: fill vs press-sequentially (`slowly`). Scroll can stay IRIS `Scroll(delta)` — Playwright MCP oddly omits core scroll; IRIS is already ahead there.

4. **Loop = Hermes MCP inner loop, not a new `Agent.run`.** That preserves constraint 1 and avoids browser-use’s screenshot-every-step inner agent. Multi-step = multiple `iris_invoke`s; verify by reading `last_ok` + packed page text (already in `PackedBrowserObservation`). Do not restore regex intercept.

5. **HUD for sensitive acts** from Cursor public approval + Nova HITL + Open Interpreter “screenshot/approve before submit,” implemented with existing `looks_sensitive_browser_act` (do not let the model set `confirm=true`). Playwright MCP’s optional `element` description is a good permission string to show in the HUD.

6. **Do not feed screenshots to the local model by default.** Public MCP docs treat screenshots as optional layout, not the click channel. Vision is an opt-in capability everywhere it appears.

7. **Do not enable a second Hermes/Playwright browser.** Teaching text already says so (`observation.py`). Playwright MCP / Chrome DevTools MCP as extra MCP servers would duplicate tools and spawn Chromium.

**Evidence this is the closest public design:** Playwright MCP and Chrome DevTools MCP independently converged on **a11y snapshot + uid/ref + click/fill by that id**, and both tell agents not to click from pixels. That matches IRIS’s existing landmark/locator direction and Hermes tool calling. browser-use/Nova/Stagehand/Skyvern all add **another browser and another planner**, which violate the QWebEngine and Hermes constraints without a measured insufficiency of the current command bus.

What this survey does **not** claim: that QWebEngine JS click equals Playwright actionability on every site; that an a11y tree from `querySelectorAll` equals Chromium `Accessibility.getFullAXTree`; or anything about unpublished ChatGPT/Cursor targeting.

---

## Source list (fetched)

- https://playwright.dev/mcp/introduction
- https://playwright.dev/mcp/snapshots
- https://playwright.dev/mcp/capabilities
- https://raw.githubusercontent.com/microsoft/playwright-mcp/main/README.md
- https://playwright.dev/docs/aria-snapshots
- https://playwright.dev/docs/input
- https://playwright.dev/docs/api/class-cdpsession
- https://docs.browser-use.com/
- https://docs.browser-use.com/llms.txt
- https://docs.browser-use.com/open-source/introduction
- https://docs.browser-use.com/open-source/customize/tools/available
- https://docs.browser-use.com/open-source/customize/tools/basics
- https://docs.browser-use.com/open-source/customize/agent/basics
- https://docs.browser-use.com/open-source/examples/templates/sensitive-data
- https://raw.githubusercontent.com/browser-use/browser-use/main/README.md
- https://browser-use.com/posts/production-architecture-browser-use
- https://raw.githubusercontent.com/browser-use/browser-use/main/browser_use/dom/service.py
- https://raw.githubusercontent.com/browser-use/browser-use/HEAD/browser_use/browser/watchdogs/dom_watchdog.py
- https://docs.stagehand.dev/v4/basics/observe
- https://docs.stagehand.dev/v4/basics/act
- https://docs.stagehand.dev/v4/basics/extract
- https://raw.githubusercontent.com/browserbase/stagehand/main/README.md
- https://docs.aws.amazon.com/nova-act/latest/userguide/what-is-nova-act.html
- https://docs.aws.amazon.com/nova-act/latest/userguide/glos-chap.html
- https://github.com/aws/nova-act
- https://www.openinterpreter.com/docs/desktop/browser-workflows
- https://cursor.com/docs/agent/tools/browser
- https://developer.chrome.com/docs/devtools/agents
- https://raw.githubusercontent.com/ChromeDevTools/chrome-devtools-mcp/main/README.md
- https://raw.githubusercontent.com/ChromeDevTools/chrome-devtools-mcp/main/docs/tool-reference.md
- https://raw.githubusercontent.com/aslushnikov/getting-started-with-cdp/master/README.md
- https://github.com/skyvern-ai/skyvern
- https://github.com/Skyvern-AI/skyvern/blob/main/skyvern/cli/skills/skyvern/SKILL.md
