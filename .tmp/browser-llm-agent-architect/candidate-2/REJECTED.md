# Rejected shapes

Whole-shape alternatives this candidate considered and discarded. Not other arena runners.

## Regex intercept as a reliability patch

Keep `_try_local_browser_control` / `match_browser_intent` for play/pause/search, and "also" teach Hermes.

This is the current HEAD. It is two ways to do one task. The local path skips Hermes, TTS, and followthrough, freezes Qt during YouTube waits, and never packs observation for the next model turn. An agent that opens `intent.py` will keep adding phrases there. Rejected so chat drives the page only through Hermes `iris_invoke` into `BrowserSession.execute`.

A non-regex local compiler (intent classifier, small constrained decode) is the same shape. Still an executor in front of the model. Rejected with the regex.

## Prompt-only, skill-only, or workspace-context-only

Put more sentences in `_workspace_screen_context` or `iris-browser/SKILL.md` and delete the intercept.

The postmortem already states that changing the system prompt did not produce a tool call, and that the skill's play example was documentation the model did not follow. Workspace context also fires only when `workspace_mode == "browser"`, so a cold home-screen 「유튜브에서 노래 틀어줘」 never sees it. No observation packing. Hermes built-in `browser_navigate` stays enabled. This is the failed premise, not a variant of packing. Rejected.

## Policy in new session types, not in the request

Add `UntrustedSnapshot`, store last observation on `BrowserSession` for `iris_get_state`, mark `confirm_required` on commands, and skip packing into `messages`.

That hides policy in types a later turn never sees unless the model calls `iris_get_state` first. Gemma skipping that call is the original incident. Consecutive 「첫 번째 결과」 would depend on a tool the model already fails to emit. Catalog/session types also do not disable the Hermes sibling browser or name `browser.*` on the home-screen POST. Extra types without a packer leak the same hole. Rejected.

This candidate still stores `last_result` on the existing session, as a *read* for the packer. That is not a parallel teaching channel.

## Policy in Control Surface catalog schemas

Give `/v1/catalog` argument schemas and risk/confirm, and treat the catalog as the only teaching. Thin MCP stays three tools.

Catalog today is `{name, summary, risk, confirm_required}`. Adding schemas is a new contract every action must keep in sync with `parse_command`. The model still has to *choose* `iris_invoke` on a home-screen play phrase. That choice is taught by the always-on request, MEMORY, and the tool description, which currently omit browser. Schema-on-catalog without packing observation also leaves consecutive turns blind. Rejected. This shape names `browser.*` in the request Iris already sends and leaves the catalog schema-less.

## Fold browser into `hermes_owns_local_intents`

Return False for browser while Hermes is on, or split the predicate by intent.

The gate is a documented six-intent bool. `_check_agent_turn_tools.py` asserts `True`/`False` only. Browser never belonged in that list (`80d5e34f` predates `browser.*` play). Overloading it creates a second meaning for the same function. Rejected. Delete the pre-gate hook instead. Leave the bool alone.

## Second agent or second browser

A Playwright MCP, Browser Use, or Hermes `browser_navigate` / `browser_snapshot` sibling next to `BrowserSession`.

The user watches one `QWebEngineView`. A second driver clicks a page they cannot see. The skill and the postmortem forbid it. Disabling the Hermes browser toolset is part of this design because leaving it on *is* this rejected shape. Do not disable Hermes `web` (`web_search` / `web_extract`). That is research search, not a second visible page.

## Tools plumbing outside Hermes

Keep play working when Hermes is down by teaching Ollama / OpenAI-compat workers to call `browser.*`.

연번 9 closed that path by making Hermes required. `_check_hermes_required.py` fails if a settings toggle returns. A second tool loop on the non-Hermes backend is two ways again. Rejected. Hermes-off play that works today only because of the intercept is an accepted loss.

## Confirm as `args.confirm=true` with a comment asking the model not to self-pass

Reuse `ActionSpec.confirm_required` as it is, and prompt the model not to set `confirm` until the user agrees.

The model is the attacker of that flag. HUD `run_hud_confirm` is unused for these actions today. A prompt cannot encode "the human clicked yes." Rejected. Extend `ActionRegistry.invoke` so the wire bool is ignored and the HUD callback is the only yes. That also closes the hole on `email.send` instead of inventing a browser-only token type.

## Keep `format_browser_reply` as a parallel chat owner

Let Hermes invoke `browser.*`, then replace the model's sentence with the Korean template.

Two reply owners. Tests that require the word "스피커" in a local template would keep a dead module alive. Rejected. Play success stays `media.playing` on the session result. Prose is the model's, bound by teaching (no speaker claims, ads are ads, consent fail-closed).
