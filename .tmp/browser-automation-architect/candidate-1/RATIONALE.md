# Rationale — BrowserSession command bus (candidate-1)

## Problem

IRIS needs an IDE-visible browser the agent can drive (search, click, type, scroll, navigate) while the user watches the same surface, without exploding Hermes MCP tools or fighting existing Qt WebEngine / Control Surface rules. The non-obvious part is ownership: today preview escapes to the OS browser, IDE bridge has no browser commands, and WebEngine already powers Theia/email/wiki — so a second automation stack (Playwright) easily becomes a second invisible browser unless one session owns both chrome and agent actions. Hard constraints from grounding: Control Surface contract, off-UI for blocking work (`emulator.*` precedent), `ensure_qt_webengine_ready`, no UI-thread waits, thin `iris_invoke`.

## Usage (caller's view)

Callers never touch QWebEngine. They build or parse a `BrowserCommand` and call `BrowserSession.execute`, or send `browser.invoke` through Control Surface. The toolbar is the same API with `source=human`. Results return a `BrowserSnapshot` that both the panel and the agent trust. Three realistic call sites (MCP invoke, toolbar slots, scenario tests) are in DESIGN.md; the type sketch is derived from those sites.

## Shape

Data structures first: a closed `BrowserCommand` union and one `BrowserSnapshot` carry all domain state that UI flags would otherwise scatter (`can_go_back`, ready, scroll, errors). A single `command_specs()` table is the source of truth for parsers, risk, and Control Surface registration (derive, don't sync). `BrowserSession` is the deep module — public surface is `execute` / `snapshot` / `ensure_visible`; settle timeouts, locator resolution, lazy panel create, and locking live inside. Validation at the wire boundary (`parse_command`); trust typed commands inside (`per boundary-discipline`). Human and agent share one writer lock so concurrent toolbar + tool calls serialize (`per separate-before-serializing-shared-state` — here one session, merge unnecessary). Idempotent navigates and failed history steps leave state well-defined (`per make-operations-idempotent`). Call chain stays three hops: MCP → session → private driver (`per minimize-reader-load`).

OSS: **Qt WebEngine** for the live, user-visible Chromium. Automation is a private `PageDriver` (QWebChannel + injected helpers), not Playwright attached to a headless browser. That choice maximizes “user sees what the agent drives” without a mirror-sync problem. Playwright remains available later as an optional sibling only if CDP depth without Iris chrome is required — outside this candidate's v1 surface.

Interface depth: the public surface is small (one execute + snapshot); complexity hidden includes load settling, locator strategy, thread marshaling, search URL policy, and history capability derivation. Exposed to callers: command kinds and snapshot fields they need to plan next actions.

Deliberately does not: Theia browser tab in v1, per-verb MCP tools, OS `webbrowser.open` for agent flows, or importable driver types.

## Synthesis decision

TBD

## Tradeoffs accepted

- We accept QWebEngine locator/JS automation limits in exchange for one shared visible session with no Playwright mirror sync.
- We accept a single process-wide `BrowserSession` (serialized writers) in exchange for no split-brain between human chrome and agent tools.
- We accept `browser.invoke` as the primary MCP shape (with optional derived aliases) in exchange for thin Hermes tools and one parse path.
- We accept deferring a Theia convenience tab in exchange for avoiding `sync_workspace_build` on the critical path.
- We accept injecting a private bridge script in exchange for encoding click/type/scroll without a second browser runtime.

## Alternatives considered

- **Playwright-first headless + optional screenshot mirror to a panel.** Hides automation power behind Playwright's API but exposes callers to two browsers and sync lag; user does not truly watch the driven page. Lost on interface depth for the *product* requirement (shared visibility) despite deeper *automation* API.
- **Many Control Surface actions (`browser.click`, `browser.type`, …) each owning bits of UI state.** Looks familiar next to `emulator.*` but scatters readiness/history booleans and invites two ways (toolbar vs action) to diverge. Shallower module: callers coordinate verbs and interpret partial state.
- **Theia tab as primary surface with IDE bridge commands.** Fits “IDE-internal” literally but couples every nav/click to bridge polling + bundle rebuild, and still needs a Python automation backend. Exposes transport timing to callers; lost on short call chains and Qt WebEngine readiness rules already solved in-process.

## Open questions and risks

- Which default search engine and locale should `Search` use for the YouTube IU scenario — hard-coded DDG, user setting, or navigate to youtube.com/results?
- How strict should locator failure be (fail command vs return snapshot with `last_error`) for agent retries?
- Should integration tests hit the live network, or record/replay WebEngine fixtures for CI stability?
- Is a future Playwright sibling MCP allowed to attach CDP to *this* WebEngine profile, or must it stay fully separate?
- Do we need agent confirmation (`risk=high`) before navigations off allowlisted hosts?

## Next implementation step

Add `iris/browser/types.py` + `registry.py` with `not implemented` bodies and a failing `test_browser_registry_sync` that locks the command table to Control Surface registration shape.
