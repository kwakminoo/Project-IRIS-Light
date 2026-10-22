"""위키 페이지 메모 — vault 밖 저장."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from iris.storage.wiki_page_memos import PageMemoStore


class WikiPageMemoStoreTests(unittest.TestCase):
    def test_crud_persists_outside_vault(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / "wiki"
            vault.mkdir()
            store = PageMemoStore(root)
            memo = store.add("user/inbox/a.md", "첫 메모")
            self.assertEqual(memo.note_rel, "user/inbox/a.md")
            self.assertEqual(store.count("user/inbox/a.md"), 1)
            again = PageMemoStore(root)
            listed = again.list("user/inbox/a.md")
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0].body, "첫 메모")
            updated = again.update("user/inbox/a.md", memo.memo_id, "수정됨")
            assert updated is not None
            self.assertEqual(updated.body, "수정됨")
            self.assertTrue(again.delete("user/inbox/a.md", memo.memo_id))
            self.assertEqual(again.list("user/inbox/a.md"), [])
            # vault 안에 md를 만들지 않음
            self.assertEqual(list(vault.rglob("*.md")), [])

    def test_notes_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = PageMemoStore(Path(tmp))
            store.add("a.md", "A")
            store.add("b.md", "B")
            self.assertEqual([m.body for m in store.list("a.md")], ["A"])
            self.assertEqual([m.body for m in store.list("b.md")], ["B"])


if __name__ == "__main__":
    unittest.main()
