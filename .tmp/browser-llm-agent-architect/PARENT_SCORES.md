# Parent scores (Phase D, parallel with cross-judge)

Scored 1–5 from the sketches. Not holistic.

| Criterion | C1 types/session | C2 request packer | Notes |
|---|---|---|---|
| 1 Single execution path | 5 | 5 | Both delete intercept, disable Hermes browser toolset, one execute |
| 2 Tool calling load-bearing | 3 | 4 | C1 cold play still needs the model to call tools; teaching is MCP description (Hermes-injected). C2 names browser.* in the Iris POST that already works for IDE/wiki. Both still fail if gemma never invokes. C2 tests a different premise than prompt-only. |
| 3 Continuity | 3 | 5 | C1 follow-ups need `iris_get_state` first, another skip. C2 packs url/title/last result/landmarks every POST. Same-request sequential invoke is already in both (invoke result snapshot). |
| 4 Safety encoded | 4 | 4 | C1 stronger untrusted (`UntrustedText`, `ByLandmark` stale id). C2 stronger confirm (HUD for all `confirm_required`, email hole closed). Wrap in C2 is structural grep like attachments. |
| 5 Interface depth | 3 | 4 | C1: callers coordinate get_state then invoke (shallow). Many types. C2: two functions, packer hides wrap. Twelve `browser.*` stay visible in both. |
| 6 Testable without live LLM | 4 | 5 | C2 names stub-registry zero invokes on veto chats, POST payload checks, HUD False despite confirm=true, live script as separate proof. C1 mapping table is not binding on the model. |
| **Total** | **22** | **27** | |

## Red flags

**C1.** Follow-up needs two tool calls (get_state, then invoke). That is caller coordination. Extra types (`ObservationId`, `ByLandmark`) without putting observation on the POST the model always sees. Skill/MCP/get_state.browser_play can become three teaching lists unless derived.

**C2.** Teaching block is still a prompt, but wrap and HUD are structural. Confirm has two entry points (`confirm_required` on spec vs `looks_sensitive_browser_act` in browser handler). Sensitive predicate can false-trigger on a YouTube "Buy". Extra tokens every POST.

## Lean

Base: **candidate 2**. Smaller surface. Consecutive commands do not depend on another tool call. Different premise than the failed prompt-only trial.

Grafts from C1 (one or two, not most):

1. Wrap landmark names as untrusted in `iris_get_state` too, or keep get_state landmark-free and only pack (C2 already chose not to dual-teach via get_state). Prefer C1's **ByLandmark + stale observation_id fail-closed** if click-by-name is the injection path.
2. **ConfirmChannel distinct from args.confirm** is already in C2 as HUD-ignores-wire-bool. Graft C1's rule that Actor.HUMAN chrome skips HUD.

Reject from C1: type zoo as the observation store the POST never sees; get_state as the only continuity; YOUTUBE_PLAY_RECIPE as a third catalog.

Await cross-judge. Disagreement means re-read both rationales.
