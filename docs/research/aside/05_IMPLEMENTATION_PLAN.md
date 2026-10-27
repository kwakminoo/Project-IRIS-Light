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

## Phase 1. Packed snapshot

Change `_bridge.js` and the `PageNode` fields so the model sees fewer wrapper nodes and more of: role, name, focused, clickable, iframe id. Raise or replace `NODE_CAP = 40` in `iris/browser/types.py` with a byte budget, not a hard 40.

Do not change ref format `g{gen}e{index}`. `browser.click` and `browser.type` already consume that.

Check: `python -m iris.browser._check_intent` and a fixture page whose 40th control is currently dropped. The packed snapshot must still include that control's ref.

On human tab switch, `BrowserSession.snapshot()` keeps the old `gen` and `nodes` while the view shows a new page (`iris/browser/session.py`). Publish a fresh stamp there, or `browser.click` will use `lastEls` from the previous document. Check: two tabs, switch, then click a ref from the new PAGE TEXT.

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

If only one phase happens, do Phase 1. The 40-node cap is the cheapest miss on dense pages, and it stays inside the current Hermes tool contract.

## Verification after any phase

- `python -m iris.browser._check_intent`
- `python -m iris.ui.browser._check_mini_player` if `ViewHost` code moved
- Confirm workspace and install bundles still contain the IDE markers only if `iris/**` UI that the IDE loads also changed. Browser-only Python does not need an iris-ide rebundle.

No IRIS feature code was changed in the session that wrote this plan.
