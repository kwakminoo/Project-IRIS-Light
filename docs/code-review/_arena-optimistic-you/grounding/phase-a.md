# Phase A grounding: optimistic You on send

## Problem (user goal)

보내기 직후 채팅에 You가 바로 보여야 한다. 지금은 입력창만 즉시 비고, You는 AttachmentWorker·의도 게이트·`_continue_user_turn_bound` 이후에 뜬다.

## Current flow (measured from source)

1. `ChatPanel._emit_send` — clear input/chips, `send_clicked(payload, attachments)`
2. `MainWindow._on_user_text` — optional `_try_open_at_path_refs`, then `UserTurnDispatcher.submit`
3. `submit` — if session free: `turn_ready` sync → `_dispatch_user_turn` → `_execute_user_turn_body`
4. Body — local intent gates; if `turn.attachments or attached_store.roots`: `AttachmentWorker.start(); return` (**no You yet**)
5. `_continue_user_turn_bound` — `append_message_instant('You', shown)` then material/commit
6. `_commit_recorded_user_turn_bound` — `_record_history` then `_launch_chat_turn` (ChatWorker)

## Constraints

- Do not double-append You when continue path still appends.
- Followthrough turns (`_turn_is_followthrough`) currently skip You append; keep that.
- Voice path uses STT pending completion; do not break.
- Queued turns (`turn_queued`) have no chat bubble today; decide whether optimistic show happens at submit or at turn_ready.
- Workspace panels (`WorkspaceIrisPanel.append_user`) vs main `_chat.append_message_instant` — active surface must match `_showing_bound` / `_active_workspace_iris_panel`.
- Qt slot exceptions = process abort; keep append on UI thread, no new fatals.
- Prefer smallest diff (Laziness); Experience First prefers immediate bubble over prep-first correctness theater.
- Idempotent: second call to show You for same turn must no-op.

## Display text

`_format_user_turn_content(turn)` via `format_user_attachment_block` — available as soon as turn exists (before AttachmentWorker).
