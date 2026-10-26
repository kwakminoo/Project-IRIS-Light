# Rationale. Policy in types, BrowserSession, Control Surface

## Problem

IRIS intercepts high-confidence browser phrases in `_try_local_browser_control` before Hermes. The 2026-10-22 authors wrote that gemma-class models skip `iris_invoke`, and that changing the system prompt does not make the tool fire. The same commit left `hermes_owns_local_intents` as a pure bool for six non-browser intents. Removing the regex is the right product move only if play, pause, search, and multi-step click still run through existing `browser.*` actions on the one `QWebEngineView`, questions still do not drive the page, and follow-ups can see landmarks even though chat history stores final prose only.

The shape is non-obvious because two later fixes that share one premise already failed the same gate. Prompt-only failed. Skill text as documentation failed. A third essay would assume the same premise. `per attack-the-premise`. Constraints that stay: same `browser.*` mappings, `media.playing` as play success, no speaker claims, no consent bypass, TTS stays out of the browser package, the six-intent gate stays a pure bool, `_check_intent.py` is rewritten rather than silently deleted.

## Usage (caller's view)

The consumer is the Hermes inner loop, and the person watching the IDE browser. They do not import an intent matcher. Cold play is `iris_invoke` `browser.search` with `engine=youtube` and `play=true`. Follow-ups call `iris_get_state` and read `browser_observation`. Purchase waits on a HUD the model cannot pass. Three call sites are in DESIGN.md. The type sketch there is derived from those sites. When they disagree, change the types.

## Shape

Data first. Page text becomes `UntrustedObservation` with branded `UntrustedText` and `LandmarkId`. Confirm becomes `ConfirmGate` with `ConfirmChannel.HUMAN_HUD` distinct from email's `MACHINE_FLAG`. Play stays `Search(play=True)` with `YOUTUBE_PLAY_RECIPE` as the one constant. `per foundational-thinking`, `per model-the-domain`.

If this requirement had been day-one, Iris would never have grown a phrase executor beside Hermes, and would never have left landmarks out of `iris_get_state`. Subtract the intercept and the browser paragraph in `_workspace_screen_context`. Then the session last snapshot is the observation store. `per redesign-from-first-principles`, `per subtract-before-you-add`.

Validation stays at `parse_command` and `parse_observation`. `execute` trusts typed commands. The Control Surface handler owns HUD. Session tests do not need Qt dialogs. `per boundary-discipline`.

Illegal states. A stale `ByLandmark.observation_id` cannot click. A landmark name cannot be constructed except by `parse_observation`. `args.confirm=true` cannot be a `HUMAN_HUD` grant because the handler does not read it. `per type-system-discipline`, `per encode-lessons-in-structure`.

One writer. `BrowserSession` already serializes human chrome and agent invokes on one lock. Observation is not copied into chat messages. `_browser_state_fields` is replaced by `session.observation_state()`, not kept beside it. `per separate-before-serializing-shared-state`.

Call chain. MCP → handler → `session.execute`. Deleting `intent.py` removes a layer that hid no policy. `per laziness-protocol`, `per minimize-reader-load`, `per migrate-callers-then-delete-legacy-apis`.

Interface depth. Callers keep three MCP tools. Complexity that moves behind them: wrap, sensitivity, HUD, stale ids, `"음악"` default, YouTube first-result play. Exposed: command names, observation fields, `confirm_required` on a denied HUD result. The API is no larger than today's `iris_get_state` / `iris_invoke` plus the observation object those tools should have returned.

Teaching. Always-on MCP descriptions may name `browser.search` and `iris_get_state.browser_observation`. That is the same channel `ide.enter_companion` already uses, and it is attached every Hermes turn. It is not the `iris-browser` skill, which this repo cannot prove is loaded. MEMORY nudge may list the skill as a helper. Neither nudge nor skill is load-bearing for wrap, HUD, continuity, or intercept absence. `per experience-first` for the person who says play from the home screen and still sees one page.

Hermes built-in browser toolset is disabled next to terminal. One way to drive a page. `per encode-lessons-in-structure`.

## Synthesis decision

TBD

## Tradeoffs accepted

- We accept that a model which never calls tools will not play, in exchange for one execution path and no regex router. Prompt-only already failed. This shape makes the correct invoke obvious in catalog and state. It does not execute on the model's behalf.
- We accept Hermes-off play dying with the intercept, in exchange for not rebuilding tools plumbing the product already closed as 연번 9.
- We accept follow-ups costing an `iris_get_state` call, in exchange for not packing landmarks into chat history that cannot store tool JSON.
- We accept deleting the Korean `format_browser_reply` path, in exchange for one user-visible voice. Hermes prose plus Live Activity. Tests that required the word 스피커 must relax to "must not claim output."
- We accept a purchase classifier that can miss a clever checkout, in exchange for not HUD-gating ordinary YouTube clicks.
- We accept injecting wrapped landmark text into `iris_get_state`, in exchange for consecutive commands working without a second observation copy in the Hermes request.
- We accept `parent=None` for the browser HUD, in exchange for not attaching a modal to frameless `MainWindow`.

## Alternatives considered

- **Keep a local phrase compiler that does not execute, then inject the compiled `iris_invoke` into Hermes.** Looks like a reliability fix for gemma. It is regex command routing under a new name, and it is a second way to choose `browser.search`. Rejected. Two ways to do one task.
- **Pack last snapshot into `_chat_messages_with_project_context` and teach via MEMORY plus skill text.** Hides continuity in the Hermes request. Callers must learn the packer and still call tools. Observation would exist in chat and in the session. Split ownership, and it is the prompt-only premise again. Rejected for this shape.
- **Put argument schemas on every catalog row and treat that as the only policy.** Deep for discovery. It does not wrap untrusted text, does not own last observation, and does not distinguish HUD from `args.confirm`. Callers would still coordinate those rules. Rejected as the home for policy. Catalog derive-from-`command_specs` stays a read model of this shape.
- **`confirm_required=True` on all `browser.click` / `type` / `navigate` using today's machine flag.** Small catalog change. The model self-passes `confirm=true` the way it already can for `email.send`. The FRAME requires a human HUD the model cannot self-pass. Rejected.
- **A grant-token retry after HUD.** Exposes an extra round to callers. Sync HUD inside the handler hides it. Rejected as a shallower public API.

## Open questions and risks

- What string does Hermes use for its built-in browser toolset in `agent.disabled_toolsets`? Terminal is `"terminal"`. If the name is wrong, the sibling stays enabled.
- How aggressive should purchase matching be when a YouTube title contains "Buy"?
- Should `TypeText` into any password field HUD-gate even on a login wall we already fail closed for consent?
- Will `iris_get_state` landmark payloads blow the model context on dense pages? Cap stays 40 from `_bridge.js` unless that number is raised on purpose.
- The recorded gemma skip may still happen. Unit tests cannot prove a live `iris_invoke`. Who runs that proof, and on which model, before the intercept deletion ships?
- Does a frameless-safe HUD with `parent=None` steal focus from the mini player during a purchase confirm?

## Next implementation step

Add `UntrustedObservation`, `parse_observation`, and `session.observation_state()` with a failing check that `iris_get_state` includes wrapped landmarks and `observation_id`, before deleting `_try_local_browser_control`.
