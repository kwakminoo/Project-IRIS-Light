# Why investigator — source control (4a7ae70d)

Question: Why does IRIS intercept high-confidence browser phrases before Hermes?

## Direct

- Entire regex stack is one commit: `3658a305` (2026-10-22, serin + Cursor). Message: `feat(browser): route chat intents through the workspace WebEngine`. No PR, no ticket, no later edits. HEAD of feat/iris-ide-browser is this commit.
- Comments in that commit: `agent_local_gate.py` “브라우저 play/pause/search는 예외 — 소형 모델이 도구를 안 부른다.” `main_window.py` “gemma-class models often skip tool calls. Same browser.* actions as Hermes.”
- Same-commit postmortem `docs/code-review/completed/브라우저-명령-미실행-원인과-개선.md`: AGENT CONNECTED + 「유튜브에서 노래 하나 아무거나 틀어줘」 → gemma4:e2b answered it cannot play, page unchanged. “시스템 프롬프트만 바꿔도 도구는 호출되지 않는다.” Fix: high-confidence phrases invoke `browser.*` regardless of Hermes.
- `hermes_owns_local_intents` (`80d5e34f`, 2026-10-01) was for six non-browser intents (IDE/wiki/PDF/extension/workspace). Browser session did not exist until `62a5a534` (2026-10-19) as an agent tool path, not a chat regex.
- Tests lock: play phrase → youtube play query 음악; questions stay None; hook source-index before `owns`; no speaker claims; no TTS import.

## Preserve if router is removed (from same-commit tests/docs)

- Same `browser.*` actions
- Question skip (유튜브가 뭐야)
- Success = `media.playing`
- No speaker claims; do not bypass consent/signin/age/captcha
- Ambiguous asks still go to model `iris_invoke`

## Contradictions / gaps

- Postmortem says youtube `play` + `tryPlay` were “기존 도구”; git shows they landed in the same commit as the router.
- Gate never listed browser; there was no hook to skip. Path was “no local hook → Hermes.”
- No transcript of “텍스트만 담당한다” in repo. In-app replay of the incident phrase is marked 미실시.
- No PR/gh. GitHub MCP was error for this investigator.

## Constraints for change (planning, not investigator conclusion)

- Prompt-only already claimed failed in the postmortem. Removing regex without making `iris_invoke` actually fire recreates the incident.
- `_check_intent.py` hook-before-gate assertion must be rewritten, not silently deleted, and the question-veto must move to a turn-level test.
- Hermes-off play works today only because of the intercept.
