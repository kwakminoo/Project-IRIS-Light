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
  Install/update checkout the pin in `PIN` via `load_pinned_sha()` (see `install_iris_agent_*` / `iris_agent_update`).
- New installs write `iris-agent`. Readers prefer `iris-agent` then fall back to
  `hermes-agent`. Soft-fail rename when Windows locks the live tree; do not force-rename.

## Phase F next (package ownership)

**Current = pin + F1 name overlay + F2 CLI shim + F3 overlay rename.** UPSTREAM stays Nous (`https://github.com/NousResearch/hermes-agent.git`). Product owns `PIN`/`UPSTREAM`, checkout write name `iris-agent`. Probe accepts `iris_agent_cli` / `iris_cli` only (dual-accept of `hermes_cli` off when F3 applied). F1 soft-patches `pyproject.toml` name/scripts (`iris-agent` / `iris` → `iris_agent_cli.main`). F3 (`apply_iris_agent_cli_rename_overlay`) copies `hermes_cli` → real `iris_agent_cli` with text rewrite, then replaces physical `hermes_cli` with a reverse shim; `iris_cli` re-exports `iris_agent_cli`. Soft-fail on Windows locks: leave upstream `hermes_cli`, keep real `iris_agent_cli` if copy succeeded; F2 forward shim runs only when F3 did not materialize a real package.

**Next (optional) = Iris-owned remote.** Publish an Iris fork (or absorb a trimmed tree) and point `UPSTREAM` at it. Do not force-rename a live locked Windows tree as a destructive test; overlays remain the install path.

## CVE / rebase procedure

1. Pick a new upstream SHA (release or reviewed commit).
2. Replace `PIN` (and bump any overlay tests).
3. Fresh install or `apply` path: checkout that SHA, run baseline overlays, run `python -m iris.system._check_iris_agent_runtime_phase1`.
4. If a soft-patch no longer applies, fix the overlay/verify before shipping the new pin.
5. Optional later: publish an Iris GitHub fork at the same pin for external review; install URL then switches from Nous to that fork without changing the pin contract.
