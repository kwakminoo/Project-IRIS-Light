"""대화 세션 저장소 — 세션 분리·제목·되돌리기."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from iris.runtime.chat_session import (
    ChatSession,
    should_open_fresh_work_chat,
    workspace_needs_fresh_chat,
)
from iris.storage.conversations import (
    DEFAULT_TITLE,
    TITLE_BASIS_FIRST,
    active_conversation_id,
    append_message,
    clear_conversation_messages,
    create_conversation,
    delete_conversation,
    ensure_active_conversation,
    get_conversation,
    history_dicts,
    list_conversations,
    load_title_basis,
    pop_last_user_message,
    refresh_conversation_title,
    rename_conversation,
    save_title_basis,
    set_active_conversation_id,
    start_new_conversation,
    suggest_title,
    summarize_reply,
    summarize_work_title,
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

    def test_title_stays_blank_until_the_model_names_it(self) -> None:
        from iris.storage.chat_title import apply_generated_title

        conv = create_conversation(self.db)
        self.assertEqual(conv.title, DEFAULT_TITLE)
        question = "PDF 저장하면 프로그램이 꺼지는 문제가 있는데 원인 확인하고 수정해줘"
        append_message(self.db, conv.id, "user", question)
        append_message(self.db, conv.id, "assistant", "저장 직후 종료 경로를 고쳤습니다.")
        waiting = get_conversation(self.db, conv.id)
        assert waiting is not None
        self.assertEqual(waiting.title, DEFAULT_TITLE)
        stored = apply_generated_title(self.db, conv.id, "PDF 저장 종료 오류 수정")
        self.assertEqual(stored, "PDF 저장 종료 오류 수정")
        reloaded = get_conversation(self.db, conv.id)
        assert reloaded is not None
        self.assertEqual(reloaded.title, "PDF 저장 종료 오류 수정")
        self.assertNotIn(question, reloaded.title)
        self.assertFalse(reloaded.title_locked)
        bodies = [item["content"] for item in history_dicts(self.db, conv.id)]
        self.assertNotIn("PDF 저장 종료 오류 수정", bodies)

    def test_user_text_does_not_become_title(self) -> None:
        conv = create_conversation(self.db)
        append_message(self.db, conv.id, "user", "IRIS 구조 알려줘")
        reloaded = get_conversation(self.db, conv.id)
        assert reloaded is not None
        self.assertEqual(reloaded.title, DEFAULT_TITLE)

    def test_first_basis_keeps_first_model_title(self) -> None:
        from iris.storage.chat_title import apply_generated_title

        save_title_basis(self.db, TITLE_BASIS_FIRST)
        conv = create_conversation(self.db)
        append_message(self.db, conv.id, "user", "IRIS 창 구조 알려줘")
        append_message(self.db, conv.id, "assistant", "ui와 system으로 나뉩니다.")
        self.assertEqual(apply_generated_title(self.db, conv.id, "IRIS 구조"), "IRIS 구조")
        append_message(self.db, conv.id, "user", "내일 부산 여행 일정 짜줘")
        append_message(self.db, conv.id, "assistant", "오전에는 해운대를 추천합니다.")
        self.assertEqual(apply_generated_title(self.db, conv.id, "부산 여행 일정"), "IRIS 구조")

    def test_later_model_title_replaces_when_basis_is_last(self) -> None:
        from iris.storage.chat_title import apply_generated_title

        conv = create_conversation(self.db)
        append_message(self.db, conv.id, "user", "IRIS 창 구조 알려줘")
        append_message(self.db, conv.id, "assistant", "ui와 system으로 나뉩니다.")
        apply_generated_title(self.db, conv.id, "IRIS 구조")
        append_message(self.db, conv.id, "user", "내일 부산 여행 일정 짜줘")
        append_message(self.db, conv.id, "assistant", "오전에는 해운대를 추천합니다.")
        apply_generated_title(self.db, conv.id, "부산 여행 일정")
        reloaded = get_conversation(self.db, conv.id)
        assert reloaded is not None
        self.assertEqual(reloaded.title, "부산 여행 일정")
        self.assertFalse(reloaded.title_locked)

    def test_title_exchange_skips_a_greeting_before_the_question(self) -> None:
        from iris.storage.chat_title import title_exchange

        save_title_basis(self.db, TITLE_BASIS_FIRST)
        pair = title_exchange(
            [
                {"role": "assistant", "content": "무엇을 도와드릴까요?"},
                {"role": "user", "content": "IRIS 창 구조 알려줘"},
                {"role": "assistant", "content": "ui와 system으로 나뉩니다."},
            ],
            basis=TITLE_BASIS_FIRST,
        )
        assert pair is not None
        self.assertEqual(pair[0], "IRIS 창 구조 알려줘")

    def test_switching_basis_does_not_rewrite_the_model_title(self) -> None:
        from iris.storage.chat_title import apply_generated_title

        conv = create_conversation(self.db)
        append_message(self.db, conv.id, "user", "IRIS 창 구조 알려줘")
        append_message(self.db, conv.id, "assistant", "첫 답변입니다.")
        apply_generated_title(self.db, conv.id, "IRIS 구조")
        save_title_basis(self.db, TITLE_BASIS_FIRST)
        refresh_conversation_title(self.db, conv.id)
        self.assertEqual(get_conversation(self.db, conv.id).title, "IRIS 구조")
        self.assertEqual(load_title_basis(self.db), TITLE_BASIS_FIRST)
        apply_generated_title(self.db, conv.id, "다른 주제")
        self.assertEqual(get_conversation(self.db, conv.id).title, "IRIS 구조")

    def test_summarize_reply_skips_code_fence(self) -> None:
        title = summarize_reply("```python\nprint(1)\n```\n설치가 끝났습니다. 이어서 실행하세요.")
        self.assertEqual(title, "설치가 끝났습니다.")

    def test_summaries_are_short_work_titles(self) -> None:
        cases = {
            "PDF 저장하면 프로그램이 꺼지는 문제가 있는데 원인 확인하고 수정해줘": "PDF 저장 종료 오류 수정",
            "GitHub 링크를 입력하면 MCP 연결 가능한지 확인하고 없으면 구현해줘": "GitHub MCP 자동 연결 구현",
            "Wiki 검색창에서 선택한 노드를 확대해서 보여주고 싶어": "Wiki 검색 및 노드 확대 기능",
        }
        for question, title in cases.items():
            self.assertEqual(summarize_work_title(question), title)
            self.assertEqual(
                suggest_title([{"role": "user", "content": question}], basis=TITLE_BASIS_FIRST),
                title,
            )
            self.assertEqual(suggest_title([{"role": "user", "content": question}]), DEFAULT_TITLE)
            self.assertLessEqual(len(title), 25)
            self.assertNotEqual(title, question)

    def test_saved_messages_are_not_replaced_by_the_title(self) -> None:
        from iris.storage.chat_title import apply_generated_title, title_exchange, title_messages

        conv = create_conversation(self.db)
        question = "프랜스포머는 뭔지 아는데 어탠션은뭐야?"
        answer = "어텐션은 각 토큰이 서로를 보는 방식입니다."
        append_message(self.db, conv.id, "user", question)
        append_message(self.db, conv.id, "assistant", answer)
        apply_generated_title(self.db, conv.id, "트랜스포머와 어텐션")
        self.assertEqual(
            history_dicts(self.db, conv.id),
            [
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer},
            ],
        )
        pair = title_exchange(history_dicts(self.db, conv.id), basis="last")
        assert pair is not None
        prompt = title_messages(*pair)
        self.assertIn("트랜스포머와 어텐션", prompt[0]["content"])
        self.assertIn(question, prompt[1]["content"])
        self.assertNotIn("트랜스포머와 어텐션", history_dicts(self.db, conv.id)[1]["content"])

    def test_attachment_path_is_left_out_of_the_title_request(self) -> None:
        from iris.storage.chat_title import title_exchange

        pair = title_exchange(
            [
                {
                    "role": "user",
                    "content": '이 pdf 내용을 요약해서 알려줘 [첨부 파일] @"C:/secret/a.pdf"',
                },
                {"role": "assistant", "content": "요약을 마쳤습니다."},
            ],
            basis=TITLE_BASIS_FIRST,
        )
        assert pair is not None
        self.assertNotIn("secret", pair[0])
        self.assertNotIn("첨부", pair[0])
        self.assertNotIn(".pdf", pair[0])

    def test_manual_title_is_not_auto_updated(self) -> None:
        conv = create_conversation(self.db)
        append_message(self.db, conv.id, "user", "PDF 저장하면 프로그램이 꺼지는 문제가 있는데 원인 확인하고 수정해줘")
        append_message(self.db, conv.id, "assistant", "고쳤습니다.")
        rename_conversation(self.db, conv.id, "PDF Export Crash")
        append_message(self.db, conv.id, "user", "내일 부산 여행 일정 짜줘")
        append_message(self.db, conv.id, "assistant", "일정을 정리했습니다.")
        reloaded = get_conversation(self.db, conv.id)
        assert reloaded is not None
        self.assertEqual(reloaded.title, "PDF Export Crash")
        self.assertTrue(reloaded.title_locked)

    def test_launch_chat_keeps_old_history(self) -> None:
        session = ChatSession(self.db)
        session.record("user", "예전 질문")
        session.record("assistant", "예전 답")
        old_id = session.conversation_id
        fresh = session.open_launch_chat()
        self.assertNotEqual(fresh, old_id)
        self.assertEqual(session.history, [])
        self.assertEqual(
            history_dicts(self.db, old_id),
            [
                {"role": "user", "content": "예전 질문"},
                {"role": "assistant", "content": "예전 답"},
            ],
        )
        self.assertIn(old_id, [item.id for item in session.list_items()])

    def test_iris_ide_keeps_current_chat(self) -> None:
        self.assertFalse(
            should_open_fresh_work_chat(
                ide_id="iris_ide",
                prev_active=False,
                prev_root="",
                mode="hero",
                root="",
            )
        )
        self.assertFalse(
            should_open_fresh_work_chat(
                ide_id="iris_ide",
                prev_active=True,
                prev_root="",
                mode="workspace",
                root="C:/proj-a",
            )
        )
        self.assertTrue(
            should_open_fresh_work_chat(
                ide_id="cursor",
                prev_active=True,
                prev_root="",
                mode="workspace",
                root="C:/proj-a",
            )
        )

    def test_workspace_change_asks_for_fresh_chat(self) -> None:
        self.assertTrue(
            workspace_needs_fresh_chat(
                prev_active=False, prev_root="", mode="welcome", root=""
            )
        )
        self.assertTrue(
            workspace_needs_fresh_chat(
                prev_active=True, prev_root="", mode="workspace", root="C:/proj-a"
            )
        )
        self.assertTrue(
            workspace_needs_fresh_chat(
                prev_active=True,
                prev_root="C:/proj-a",
                mode="workspace",
                root="C:/proj-b",
            )
        )
        self.assertFalse(
            workspace_needs_fresh_chat(
                prev_active=True,
                prev_root="C:/proj-a",
                mode="workspace",
                root="C:/proj-a",
            )
        )

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
