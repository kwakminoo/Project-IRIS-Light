# Arena frame — IRIS browser: regex intercept → Hermes tool calling

## Artifact

A design package (not code): usage sketch + type signatures + module map + rationale.

Write:

- `DESIGN.md` — caller usage first (2–3 realistic call sites), then types/signatures with `not implemented` bodies, module map, data flow
- `RATIONALE.md` — per rationale-template.md (leave Synthesis decision blank)
- `REJECTED.md` — whole-shape alternatives you considered and rejected, with why

## Problem

Remove `_try_local_browser_control` / `match_browser_intent` as the thing that *executes* browser commands. Hermes/LLM must call `iris_invoke` → existing `browser.*` → `BrowserSession.execute`. Simple play and multi-step (search then click official site) use that same loop. Do not add a second agent or a second browser.

Required user phrases:

- "유튜브에서 노래 틀어줘" → tool call + play (`media.playing`)
- "다른 노래 틀어줘" → uses conversation + current page/state
- "첫 번째 결과 열어줘" → click from current page
- "검색해서 공식 홈페이지 들어가줘" → sequential tools
- "유튜브가 뭐야?" → no browser action

Also: untrusted page content must not be followed as commands. External send / purchase need user approval after they confirm. Keep IDE browser, mini player, Hermes, Live Activity. Minimize extra LLM calls and extra context. Do **not** reintroduce regex command routing for speed.

## Grounding (read these)

- `.tmp/browser-llm-agent-how/GROUNDING.md`
- `.tmp/browser-llm-agent-how/WHY.md`
- `iris/browser/intent.py`, `iris/runtime/agent_local_gate.py`
- `iris/ui/window/main_window.py` `_try_local_browser_control`, `_execute_user_turn_body`, `_workspace_screen_context`, `_chat_messages_with_project_context`
- `iris/mcp/iris_control_stdio.py`, `iris/system/hermes_memory_nudge.py`
- `iris/ui/control_actions/browser.py`, `iris/browser/session.py`, `iris/browser/registry.py`
- `integrations/hermes-skills/iris-control/iris-browser/SKILL.md`

## Constraints from why (Preserve / Change / Avoid / Risk)

Preserve: same `browser.*` mappings; question veto; `media.playing` success; no speaker claims; no consent/signin/age/captcha bypass; ambiguous asks still `iris_invoke`; TTS separate; `hermes_owns_local_intents` stays a pure bool for the six intents; rewrite `_check_intent.py` hook-before-gate rather than delete it silently.

Change: delete regex as executor; model must emit `iris_invoke`; move question-veto to a turn-level test.

Avoid: prompt-only as the replacement (already claimed failed); new agent layer; Playwright sibling; folding browser into `hermes_owns_local_intents`; claiming speakers; treating “기존 도구” as a prior-commit fact.

Risk: gemma-class skip tools again; Hermes-off residual play; over-narrow veto; “스피커” wording in tests.

## Distinctness (mandatory)

Your candidate must be a **whole-shape** alternative, not a point fix. Pick one organizing structure and go all the way:

Examples of *different* structures (do not converge on a mush of all of them):

- Policy in **types/session**: `UntrustedSnapshot`, `confirm_required` on sensitive commands, HUD at ActionRegistry, `iris_get_state` carries last observation so consecutive turns need no chat packing.
- Policy in **the Hermes request Iris already sends**: compact observation packed into messages, MEMORY/nudge/invoke-description teaching, snapshot wrapped like attachments, no new types beyond a small packer.
- Policy in **Control Surface catalog**: argument schemas + risk/confirm as the only teaching the model gets, disable Hermes built-in browser toolset, thin MCP stays 3 tools.

Do **not** hedge toward the other runner. Differences are the signal.

## Rubric (picker only; candidates do not see scores)

1. **Single execution path.** One way to run a browser command. Regex intercept gone. No second agent, no Playwright, no Hermes sibling browser left enabled.
2. **Tool calling is load-bearing.** A cold home-screen play phrase can reach `iris_invoke` without relying on “the skill will be loaded.” Addresses the recorded gemma skip without bringing regex routing back.
3. **Continuity.** Consecutive commands see URL/title/last result/landmarks without hoping chat history remembered a snapshot. History today stores final prose only.
4. **Safety encoded, not prompted.** Page text cannot be treated as user instructions. Purchase/send need a human gate the model cannot self-pass with `confirm=true`.
5. **Interface depth.** Small public surface. Complexity lives in BrowserSession / Control Surface / one packer, not a new router. Call chain stays short.
6. **Testable without a live LLM for the invariants.** Question veto, untrusted wrap, confirm HUD, intercept absence, `media.playing` are unit/self-checkable. Live LLM tool-call is a separate proof, named.

## Discipline

Read architect SKILL.md and runner-prompt.md. Usage first, then types. Validate at boundaries. Encode invariants in types. `not implemented` bodies. Screen yourself against design-red-flags.md (shallow module, two ways to do one task, hand-synced lists, pass-through methods).
