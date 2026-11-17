"""chat_messages.parts_json persist + legacy hydrate (T1 storage only)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from iris.core.message_parts import (
    TextPart,
    parse_parts,
    parts_display_md,
    parts_to_jsonable,
)
from iris.storage.conversations import (
    ChatMessage,
    append_message,
    create_conversation,
    ensure_chat_schema,
    list_messages,
    message_parts,
)
from iris.storage.database import Database

_SAMPLE_TURN = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "code-review"
    / "scratch-b0-gpt-transcript"
    / "shared"
    / "sample_turn.json"
)


class ChatMessagePartsPersistTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.path = Path(self._tmp.name) / "chat.db"
        self.db = Database(self.path)

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def _reopen(self) -> Database:
        self.db.close()
        self.db = Database(self.path)
        return self.db

    def test_append_parts_round_trips_across_reopen(self) -> None:
        raw = json.loads(_SAMPLE_TURN.read_text(encoding="utf-8"))
        parts = parse_parts(raw["parts"])
        conv = create_conversation(self.db)
        mid = append_message(self.db, conv.id, "assistant", "", parts=parts)

        db2 = self._reopen()
        msgs = list_messages(db2, conv.id)
        self.assertEqual(len(msgs), 1)
        msg = msgs[0]
        self.assertEqual(msg.id, mid)
        self.assertTrue(msg.parts_json)
        loaded = message_parts(msg)
        self.assertEqual(loaded, parts)
        self.assertEqual(parts_to_jsonable(loaded), parts_to_jsonable(parts))

    def test_legacy_empty_parts_json_hydrates_text_from_content(self) -> None:
        conv = create_conversation(self.db)
        append_message(self.db, conv.id, "user", "옛 본문만 있음")
        msgs = list_messages(self.db, conv.id)
        self.assertEqual(len(msgs), 1)
        msg = msgs[0]
        self.assertEqual(msg.parts_json, "")
        self.assertEqual(message_parts(msg), [TextPart(markdown="옛 본문만 있음")])

    def test_content_equals_parts_display_md_when_parts_given(self) -> None:
        raw = json.loads(_SAMPLE_TURN.read_text(encoding="utf-8"))
        parts = parse_parts(raw["parts"])
        expected = parts_display_md(parts)
        conv = create_conversation(self.db)
        append_message(self.db, conv.id, "assistant", "ignored-when-parts", parts=parts)
        msg = list_messages(self.db, conv.id)[0]
        self.assertEqual(msg.content, expected)

    def test_ensure_chat_schema_adds_parts_json_to_legacy_db(self) -> None:
        # Pre-migration schema: chat_messages without parts_json.
        self.db._execute(
            """
            CREATE TABLE chat_conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT '새 채팅',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                title_locked INTEGER NOT NULL DEFAULT 0,
                project_id INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self.db._execute(
            """
            CREATE TABLE chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                model_content TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self.db._execute(
            """
            INSERT INTO chat_conversations(title, created_at, updated_at)
            VALUES('legacy', '2020-01-01T00:00:00', '2020-01-01T00:00:00')
            """
        )
        self.db._execute(
            """
            INSERT INTO chat_messages(conversation_id, role, content, created_at)
            VALUES(1, 'user', '마이그레이션 전', '2020-01-01T00:00:00')
            """
        )
        self.db._commit()

        cols_before = {
            str(row["name"])
            for row in self.db._execute("PRAGMA table_info(chat_messages)").fetchall()
        }
        self.assertNotIn("parts_json", cols_before)

        ensure_chat_schema(self.db)
        cols_after = {
            str(row["name"])
            for row in self.db._execute("PRAGMA table_info(chat_messages)").fetchall()
        }
        self.assertIn("parts_json", cols_after)

        msgs = list_messages(self.db, 1)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].parts_json, "")
        self.assertEqual(message_parts(msgs[0]), [TextPart(markdown="마이그레이션 전")])


if __name__ == "__main__":
    unittest.main()
