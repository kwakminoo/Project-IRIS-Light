# Synthesis: optimistic You

## Synthesis decision

**Base:** Candidate B (`UserTurn.user_bubble_shown` + `MainWindow._present_user_turn_early`).

**Why:** Smaller public surface (one method, no new module). Latch lives on the turn so queue → body → continue shares state without a side registry. Matches Laziness Protocol and Experience First (queued present).

**Cross-judge:** skipped. Arena pool entries are `auto` / parent-family, so Phase C has no other-family judge.

**Graft from A:**
- Continue path must go through the same idempotent present/skip contract (A's `ensure` idea, implemented as flag check + present).
- Voice: mark-only when STT pending already became the You line (A's `mark_painted` without second append). If `complete_stt_pending` succeeds, call `turn.mark_user_bubble_shown()` so continue does not append again.

**Rejected from A:** `UserBubblePaintRegistry`, `YouBubbleSurface` protocol file, `forget` on finish (turn GC is enough).

**Rejected from B extreme:** forcing every local echo to refactor in this PR beyond a `user_bubble_shown` skip / present share at the known double-append sites.

## Placement

1. `_execute_user_turn_body` after empty-check and followthrough bookkeeping, before local intent gates and AttachmentWorker.
2. `_on_turn_queued` for keyboard (and non-voice) turns so busy-session send still shows You.
3. `_continue_user_turn_bound` skips You append when `turn.user_bubble_shown`.
4. Local You echo sites that still append: skip if already shown, else present or mark after append.

## Verification target

첨부 전송 시 AttachmentWorker 완료 전에 You가 보인다. continue 후 You가 하나다. followthrough·voice STT는 회귀 없다.
