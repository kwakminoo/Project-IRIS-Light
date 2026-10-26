# Rationale

## Problem

Iris intercepts high-confidence browser phrases in `_try_local_browser_control` / `match_browser_intent` before Hermes, then invokes the same `browser.*` actions the model was supposed to call. The 2026-10-22 postmortem says gemma-class models skip `iris_invoke`, and that changing the system prompt did not produce a tool call. That intercept is an exception sitting *in front of* `hermes_owns_local_intents`, not inside it. The gate stays a pure `bool(hermes_enabled)` for six non-browser intents.

Removing the regex is the goal. The surrounding system makes the shape non-obvious. Chat history stores final prose only, so consecutive commands ("다른 노래", "첫 번째 결과") cannot see the previous snapshot unless this request carries it. Always-on teaching names IDE and wiki and omits `browser.*`. `_workspace_screen_context` names browser tools only after the user is already on that screen. MEMORY and the `iris_invoke` description omit browser. Hermes' built-in page-driving browser toolset is still on (only `terminal` is disabled). `args.confirm=true` is a machine flag the model can self-pass. Prompt-only, with those holes still open, is the failed replacement. Constraints we must keep: same `browser.*` mappings, `media.playing` as play success, no speaker claims, no consent bypass, TTS not imported by browser code, `hermes_owns_local_intents` still a pure bool, `_check_intent.py` rewritten rather than silently deleted.

## Usage (caller's view)

`MainWindow._chat_messages_with_project_context` already POSTs `{model, messages, stream}`. After this change it still does. It appends `browser_teaching_block()` to the always-on system bit on every turn, including the assistant home screen, and inserts `pack_browser_observation(get_browser_session())` next to the user message the way pinned status and attachments already sit there. Trusted fields are url, title, phase, playing, last action, last ok. Landmark text is wrapped as `BEGIN PAGE TEXT (untrusted input data)`.

Hermes then calls existing `iris_invoke` → `browser.search {engine:youtube, play:true}` for 「유튜브에서 노래 틀어줘」. The next user turn reads the same `BrowserSession` instead of hoping the last assistant sentence remembered a watch URL. 「유튜브가 뭐야?」 has no local executor. Sensitive send/purchase reuse `ActionRegistry` confirm, but `run_hud_confirm` is the only yes. `args.confirm` from MCP does not count.

## Shape

The organizing structure is the Hermes request, not a new type zoo. Per **model-the-domain**, the thing that branches today is "what the model sees this turn." `BrowserSession` already models the page. We do not add a second state machine.

One packer record (`PackedBrowserObservation`) and two functions (`pack_browser_observation`, `browser_teaching_block`) are the new public pieces. Per **laziness-protocol** and **minimize-reader-load**, that is the whole addition. Execute, MCP, mini player, and Live Activity stay.

Per **foundational-thinking**, the data that must be right is the POST `messages` list. Trace the dominant paths through it. Cold play needs teaching in that list from home. Consecutive commands need url/title/last result in that list because history dropped the tool JSON. Hostile pages need the untrusted wrap in that list. A type-heavy session object does not get those strings onto the wire.

Per **redesign-from-first-principles**, if browser control had shipped with IDE on 2026-10-01, it would have been named in the always-on block, MEMORY, and `iris_invoke` description, and the competing Hermes browser toolset would have been disabled the way `terminal` is. The October 22 regex is a bolt-on after that teaching was skipped. Put browser in the request those three channels already own.

Per **attack-the-premise**, the failed premise is "more prompt or skill text makes gemma call `iris_invoke` for play." That trial left `browser.*` out of the always-on home-screen bit, left Hermes `browser_navigate` enabled, and packed no observation. This shape tests a different premise. Gemma already calls `iris_invoke` for IDE/wiki from those channels. Browser was omitted. Name it there, kill the sibling browser toolset, pack observation, delete the executor. If a named live Hermes check still shows a skip, that is the same incident. Do not restore regex.

Per **encode-lessons-in-structure**, teaching is one function inserted three times, not three essays. Untrusted is a wrap marker tests can grep, not a reminder sentence. Confirm is a HUD callback. `args.confirm=true` is no longer a legal yes (per **type-system-discipline**, make the self-pass unrepresentable). Per **boundary-discipline**, page text is parsed into the wrap at the packer. `parse_page_url` remains the URL fence. Per **separate-before-serializing-shared-state**, `BrowserSession` is the only writer of snapshot and last result. The packer and `iris_get_state` read. `MainWindow` does not keep a second copy.

Per **subtract-before-you-add** and **migrate-callers-then-delete-legacy-apis**, the intercept and the browser branch of `_workspace_screen_context` go away in the same wave as the packer. Do not land two ways to play YouTube. Per **make-operations-idempotent**, HUD cancel is a no-op on the page. A retry shows the HUD again. `last_result` is whatever `execute` last stored.

Interface depth. Callers of chat still call one POST builder. The packer hides wrap format, landmark cap, and last-result formatting. The twelve `browser.*` names stay visible because the model must emit them. Catalog stays schema-less.

Per **experience-first**, the user watches the same QWebEngine page. Play from the home screen is a tool call, not a Korean template that skips Hermes and TTS. Send/purchase wait on a real HUD.

Per **test-behavior-not-implementation**, `_check_intent.py` asserts intercept absence, home-screen payload contents, untrusted wrap, HUD False despite `confirm=true`, and zero local browser invokes on the four veto chats. Matcher internals go away. Live tool-calling is a named script, not a unit stand-in.

## Synthesis decision

*(Arena fills this section. Left blank on purpose.)*

## Tradeoffs accepted

- We accept that Hermes-off play dies, in exchange for one execution path. Residual Hermes-off play exists only because the intercept never asked the model. `_check_hermes_required.py` already forbids turning Hermes off.
- We accept that gemma may still skip `iris_invoke` after always-on naming, in exchange for not bringing regex back. A named live check reports that miss. Another prompt paragraph is not the next patch.
- We accept HUD on `email.send` / `learning.run` as well as checkout clicks, in exchange for one confirm meaning. Extending only browser would leave the self-pass hole next to the new code.
- We accept that the model's final sentence replaces `format_browser_reply` Korean templates, in exchange for not keeping a second reply owner. Session tests still own `media.playing` and fail-closed blocks.
- We accept packing capped landmarks every POST, in exchange for consecutive "첫 번째 결과" without a mandatory extra snapshot. Empty wrap on a closed page is a few tokens.
- We accept leaving Hermes `web` (`web_search` / `web_extract`) enabled, in exchange for not breaking research citations. Only the page-driving browser toolset is disabled.
- We accept that intercept skip-TTS goes away, in exchange for not special-casing browser in the chat TTS owner. Packer still must not import TTS.

## Alternatives considered

- **Keep regex as a fallback when the model skips.** Two ways to play YouTube. An agent copies whichever it opens first. Rejected. Per **laziness-protocol**, delete the executor.
- **Local compiler (non-regex) that still maps Korean to `browser.*` before Hermes.** Same two-way problem under a new name. Rejected.
- **New observation types on the session (`UntrustedSnapshot`, last observation on `iris_get_state` only) and no request packing.** Consecutive turns then depend on the model calling `iris_get_state` first, which is the skip we are removing. Policy would live in types the POST never sees. Rejected for this shape.
- **Catalog argument schemas as the only teaching.** Catalog today has no args schema. MCP stays three tools. Teaching would move onto `/v1/catalog` while the always-on request still omitted `browser.*` from home. Rejected. This shape puts names in the request Iris already sends.
- **Prompt or skill text without a packer and without disabling Hermes browser.** Already claimed failed in the postmortem. Rejected.
- **Fold browser into `hermes_owns_local_intents`.** The function would sometimes mean "skip intercepts except browser." Breaks `_check_agent_turn_tools.py` and the six-intent bool. Rejected.
- **Playwright or a Hermes sibling browser.** User would watch the wrong page. Skill and postmortem forbid it. Rejected.

## Open questions and risks

- What exact token does the installed Hermes build use for the page-driving toolset (`browser` vs another string)? Vault docs list a Browser category with `browser_navigate` / `browser_snapshot`. Should fill-in fail the self-check if that token is missing rather than guessing `web`?
- Does a YouTube merch "Buy" button false-trigger `looks_sensitive_browser_act` often enough to HUD during play? If yes, should the predicate require checkout-like URL *and* locator text?
- Should the email HUD change ship in the same wave as intercept deletion, or is confirm-hardening a follow-up that still must land before calling browser confirm "done"?
- If the named live Hermes play check fails on the shipped gemma-class model after always-on naming, do we stop and report, or change the default model? This design does not restore a compiler.

## Next implementation step

Add `browser_teaching_block` and `pack_browser_observation`, wire both into `_chat_messages_with_project_context` so a home-screen POST already contains `browser.search` and `BEGIN PAGE TEXT (untrusted input data)`, and self-check that payload before deleting the intercept.
