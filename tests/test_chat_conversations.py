"""대화 세션 저장소 — 세션 분리·제목·되돌리기."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from iris.storage.conversations import (
    DEFAULT_TITLE,
    active_conversation_id,
    append_message,
    clear_conversation_messages,
    create_conversation,
    delete_conversation,
    ensure_active_conversation,
    get_conversation,
    history_dicts,
    list_conversations,
    pop_last_user_message,
    rename_conversation,
    set_active_conversation_id,
    start_new_conversation,
    title_from_text,
)
from iris.storage.database import Database


class ChatConversationTests(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(Path(self._tmp.name) / "chat.db")

    def tearDown(self) -> None:
        # Database는 close()가 없어 WAL 파일이 잠긴 채 남는다 — 연결을 직접 닫는다.
        self.db._conn.close()
        self._tmp.cleanup()

    def test_ensure_active_creates_and_persists(self) -> None:
        cid = ensure_active_conversation(self.db)
        self.assertGreater(cid, 0)
        self.assertEqual(active_conversation_id(self.db), cid)
        # 두 번째 호출은 같은 세션을 재사용한다
        self.assertEqual(ensure_active_conversation(self.db), cid)

    def test_messages_are_scoped_per_conversation(self) -> None:
        first = create_conversation(self.db)
        second = create_conversation(self.db)
        append_message(self.db, first.id, "user", "첫 세션 질문")
        append_message(self.db, first.id, "assistant", "첫 세션 답변")
        append_message(self.db, second.id, "user", "둘째 세션 질문")

        self.assertEqual(
            history_dicts(self.db, first.id),
            [
                {"role": "user", "content": "첫 세션 질문"},
                {"role": "assistant", "content": "첫 세션 답변"},
            ],
        )
        self.assertEqual(
            history_dicts(self.db, second.id),
            [{"role": "user", "content": "둘째 세션 질문"}],
        )

    def test_first_user_message_becomes_title(self) -> None:
        conv = create_conversation(self.db)
        self.assertEqual(conv.title, DEFAULT_TITLE)
        append_message(self.db, conv.id, "user", "IRIS 구조 알려줘")
        append_message(self.db, conv.id, "user", "그다음 질문")
        reloaded = get_conversation(self.db, conv.id)
        assert reloaded is not None
        self.assertEqual(reloaded.title, "IRIS 구조 알려줘")
        self.assertFalse(reloaded.title_locked)

    def test_same_topic_keeps_first_title(self) -> None:
        conv = create_conversation(self.db)
        append_message(self.db, conv.id, "user", "IRIS 창 구조 알려줘")
        append_message(self.db, conv.id, "user", "그럼 패키지 폴더는 어디야?")
        reloaded = get_conversation(self.db, conv.id)
        assert reloaded is not None
        self.assertEqual(reloaded.title, "IRIS 창 구조 알려줘")

    def test_topic_shift_updates_title(self) -> None:
        conv = create_conversation(self.db)
        append_message(self.db, conv.id, "user", "IRIS 창 구조 알려줘")
        append_message(self.db, conv.id, "assistant", "ui/system으로 나뉩니다.")
        append_message(self.db, conv.id, "user", "내일 부산 여행 일정 짜줘")
        reloaded = get_conversation(self.db, conv.id)
        assert reloaded is not None
        self.assertEqual(reloaded.title, "내일 부산 여행 일정 짜줘")
        self.assertFalse(reloaded.title_locked)

    def test_manual_title_is_not_auto_updated(self) -> None:
        conv = create_conversation(self.db)
        append_message(self.db, conv.id, "user", "IRIS 창 구조 알려줘")
        rename_conversation(self.db, conv.id, "내 채팅")
        append_message(self.db, conv.id, "user", "내일 부산 여행 일정 짜줘")
        reloaded = get_conversation(self.db, conv.id)
        assert reloaded is not None
        self.assertEqual(reloaded.title, "내 채팅")
        self.assertTrue(reloaded.title_locked)

    def test_title_from_text_truncates_long_input(self) -> None:
        title = title_from_text("가" * 100)
        self.assertLessEqual(len(title), 36)
        self.assertTrue(title.endswith("…"))

    def test_empty_sessions_are_hidden_except_active(self) -> None:
        used = create_conversation(self.db)
        append_message(self.db, used.id, "user", "질문")
        empty = create_conversation(self.db)

        ids = [c.id for c in list_conversations(self.db)]
        self.assertIn(used.id, ids)
        self.assertNotIn(empty.id, ids)

        ids_with_active = [
            c.id for c in list_conversations(self.db, include_empty_id=empty.id)
        ]
        self.assertIn(empty.id, ids_with_active)

    def test_recent_conversation_is_listed_first(self) -> None:
        older = create_conversation(self.db)
        append_message(self.db, older.id, "user", "예전 질문")
        newer = create_conversation(self.db)
        append_message(self.db, newer.id, "user", "새 질문")
        self.assertEqual(list_conversations(self.db)[0].id, newer.id)

    def test_pop_last_user_message_only_removes_user_tail(self) -> None:
        conv = create_conversation(self.db)
        append_message(self.db, conv.id, "user", "질문")
        append_message(self.db, conv.id, "assistant", "답변")
        self.assertFalse(pop_last_user_message(self.db, conv.id))

        append_message(self.db, conv.id, "user", "실패할 질문")
        self.assertTrue(pop_last_user_message(self.db, conv.id))
        self.assertEqual(
            history_dicts(self.db, conv.id),
            [
                {"role": "user", "content": "질문"},
                {"role": "assistant", "content": "답변"},
            ],
        )

    def test_start_new_conversation_reuses_empty_session(self) -> None:
        first = start_new_conversation(self.db)
        self.assertEqual(start_new_conversation(self.db), first)

        append_message(self.db, first, "user", "질문")
        second = start_new_conversation(self.db)
        self.assertNotEqual(second, first)
        self.assertEqual(active_conversation_id(self.db), second)
        self.assertEqual(history_dicts(self.db, second), [])

    def test_clear_messages_keeps_session_and_resets_title(self) -> None:
        conv = create_conversation(self.db)
        append_message(self.db, conv.id, "user", "질문")
        clear_conversation_messages(self.db, conv.id)
        reloaded = get_conversation(self.db, conv.id)
        assert reloaded is not None
        self.assertEqual(reloaded.title, DEFAULT_TITLE)
        self.assertEqual(reloaded.message_count, 0)

    def test_delete_conversation_removes_messages(self) -> None:
        conv = create_conversation(self.db)
        append_message(self.db, conv.id, "user", "질문")
        delete_conversation(self.db, conv.id)
        self.assertIsNone(get_conversation(self.db, conv.id))
        self.assertEqual(history_dicts(self.db, conv.id), [])

    def test_deleted_active_session_falls_back(self) -> None:
        keep = create_conversation(self.db)
        append_message(self.db, keep.id, "user", "남길 질문")
        active = create_conversation(self.db)
        set_active_conversation_id(self.db, active.id)
        delete_conversation(self.db, active.id)
        self.assertEqual(ensure_active_conversation(self.db), keep.id)
