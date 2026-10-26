# Cross-judge — browser automation architect candidates

Readonly arena judgment. Grounding: `GROUNDING.md`. Candidates read in full (`DESIGN.md`, rationale, rejected alternatives).

**Recommended base: candidate-1** (BrowserSession command bus + Qt WebEngine sole live page).

---

## Scores (1–5, higher is better)

For criterion 6, higher = lower shipping risk (safer wrt nested Chromium / dual browsers / sync bugs).

| # | Criterion | Candidate-1 | Candidate-2 |
|---|-----------|:-----------:|:-----------:|
| 1 | Meets user requirements | **4** | **5** |
| 2 | Interface depth | **5** | **3** |
| 3 | Fits IRIS constraints | **5** | **3** |
| 4 | Domain modeling | **5** | **4** |
| 5 | Implementability for v1 | **5** | **2** |
| 6 | Risk (nested Chromium / dual browsers / sync) | **5** | **2** |
| | **Total** | **29** | **19** |

---

### 1. Meets user requirements

**C1 — 4.** Covers agent search/click/type/scroll/navigate, thin `iris_invoke` (`browser.invoke`), user-visible same surface, and three scenario tests. Human chrome (URL / reload / back / forward) is real. Gap vs literal user ask: surface is an Iris `BrowserPanel`, not an IDE/Theia tab. That matches grounding’s explainer default (“Python lazy QWebEngine… Optional Theia tab for human convenience only”) but under-delivers “IDE-internal browser tab” as worded.

**C2 — 5.** On paper hits every bullet: Theia tab with URL/refresh/back/forward, full agent verb set, user watches the driven document, MCP stays on `iris-control`, scenarios A/B/C with fixture + live flag. Strongest requirements coverage *as a design claim*.

---

### 2. Interface depth

**C1 — 5.** Public surface is intentionally tiny: `execute` / `snapshot` / `ensure_visible`. Closed `BrowserCommand` union + private `PageDriver`. Callers never see QWebEngine, settle policy, or locator JS. Control handler is parse + shape only.

**C2 — 3.** Still hides Playwright/CDP (good), but the *public* Session API is a wide method fan-out (`ensure_open`, `close`, `navigate`, `reload`, `back`, `forward`, `search`, `click`, `type_text`, `scroll`, `snapshot`) mirrored as many `browser.*` catalog entries. Complexity is partially pushed into the catalog surface instead of one command bus. Deeper automation adapter, shallower module boundary for callers.

---

### 3. Fits IRIS constraints

**C1 — 5.** Aligns with grounding hard rules: `ensure_qt_webengine_ready` + lazy view, off-UI like `emulator.*`, thin MCP, companion/frameless-safe (Iris workspace page, not IDE child HWND), and **keeps `sync_workspace_build` off the critical path**. Precedent: Control Surface owns `browser.*` contract.

**C2 — 3.** Thin MCP and off-UI prefixes are fine; avoiding a *new* Qt agent panel sidesteps one bootstrap footgun. But v1 *requires* Theia widget + bridge CDP endpoint + `sync_workspace_build` + restart — explicitly taxed by grounding. Open question in its own rationale: Qt-hosted Theia webview may not expose a stable CDP URL Playwright can attach to. That is a constraint-fit risk, not a polish issue.

---

### 4. Domain modeling

**C1 — 5.** One writer (`BrowserSession`), one `BrowserSnapshot` as UI+agent truth, closed command set, `command_specs()` as single registry source (derive ActionSpecs; sync test fails CI). Toolbar binds snapshot only — no scattered `_can_go_back` booleans. Idempotent navigate / failed history edges encoded.

**C2 — 4.** Strong types (`BrowserPhase`, `PageUrl`, `TargetRef`, `ScrollDelta`, landmarks with bbox) and sole-mutator invariant. Slightly weaker encoding of “one way in”: many Session methods vs one `execute(cmd)`, so policy can drift per verb unless discipline holds. Chrome sync path (`browserApplyChrome`) is a second projection channel beside CDP document mutation — modeled as intentional, but it is still two channels to keep coherent.

---

### 5. Implementability for v1 (this repo, no heroic infra)

**C1 — 5.** Path is local: `iris/browser/*`, Control Surface registration, existing WebEngine patterns, optional `@pytest.mark.webengine`. Locator bridge is work, but not new process topology. First step (types + registry + failing sync test) is immediately actionable.

**C2 — 2.** Needs Playwright runtime, Theia `IrisBrowserWidget`, CDP endpoint plumbing on Windows, bridge command round-trips, IDE rebuild/sync, and a fallback story if attach is impossible. That is multi-surface heroic infra for v1 relative to this repo’s proven Control Surface + Qt paths. Fixture harness is good; the attach dependency is not.

---

### 6. Risk of nested Chromium / dual browsers / sync bugs

**C1 — 5 (low risk).** One live page for the feature; human and agent share `execute` under one lock. Explicitly rejects Playwright-mirror and dual writers. Residual risk is locator flakiness / another in-process WebEngine view alongside Theia’s host — not a mirror-sync product bug.

**C2 — 2 (high risk).** Happy path claims one target via CDP attach. Failure mode (no CDP on Qt/Theia shell) pushes toward Playwright-owned Chromium — exactly the dual-browser / mirror trap grounding and both REJECTED notes warn about. Even on success: document via CDP + chrome via bridge snapshot push is a sync seam (URL bar / can_go_* drift under load). Nested debugger + Electron/webview + Playwright attach is a known sharp edge on Windows.

---

## Recommended base + why

**Base: candidate-1.**

It matches grounding’s placement default, maximizes “user sees what the agent drives” without a mirror, keeps Hermes thin, and is shippable as v1 inside existing Python/Qt/Control Surface seams without making Theia rebuild or CDP attach load-bearing. Candidate-2 wins the literal IDE-tab checkbox and Playwright locator depth, but loses on IRIS constraints, v1 implementability, and dual-browser/sync risk — including an unresolved CDP-feasibility question that can invalidate the whole shape.

Use C1’s command bus + WebEngine session as the spine; treat Theia-tab and Playwright attach as optional later grafts only if a proven CDP endpoint exists, not as the v1 owner.

---

## Grafts worth taking from candidate-2 (loser)

1. **`TargetRef` / role·text strategies** — Prefer C2’s locator algebra over ad-hoc CSS-only helpers; implement inside C1’s private `PageDriver` / bridge JS (or later CDP) without widening the public surface.
2. **`BrowserPhase` (CLOSED / OPENING / READY / BUSY / FAULTED)** — Richer than C1’s `ReadyState` alone; fold into `BrowserSnapshot` for agent planning and `iris_get_state`.
3. **`PageUrl.parse` / reject `javascript:`** — Boundary validation C1 should copy into `parse_command` / Navigate.
4. **Fixture-first scenario harness** (`_check_browser_scenarios` + local HTML + `IRIS_BROWSER_LIVE=1`) — Better CI story than “live YouTube or nothing”; keep C1’s three scenarios but adopt C2’s fixture mode.
5. **`iris_get_state` browser_* fields derived from one snapshot** — Explicit agent observability C1 only implies via invoke results.
6. **Landmark bbox (bounded)** — Useful graft for click targeting / agent UI; keep size-capped as C2 notes.
7. **Import/AST guard: control_actions must not import Playwright** — Even if v1 has no Playwright, the check encodes the “no sibling MCP / no leakage” rule.
8. **Deferred Theia convenience tab** — After C1 session works, optional Theia chrome that only posts the same `browser.invoke` / commands (C2’s “chrome → bridge → Session” direction), without making Theia the document owner.

Do **not** graft as v1 defaults: Playwright `connect_over_cdp` as sole driver, per-verb Session method explosion, or `sync_workspace_build` on the critical path.

---

## Red flags that would block shipping

1. **Two live documents** — Any path that launches Playwright Chromium *and* shows a different QWebEngine/Theia page (or URL-mirrors between them). Instant reject for the “user watches the agent” requirement.
2. **UI-thread wait on load/settle** — `QEventLoop` / blocking `execute` on the GUI thread (grounds Qt `qFatal` / freeze class of bugs). Must stay on off-UI workers with short marshaled slots.
3. **CDP-as-hard-dependency without a proven endpoint** — Shipping C2-shaped v1 when Qt-hosted Theia cannot expose `connect_over_cdp` (or attach is flaky on Windows). Do not “fallback” by opening a second browser.
4. **Tool / ownership explosion** — Sibling Playwright MCP tools beside `iris_invoke`, or toolbar mutating WebEngine while agents mutate a different driver. Two ways to click = ship blocker.
5. **Hand-synced action catalogs** — `browser.*` names in Hermes skill, Control Surface, and command table that drift without a derive-or-`_check_*` lock.
6. **Theia bundle needed for first green scenario** — If v1 cannot demonstrate Search→Click→Navigate→Scroll without `sync_workspace_build`, the critical path is wrong for this repo’s IDE rebuild tax.
7. **Locator failure = undefined session state** — Missing fail-closed snapshot / `last_error` / phase FAULTED that leaves history flags and URL bar lying to the user.

---

## Score summary (copy-paste)

```
criterion                         c1  c2
1 requirements                     4   5
2 interface depth                  5   3
3 IRIS constraints                 5   3
4 domain modeling                  5   4
5 implementability v1              5   2
6 dual-browser / sync risk         5   2
TOTAL                             29  19

BASE: candidate-1
```
