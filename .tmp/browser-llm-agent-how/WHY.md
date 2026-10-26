### The Question

Why does IRIS intercept high-confidence browser phrases in `_try_local_browser_control` / `match_browser_intent` *before* Hermes, even though `hermes_owns_local_intents` already sends IDE / wiki / PDF to the model? What forces produced that exception, and what must stay true if the regex router is removed so the LLM tool-calls `browser.*` instead?

### The Code in Question

- `iris/browser/intent.py` (entire file; added in `3658a305`)
- `iris/runtime/agent_local_gate.py` L1–12 (`hermes_owns_local_intents`)
- `iris/ui/window/main_window.py` `_try_local_browser_control` L4168–4199; call site L4512 *before* `owns = hermes_owns_local_intents(...)` at L4518
- Same-commit postmortem: `docs/code-review/completed/브라우저-명령-미실행-원인과-개선.md`

Symbols: `match_browser_intent`, `_try_local_browser_control`, `hermes_owns_local_intents`, `format_browser_reply`, `browser.search`, `iris_invoke`.

### What We Found

- **[Direct]** The authors of `3658a305` (2026-10-22, serin + Cursor; message `feat(browser): route chat intents through the workspace WebEngine`) wrote that the intercept exists because small models skip tool calls. Source: `iris/runtime/agent_local_gate.py` L3, added in that commit: “브라우저 play/pause/search는 예외 — 소형 모델이 도구를 안 부른다.” Same commit, `iris/ui/window/main_window.py` L4171: “gemma-class models often skip tool calls. Same browser.* actions as Hermes.”

- **[Direct]** The same-commit postmortem states the incident and the chosen fix. Source: `docs/code-review/completed/브라우저-명령-미실행-원인과-개선.md` §1. Observation: AGENT CONNECTED, Naver already open, user said 「유튜브에서 노래 하나 아무거나 틀어줘」 → `gemma4:e2b` answered that it could not play, page unchanged. “시스템 프롬프트만 바꿔도 도구는 호출되지 않는다.” Fix named there: high-confidence command sentences invoke the same `browser.*` actions regardless of Hermes. Success is `video` / `media.playing`, not a watch URL.

- **[Direct]** `hermes_owns_local_intents` was specified for six *non-browser* intents, three weeks earlier. Source: `docs/code-review/completed/채팅가로채기-에이전트도구-구현프롬프트.md` L7–21 and L36–38 (the six: IDE on/off, home/mail/calendar/wiki/mic, wiki save, PDF save, GitHub MCP/skill install, photo-to-code + `project.run`). Goal 1: when Hermes is on, those six do not skip the model; the model uses `iris_invoke`. `80d5e34f` (2026-10-01) introduced `iris/runtime/agent_local_gate.py` with docstring “True면 IDE·화면·위키·PDF·확장 설치·사진 코드의 신규 가로채기를 하지 않는다.” The function body is `return bool(hermes_enabled)` and was not changed in `3658a305` except for the browser-exception module comment.

- **[Direct]** The six-intent gate is still a pure boolean. Source: `iris/ui/_check_agent_turn_tools.py` L1, L13–14 (`hermes_owns_local_intents(True) is True`, `False` is `False`). Call-site comment at `main_window.py` L4517: “Hermes가 켜져 있으면 여섯 의도는 모델의 `iris_invoke`.” Browser is not in that list.

- **[Direct]** Browser as an in-process agent tool path predates the chat regex, but the chat regex does not. Source: `62a5a534` (2026-10-19) `feat(browser): add IDE WebEngine session and YouTube mini-player` — “Give the agent one shared in-process page for search, navigate, and click.” That commit already registered `browser.search`. `3658a305` is the first and only commit that adds `iris/browser/intent.py`, `_try_local_browser_control`, `_check_intent.py`, and the hook-before-gate assertion. HEAD of the current branch (`serin` / `feat/iris-ide-browser`) is still `3658a305`; no later edits to the router or the gate.

- **[Direct]** Tests added in `3658a305` lock the intercept’s contracts. Source: `iris/browser/_check_intent.py` L8–57 and `tests/browser/test_browser_intent.py`. Play phrase 「유튜브에서 노래 하나 아무거나 틀어줘」 → `browser.search` `{engine: youtube, play: True, query: "음악"}`. Named track 「아이유 밤편지 틀어줘」 keeps that query. Pause / resume / YouTube search (no `play`) match. 「유튜브가 뭐야」, 「음악을 좋아해」, 「오늘 날씨 어때」, 「코드 리뷰해줘」 stay `None`. Success reply must contain “재생을 시작” and “스피커”. Consent fail reply must mention 동의. `intent.py` must not import TTS / SoVITS. Source-index assertion: `_try_local_browser_control` appears before `owns = hermes_owns_local_intents(...)`.

- **[Direct]** Play success is `media.playing`, and restriction pages are not bypassed. Source: postmortem §1 and §9; `integrations/hermes-skills/iris-control/iris-browser/SKILL.md` L43 and L49 (same commit); `iris/browser/session.py` L249–259 and L361–362 (“verify media playing. No restriction bypass.”); `tests/browser/test_browser_session_unit.py` `test_youtube_play_clicks_first_result` / `test_youtube_play_fails_without_watch`; `format_browser_reply` + `page_block_reason` for consent / signin / age / captcha.

- **[Direct]** Hermes-off has no tools plumbing; the product direction was to require Hermes rather than add that path. Source: postmortem §4 row `openai_compat` / 연번 9 — “Hermes 밖 tools 배관 없음. 설계상 Hermes 필수. 이번 수정은 라우터로 우회.” `iris/ui/_check_hermes_required.py` L1–6: 연번 9 is closed by making Hermes required, so a settings toggle must not come back.

- **[Supported]** The exception is a *pre-gate hook*, not a change to the gate predicate. Evidence: (1) `3658a305` only appended a comment to `agent_local_gate.py` and left `return bool(hermes_enabled)` alone; (2) the turn body calls `_try_local_browser_control` at L4512, then computes `owns` at L4518; (3) `_check_intent.py` L55–57 asserts that source order; (4) the gate’s own tests still require a pure True/False. The record does not say “we chose a hook over changing the boolean,” but every artifact in that commit implements that shape.

- **[Supported]** The authors treated prompt / skill text as already tried and insufficient. Evidence: postmortem §1 (“시스템 프롬프트만 바꿔도 도구는 호출되지 않는다”); §4 rows for Hermes skill `iris-browser` (“play 예시를 문서로만 제공 / 모델이 스킬을 안 따름”) and `_workspace_screen_context` (“프롬프트 ≠ 호출”). Current `main_window.py` L7512–7521 still lists `browser.navigate/search/click/type/scroll/snapshot` on the browser screen and does not mention `play: true` or `browser.media`. The skill at SKILL.md L41–43 documents both the tool shape and the local-route fallback.

### What We Can Reasonably Infer

- **[Inferred]** Given that `80d5e34f` listed six non-browser intents and `62a5a534` added `browser.*` as an *agent* path with no chat regex, the October 22 intercept appears to be a reaction to a Hermes-on play miss rather than a planned carve-out from the original gate. Browser could not have been “owned” by that gate in October 1’s sense: the session and the play flag did not exist yet.

- **[Inferred]** Given the postmortem’s “로컬 가로채기를 건너뛰고 `gemma4:e2b`가 `iris_invoke`를 부르길 기다린다” plus the absence of any pre-`3658a305` `_try_local_browser_control`, the pre-fix path was “no browser hook → fall through to Hermes,” not “the gate listed play and skipped it.” The postmortem’s later phrase “브라우저 play도 여기에 묶여 있었음” (§2) is consistent with that *symptom* (Hermes-on turns reach the model) and inconsistent with the gate’s actual list.

- **[Inferred]** Given `git log -S tryPlay` first hits `3658a305`, and `62a5a534`’s `play` hits are `mini_player` only, the postmortem’s “기존 도구 = `browser.search {engine:youtube, play:true}` + JS `tryPlay`” likely describes the same working session’s play stack, not a prior commit. `browser.search` as search/navigate *was* already there; `play:true` / `tryPlay` / `browser.media` / `media.playing` appear together with the regex.

### Competing Hypotheses

- **Hypothesis:** The intercept sits *before* `hermes_owns_local_intents` so the six-intent boolean can stay a pure `bool(hermes_enabled)` while browser commands still run when Hermes is on.
  - **Evidence for:** Gate body unchanged in `3658a305`; `_check_agent_turn_tools.py` still asserts True/False only; hook-before-`owns` is what `_check_intent.py` locks; module comment names the exception *outside* the function.
  - **Evidence against or missing:** No commit message, PR, or comment says “do not overload the gate.” A one-line special case inside `hermes_owns_local_intents` was available and unused.

- **Hypothesis:** Placement is just the smallest turn-body patch: run a new local handler next to `_try_local_pinned_status`, which already bypasses the gate.
  - **Evidence for:** Call order at `main_window.py` L4510–4518 is pinned-status → browser → (Hermes-offline skill run) → `owns`. Pinned status is another Hermes-independent local answer. No new helper or layer was added.
  - **Evidence against or missing:** The gate comment and postmortem spend their words on gemma skipping tools, not on matching the pinned-status pattern.

- **Hypothesis:** `play:true` / `tryPlay` already existed, the model failed to call them, and the regex was bolted on top of that stack.
  - **Evidence for:** Postmortem §2 “기존 도구”; skill table documents Play YouTube as `browser.search` + `play: true`; `62a5a534` already had `browser.search`.
  - **Evidence against or missing:** `tryPlay` and the `play` flag on `Search` first appear in the same commit as the router. Git cannot split “build play, then wrap it” from “land both at once.” The in-app replay of the incident phrase is marked 미실시 (§8).

### What We Don't Know

- Whether `gemma4:e2b` actually uttered 「텍스트만 담당한다」. That wording is only in the postmortem (§1). A repo search does not find a transcript, log, or chat-message fixture with that sentence. The same postmortem marks the in-app replay of 「아무 노래」 as 미실시.

- Whether a larger / cloud model on the same turn would have called `iris_invoke`. The authors name `gemma4:e2b` and “gemma-class”; they do not report a comparative run.

- Why the authors did not change `hermes_owns_local_intents` itself, or add tools plumbing outside Hermes (연번 9), instead of a regex hook. Those alternatives are visible; the record does not rank them.

- Intra-session order inside `3658a305`: play stack first vs router first. One squashed commit, no PR.

- Issue / ticket tracker: GitHub MCP was in `error` (“failed during live tool discovery”); assigned investigator `3197fc89` stalled; `gh` is not installed. `3658a305` has no PR number. Remote is `https://github.com/kwakminoo/Project-IRIS-Light.git`. This is a coverage gap, not an empty search.

- Long-form documents (Notion): `plugin-notion-workspace-notion` stayed `needsAuth`; `mcp_auth` rejected “already handled.” No workspace query ran. Investigator `564a3d12`.

- Real-time team chat, infrastructure observability, error / exception tracking, and product analytics: no matching MCP in this environment. No independent confirmation of the incident beyond the same-commit write-up.

- People who would know and were not asked: commit author `serin <dlfksmfqwr@gmail.com>` and the Cursor co-author of `3658a305`.

### Sources Consulted

- **Source control history**: `iris/browser/intent.py`, `iris/runtime/agent_local_gate.py`, `iris/ui/window/main_window.py`, `iris/browser/_check_intent.py`, `tests/browser/test_browser_intent.py`, `tests/browser/test_browser_session_unit.py`, `iris/browser/session.py`, `iris/browser/_bridge.js`, `integrations/hermes-skills/iris-control/iris-browser/SKILL.md`, `docs/code-review/completed/브라우저-명령-미실행-원인과-개선.md`. Commits reviewed: `3658a305` (router + postmortem; current HEAD), `80d5e34f` (gate introduced), `62a5a534` (browser session / `browser.search` / mini-player), `f3d7192` (browser comment cleanup; no play flag). `git log -S tryPlay` first hit: `3658a305`. No PR numbers. Code comments in the gate module and `_try_local_browser_control` searched. Investigator: `4a7ae70d`.

- **Issue / ticket tracker**: Not searched to completion. GitHub MCP namespaceStatus `error`; `gh` missing; `3658a305` has no PR number. Investigator `3197fc89` stalled. Gap, not empty search.

- **Long-form documents**: Notion MCP `needsAuth`; no page query ran. In-repo long-form that *was* read: the same-commit postmortem; `docs/code-review/completed/채팅가로채기-에이전트도구-구현프롬프트.md`; `docs/code-review/헤르메스-미경유-채팅기능-현황.md`; `iris/ui/_check_hermes_required.py`. Investigator `564a3d12` (Notion gap).

- **Real-time team chat**: Not searched. No matching MCP available in this environment.

- **Infrastructure observability**: Not searched. No matching MCP available in this environment.

- **Error / exception tracking**: Not searched. No matching MCP available in this environment.

- **Product analytics warehouse**: Not searched. No matching MCP available in this environment.

### Confidence Summary

The named force for the exception is Direct and local: the `3658a305` authors wrote, in the gate comment, the hook docstring, and a same-commit postmortem, that gemma-class models skip `iris_invoke` and that changing the system prompt does not make the tool fire, so high-confidence play/pause/search phrases call the same `browser.*` actions without waiting for Hermes. That this is an *exception to the six-intent gate* rather than a hole *inside* it is Supported by dates and lists (`80d5e34f` never named browser; the hook runs before `owns`; the boolean stayed pure). Two same-commit sentences are loose relative to git: “기존 도구” for `play:true` / `tryPlay`, and “브라우저 play도 여기에 묶여 있었음.” There is no PR, ticket, Notion page, or independent transcript. Whether a non-gemma model would have needed the regex is unanswered.

### Preserve / Change / Avoid / Risk

Constraints for removing the regex so the LLM tool-calls `browser.*`. Only what the tests and docs above actually require. Not a new agent layer.

**Preserve**

- Same actions the intercept already maps, and that the skill documents as the Hermes path: play → `browser.search` `{query, engine: "youtube", play: true}` (empty/filler play query becomes `"음악"`; 「아이유 밤편지 틀어줘」 keeps `아이유 밤편지`); pause / resume → `browser.media` `{action: "pause"|"resume"}`; explicit YouTube / Google search → `browser.search` without `play`; site open → `browser.navigate`. Sources: `_check_intent.py`, `test_browser_intent.py`, SKILL.md L23–42.
- Question / chat veto: 「유튜브가 뭐야」, 「음악을 좋아해」, 「오늘 날씨 어때」, 「코드 리뷰해줘」 must not drive the browser. Sources: `_check_intent.py` L27–33, `test_browser_intent.py` `test_chat_does_not_drive_browser`, postmortem §8 “일반 대화 무조작.”
- Play success = `media.playing` (or `browser_playing`), not merely a `/watch` URL. Ads: say it is an ad; do not call that success. Sources: postmortem §1 / 개선안 2; SKILL.md L43; `session.py` L249–259; `test_youtube_play_clicks_first_result` / `test_youtube_play_fails_without_watch`; `format_browser_reply` play branch.
- Do not claim speaker output. The unittest currently requires the success string to contain “스피커” (today: “스피커 출력까지는 확인하지 않습니다”). The postmortem’s “하지 않은 일” is the weaker rule: do not assert that sound came out. Sources: `test_reply_does_not_claim_speakers`; postmortem §4 / §9.
- Do not bypass consent / signin / age / captcha / autoplay blocks; report them. Sources: postmortem §9; SKILL.md L49; `session.py` L361–362; `format_browser_reply` `_block_text`; `test_page_block_reason`; consent fail assert in `_check_intent.py` L48–49.
- Ambiguous browser asks that the regex would have left as `None` still go to the model’s `iris_invoke`. Source: postmortem §9.
- TTS stays a separate path: the browser reply path does not import or call TTS. Sources: `test_intent_module_does_not_import_tts`; postmortem §1 / §8.
- `hermes_owns_local_intents` remains a pure `bool(hermes_enabled)` for the six intents. Source: `_check_agent_turn_tools.py` L13–14; 채팅가로채기 prompt L36–38.
- The hook-before-gate *assertion* must be rewritten to whatever the new turn-level guarantee is, not deleted so the file goes green. Source: `_check_intent.py` L53–57.

**Change**

- Remove `match_browser_intent` / `_try_local_browser_control` as the thing that executes play/pause/search/open. The model must actually emit `iris_invoke` → those `browser.*` actions.
- Move the question-veto from “regex returns None” to a turn-level test that the model (or a non-regex guard you already have) does not search / play on those four chats.
- Rewrite `_check_intent.py`’s source-index `hook < gate` check to match the new control flow.

**Avoid**

- Prompt-only or skill-text-only as the replacement. The postmortem already states that changing the system prompt does not produce a tool call, and that the `iris-browser` skill’s play example was documentation the model did not follow.
- A new agent layer, a second browser, or a Playwright/Browser Use sibling. Postmortem §6 explicitly does not take those; SKILL.md L7–8 and L50 say not to.
- Folding browser into `hermes_owns_local_intents` so the function sometimes returns False while Hermes is on. That would break the documented six-intent boolean and `_check_agent_turn_tools.py`.
- Silently dropping the hook-before-gate self-check.
- Claiming speakers worked, or bypassing consent / signin / age / captcha.
- Treating “기존 도구” or “play가 게이트에 묶여 있었음” as prior-commit facts when planning the removal.

**Risk**

- Recreating the recorded incident: Hermes on (`AGENT CONNECTED`), high-confidence play phrase, no `iris_invoke`, text refusal, page unchanged. Prompt-only already claimed failed. In-app replay of that phrase was never done.
- Small / gemma-class models skipping tools again. That is the authors’ stated reason for the hook; this investigation has no independent transcript or larger-model comparison.
- Hermes-off (or any non-Hermes backend): 연번 9 still has no tools plumbing; `_check_hermes_required.py` keeps Hermes required in settings. Today’s Hermes-off play works only because the intercept never asks the model. Removing the regex without a tool path there breaks that residual branch even if settings cannot turn Hermes off.
- Over-narrow question veto: only four chats are locked. A model that tool-calls `browser.search` on nearby questions would not fail today’s tests.
- Success-reply wording: `test_reply_does_not_claim_speakers` requires the word “스피커” in the success string. Changing the reply to omit speakers entirely (still honest) would fail that test until it is relaxed to “must not claim output.”
