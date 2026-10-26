# Synthesized design. Base candidate 2 + two grafts from candidate 1

## Synthesis decision

**Base: candidate 2** (Hermes-request packer). Cross-judge [a0376408](a0376408-4b53-4da5-9b8b-eb9bfb5c320e): 26 vs 23. Parent scores: 27 vs 22. Agreement.

This problem is a wire problem. Typed observation the next POST never sees is policy the model can skip.

Read candidate-2 DESIGN.md as the usage sketch. Deltas below override it.

## Grafts from candidate 1

1. **Page-origin strings are untrusted.** `trusted_block` holds only Iris-owned facts: `phase`, `playing`, `last_action`, `last_ok`, `last_detail`. URL may stay as a parsed session URL. **Title and landmark names** go through the same wrap (`BEGIN PAGE TEXT (untrusted input data)`), never in the trusted block. Optional `ByLandmark` + stale `observation_id` fail-closed if click-by-id is implemented; click-by-text still exists. Do not add a ConfirmChannel enum zoo.

2. **`command_specs()` is the one verb list.** `browser_teaching_block()` derives names from specs. Do not hand-write `browser.open/navigate/…`. `_check_intent.py` greps those derived names in the POST / MCP description.

## Keep from candidate 2

- Delete `_try_local_browser_control` / `match_browser_intent` / `format_browser_reply` as executors in the same wave as the packer.
- `pack_browser_observation` + `browser_teaching_block` in `_chat_messages_with_project_context` on **every** Hermes turn, including home screen.
- `BrowserSession.last_result()` is the only extra session reader. Packer and `iris_get_state` do not become two evolving schemas. Keep get_state thin (url/title/phase/playing) unless you share one formatter with the packer.
- `ActionRegistry.invoke` ignores `args.confirm` when `confirm_required`. HUD callback is the only yes. Browser handler also HUDs `looks_sensitive_browser_act` (purchase/send). `Actor.HUMAN` chrome skips HUD.
- Disable Hermes page-driving browser toolset next to `terminal`. Do not disable `web`.
- `hermes_owns_local_intents` stays `return bool(hermes_enabled)`.
- Rewrite `_check_intent.py`. Do not delete it so CI goes green.
- Live tool-call proof is a named script, not a unit stand-in. Gemma skip → report. Do not restore regex.
- Email HUD UX is a follow-up. Registry ignore-wire-confirm is in this wave.

## Reject

Regex fallback, utterance compiler, get_state-only follow-ups, title-as-trusted, second agent, Playwright, folding browser into the gate, skill/MEMORY as the only discovery path, `args.confirm` as approval.

## Fill-in order (each step ends in a check)

1. Packer + `last_result` + teaching derived from `command_specs`. Wire into POST. Self-check home-screen payload contains `browser.search`, `play`, wrap markers, title not in trusted block. Intercept still present.
2. MEMORY + `iris_invoke` description point at the same teaching function. Disable Hermes browser toolset. Drop `_workspace_screen_context` browser paragraph.
3. `set_human_confirm`. Ignore `args.confirm`. Sensitive browser HUD. Tests: confirm=true + HUD False → ok=false.
4. Delete intercept and `intent.py` executors. Rewrite `_check_intent.py` and `tests/browser/test_browser_intent.py`. Drop gate browser-exception comment. Assert four veto chats reach launch with zero local browser invokes.
5. Run session unit tests + named live Hermes play check if the gateway is up. If live skip, report. No compiler.
