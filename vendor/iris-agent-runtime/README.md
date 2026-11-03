# Iris Agent runtime baseline (Phase 1)

## Choice

**`vendor/iris-agent-runtime`** (not a public GitHub fork).

| Option | Decision |
|---|---|
| GitHub fork | Deferred. No Iris-owned remote fork yet. Revisit when CVE chase needs a public rebase surface. |
| Full in-tree Hermes copy | Rejected for Phase 1. Inflates the Iris repo without owning the loop yet. |
| This vendor pin + overlays | **Chosen.** Product owns pin SHA + Iris soft-patches. Install clones upstream at pin only. |

## Contract

- Pin file `PIN` is the only allowed checkout for install/update.
- Update must not chase Nous `origin/main`.
- Soft-patches (ollama options guard; dead-check verify) land at install/update via `apply_iris_agent_baseline_overlays`. Gateway start does not string-replace agent sources.
- Runtime home is `iris_agent_home()` → `IRIS_AGENT_HOME` or `~/.iris-light/agent` only.
  Legacy `%LOCALAPPDATA%\hermes` is migrate-from (copy, never delete); active writers use product home.
  Install/update checkout the pin in `PIN` via `load_pinned_sha()` (see `hermes_install` / `hermes_update`).

## CVE / rebase procedure

1. Pick a new upstream SHA (release or reviewed commit).
2. Replace `PIN` (and bump any overlay tests).
3. Fresh install or `apply` path: checkout that SHA, run baseline overlays, run `python -m iris.system._check_iris_agent_runtime_phase1`.
4. If a soft-patch no longer applies, fix the overlay/verify before shipping the new pin.
5. Optional later: publish an Iris GitHub fork at the same pin for external review; install URL then switches from Nous to that fork without changing the pin contract.
