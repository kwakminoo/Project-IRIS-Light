# Rejected alternatives (this candidate)

Whole-shape alternatives rejected while forming candidate 1. Not other arena runners.

1. **Regex intercept remains the executor, with a better prompt beside it.**  
   That is the current system. It already exists because prompt-only failed. Keeping it is two ways to play a video. Rejected.

2. **Utterance compiler that only suggests `iris_invoke` args, still imported by `MainWindow`.**  
   Same matcher, new name. An agent that opens `intent.py` will call it. Rejected as regex command routing returning, and as importable internals.

3. **Observation packed into the Hermes chat request as a new system block.**  
   Continuity would live in `_chat_messages_with_project_context` instead of `iris_get_state`. History still drops tool JSON, so the packer becomes a second store that must stay in sync with `BrowserSession`. Rejected as split ownership and as another prompt essay.

4. **Catalog argument schemas as the only teaching and the only policy.**  
   Discovery gets better. Untrusted wrap, last snapshot, and HUD-versus-`confirm=true` still have nowhere typed to live. Callers coordinate those themselves. Rejected as the organizing structure.

5. **New browser agent or Hermes sibling loop.**  
   Extra LLM calls, extra context, a second owner of "what the page is." Grounding forbids it. Rejected.

6. **Playwright or a second Chromium, even headed next to the panel.**  
   The user watches the wrong page. `BrowserSession` already drives the visible view. Rejected as two ways to click.

7. **Fold browser into `hermes_owns_local_intents` so the bool is sometimes False while Hermes is on.**  
   Breaks the six-intent contract and `_check_agent_turn_tools.py`. The intercept was a pre-gate hook for a reason. Rejected.

8. **Leave `_check_intent.py` green by deleting the hook-before-gate assert.**  
   Loses the turn-level guarantee. Rejected. Rewrite the file to assert intercept absence, gate purity, and the play recipe.

9. **Keep `format_browser_reply` for Korean success lines after Hermes also speaks.**  
   Two user-visible voices for one result. Rejected. Delete with `intent.py`.

10. **`args.confirm=true` as sufficient approval for purchase and send.**  
    The model already self-passes that flag on email. Rejected for browser. HUD only.

11. **ByLandmark as the only click locator.**  
    Forces `iris_get_state` first, which is good, and breaks `nth=0` first-result clicks unless a landmark id exists. Rejected as too tight. Stale ids still fail closed when ids are used.
