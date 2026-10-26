# Rationale — Playwright CDP on Theia-sole surface

## Problem

IRIS needs an IDE-visible browser the agent can search, click, type, scroll, and navigate, while Hermes stays on the thin `iris-control` MCP (`iris_invoke`). The stack already has Qt WebEngine (Theia host, wiki, mail) and an IDE bridge without browser commands; docs once rejected Playwright for wiki capture because WebEngine was present. The non-obvious choice is **who owns the document**: a new Python QWebEngine panel (explainer default), a Playwright-launched Chromium mirrored into the IDE, or **one Theia webview with automation attached**. Constraints to honor: off-UI for blocking work (`emulator.*` precedent), `ensure_qt_webengine_ready` only where Qt WebEngine is created (this design avoids a new agent panel), Theia changes need `sync_workspace_build`, Companion HWND rules, and no MCP tool explosion.

## Usage (caller's view)

Hermes discovers `browser.*` via `iris_get_catalog` and drives with `iris_invoke` only — open, navigate, reload, back, forward, search, click, type, scroll, snapshot — getting domain snapshots back. Humans open one Theia Browser tab with URL / reload / back / forward; chrome commits call the same actions. Call sites: `register_browser_actions` → `window.browser_session.*`; Hermes `control.invoke("browser.search", ...)`; Theia address-bar commit → bridge → same session. Types in DESIGN.md are derived from this surface.

## Shape

**Theia `IrisBrowserWidget` is the sole visible surface; Python `BrowserSession` is the sole mutator; Playwright `connect_over_cdp` is a private adapter.** Domain types (`BrowserPhase`, `PageUrl`, `TargetRef`, `ScrollDelta`, `BrowserSnapshot`) encode lifecycle and locator policy so agents cannot pass raw CDP wire or `javascript:` URLs. Validation lives at the Control Surface / parse boundary; Session methods stay pure over domain values and return snapshots. Interface depth: a small `browser.*` set and one Session API hide CDP attach, auto-wait, a11y landmarks, chrome sync, and idempotent open/navigate. Deliberately not done: second Chromium for the agent, sibling Playwright MCP tools, or a Python QWebEngine agent panel. Principles: boundary-discipline, encode-lessons-in-structure, separate-before-serializing-shared-state (one writer), make-operations-idempotent (`ensure_open`), minimize-reader-load (MCP → Session → CDP|bridge).

## Synthesis decision

TBD — filled by arena synthesis. This runner’s candidate is the Theia-sole + CDP-attach shape, not the QWebEngine-panel default.

## Tradeoffs accepted

- We accept Theia/webview CDP endpoint plumbing and `sync_workspace_build` in exchange for one shared document the user actually watches.
- We accept Playwright as a runtime dependency in exchange for role/text locators and waits without inventing a CDP client.
- We accept search-as-navigation-to-a-search-URL policy in exchange for not owning a custom search index.
- We accept fixture-first scenario checks (live YouTube behind a flag) in exchange for CI-stable verification without flaky third-party DOM.
- We accept no Python-side pixel preview of the page in exchange for the IDE tab being the truth (no mirror lag).

## Alternatives considered

- **Python lazy QWebEngine agent panel (+ optional Theia convenience tab)** — hides Qt lifecycle behind Control Surface but exposes a second surface risk and splits “what the user sees” from “what Playwright would attach to” unless carefully mirrored. Shallower shared-document guarantee; lost here because ownership of the document is ambiguous and fights the “user watches the agent” requirement unless both panels are synced (two writers).
- **Playwright-launched headful Chromium + IDE screencast mirror** — deep automation interface, but callers/chrome must treat the mirror as read-only projection; user interaction on the mirror is fake or re-injected. Exposes dual-window / HWND parenting pain under Companion rules; lost on split ownership of input.
- **Sibling Playwright MCP tools (mobile-mcp analogue) plus thin `browser.open` only** — maximizes OSS reuse at the Hermes layer but creates two ways to click and violates thin `iris_invoke` preference; lost on “two ways to do one task.”

## Open questions and risks

- Does the IRIS IDE Theia/Electron (or Qt-hosted) webview expose a stable CDP websocket URL Playwright can `connect_over_cdp` to on Windows without a second Chromium?
- Should `browser.search` hardcode an engine (e.g. DuckDuckGo) or read a user setting — and is YouTube search in-scenario allowed to mean “search engine then click” vs in-site YouTube search?
- If CDP attach is impossible on the Qt WebEngine-hosted Theia shell, do we fall back to Playwright-owned Chromium (other candidate) rather than weaken to two documents?
- How aggressive should landmark snapshots be (size limits) so `browser.snapshot` stays MCP-friendly?

## Next implementation step

Add `BrowserSession` domain types with `NotImplementedError` methods and register off-UI `browser.*` stubs that round-trip parsed args into snapshot-shaped dicts, before any Playwright or Theia widget work.
