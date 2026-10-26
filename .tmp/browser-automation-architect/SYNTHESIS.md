# Synthesized design — IRIS browser automation v1

## Synthesis decision

**Base: candidate-1** (BrowserSession command bus + Qt WebEngine sole live page).

Cross-judge [8de5ff19](8de5ff19-0c7e-44e1-bf6f-d72099a5bbfc): 29 vs 19. Agreement with parent pick.

**Rejected as v1 owner:** candidate-2 Theia + Playwright CDP attach (Qt-hosted Theia has no proven CDP endpoint; dual-browser fallback risk).

## Grafts from candidate-2

- Named Control Surface actions `browser.open|navigate|reload|back|forward|search|click|type|scroll|snapshot` (aliases → same `session.execute` path)
- `TargetRef` / `BrowserPhase` / `PageUrl` validation (reject `javascript:`)
- Fixture-first `_check_browser_scenarios` + `IRIS_BROWSER_LIVE=1` for live net
- `iris_get_state` fields: `browser_open`, `browser_url`, `browser_title`, `browser_phase`
- Hermes skill `iris-browser` routing note (thin; no Playwright MCP sibling)

## IDE tab (requirement graft without CDP)

Host the browser as a **stack page inside `IrisIdeWindow`** (sibling to Theia/welcome), with URL bar + back/forward/reload. `browser.open` / first navigate switches the IDE window to that page. User watches the same QWebEngine document the agent drives. No nested Theia iframe; no Playwright in v1.

## Public surface

```text
BrowserSession.execute(BrowserCommand) → BrowserResult(snapshot)
BrowserSession.snapshot() / ensure_visible()
Control: browser.* → parse → execute
```

OSS: Qt WebEngine + private JS locator helpers. Playwright deferred until a real CDP endpoint exists.

## Principles

- Laziness Protocol: one session, no second Chromium
- Model the Domain: command union + snapshot
- Experience First: same page human and agent share
- Boundary Discipline: parse at Control Surface
