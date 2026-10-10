"""프로젝트 폴더 — 목록 선택, 위키 이름, 그 아래 채팅."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from iris.knowledge.history_store import record_entry
from iris.knowledge.iris_wiki import IrisWiki
from iris.knowledge.project_wiki import (
    apply_project_rename,
    create_project_wiki,
    project_chat_rel,
    project_index_rel,
    remove_project_wiki,
)
from iris.storage.chat_projects import (
    create_project,
    delete_project,
    list_projects,
    project_for_conversation,
)
from iris.storage.conversations import (
    append_message,
    create_conversation,
    get_conversation,
    start_new_conversation,
)
from iris.storage.database import Database
from iris.ui.monitor.chat_list_select import apply_list_click


class ChatListSelectTests(TestCase):
    def test_ctrl_toggles_and_shift_selects_the_span(self) -> None:
        order = [("c", 1), ("p", 2), ("c", 3), ("c", 4)]
        selected, anchor = apply_list_click(order, [], None, ("c", 1), ctrl=False, shift=False)
        self.assertEqual(selected, [("c", 1)])
        selected, anchor = apply_list_click(order, selected, anchor, ("c", 3), ctrl=True, shift=False)
        self.assertEqual(selected, [("c", 1), ("c", 3)])
        self.assertEqual(anchor, ("c", 3))
        selected, anchor = apply_list_click(order, [("c", 1)], ("c", 1), ("c", 4), ctrl=False, shift=True)
        self.assertEqual(selected, [("c", 1), ("p", 2), ("c", 3), ("c", 4)])
        self.assertEqual(anchor, ("c", 1))


class ChatProjectStoreTests(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self._tmp.name)
        self.db = Database(root / "chat.db")
        self.wiki = IrisWiki(user_root=root / "wiki")

    def tearDown(self) -> None:
        self.db._conn.close()
        self._tmp.cleanup()

    def test_projects_keep_chats_and_rename_history(self) -> None:
        first = create_project(self.db, "알파")
        second = create_project(self.db, "베타")
        self.assertEqual([item.name for item in list_projects(self.db)], ["알파", "베타"])
        create_project_wiki(self.wiki, first.name, first.wiki_slug)
        chat = create_conversation(self.db, project_id=first.id)
        append_message(self.db, chat.id, "user", "프로젝트 안에서 한 말")
        self.assertEqual(project_for_conversation(self.db, chat.id).id, first.id)
        loose = start_new_conversation(self.db, project_id=0)
        self.assertEqual(get_conversation(self.db, loose).project_id, 0)
        again = start_new_conversation(self.db, project_id=first.id)
        self.assertNotEqual(again, loose)

        record_entry(
            self.db,
            kind="chat",
            body="프로젝트 안에서 한 말",
            title="알파 채팅",
            conversation_id=chat.id,
            role="user",
            wiki=self.wiki,
            rel_path=project_chat_rel(first.wiki_slug, chat.id),
        )
        note = self.wiki.user_root / project_chat_rel(first.wiki_slug, chat.id)
        self.assertIn("프로젝트 안에서 한 말", note.read_text(encoding="utf-8"))
        self.assertTrue(str(note).replace("\\", "/").find(f"/projects/{first.wiki_slug}/chats/") > 0)

        renamed = apply_project_rename(self.db, self.wiki, first.id, "알파-개정")
        text = (self.wiki.user_root / project_index_rel(renamed.wiki_slug)).read_text(encoding="utf-8")
        self.assertIn("# 알파-개정", text)
        self.assertIn("- [알파] -> [알파-개정]", text)
        again_named = apply_project_rename(self.db, self.wiki, first.id, "알파-최종")
        text = (self.wiki.user_root / project_index_rel(again_named.wiki_slug)).read_text(encoding="utf-8")
        self.assertIn("- [알파] -> [알파-개정]", text)
        self.assertIn("- [알파-개정] -> [알파-최종]", text)
        moved = self.wiki.user_root / project_chat_rel(again_named.wiki_slug, chat.id)
        self.assertTrue(moved.is_file())

        delete_project(self.db, second.id)
        remove_project_wiki(self.wiki, second.wiki_slug)
        self.assertEqual([item.id for item in list_projects(self.db)], [again_named.id])
