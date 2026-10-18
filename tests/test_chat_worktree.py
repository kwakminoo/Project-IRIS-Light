"""같은 저장소의 둘째 대화는 worktree 로 나뉘고, 본 트리는 그대로다."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from iris.runtime.chat_worktree import (
    describe_for_main,
    is_chat_worktree,
    reset_worktrees,
    work_root_for,
)
from iris.system.win_subprocess import no_window_kwargs


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **no_window_kwargs(),
    )


class ChatWorktreeTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_worktrees()
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "demo"
        self.repo.mkdir()
        _git(self.repo, "init")
        _git(self.repo, "config", "user.email", "kwakmw12@naver.com")
        _git(self.repo, "config", "user.name", "kwakminoo")
        (self.repo / "README.md").write_text("a\n", encoding="utf-8")
        _git(self.repo, "add", "README.md")
        _git(self.repo, "commit", "-m", "init")

    def tearDown(self) -> None:
        reset_worktrees()
        self._tmp.cleanup()

    def test_second_chat_gets_a_worktree_and_main_stays_clean(self) -> None:
        first = Path(work_root_for(1, str(self.repo)))
        second = Path(work_root_for(2, str(self.repo)))
        self.assertEqual(first.resolve(), self.repo.resolve())
        self.assertNotEqual(second.resolve(), self.repo.resolve())
        self.assertTrue(is_chat_worktree(str(second)))
        self.assertTrue((second / "README.md").is_file())
        (second / "only-there.txt").write_text("b\n", encoding="utf-8")
        self.assertFalse((self.repo / "only-there.txt").exists())
        self.assertEqual(Path(work_root_for(1, str(second))).resolve(), self.repo.resolve())
        self.assertEqual(Path(work_root_for(2, str(second))).resolve(), second.resolve())
        quiet = describe_for_main(2, confirm=False)
        loud = describe_for_main(2, confirm=True)
        self.assertFalse(quiet["ok"])
        self.assertFalse(quiet["merged"])
        self.assertTrue(loud["ok"])
        self.assertFalse(loud["merged"])
        self.assertFalse((self.repo / "only-there.txt").exists())
        listed = subprocess.run(
            ["git", "-C", str(self.repo), "worktree", "list", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **no_window_kwargs(),
        )
        trees = [
            Path(line.split(" ", 1)[1]).resolve()
            for line in listed.stdout.splitlines()
            if line.startswith("worktree ")
        ]
        self.assertIn(second.resolve(), trees)
        source = (
            Path(__file__).resolve().parents[1] / "iris" / "runtime" / "chat_worktree.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('"merge"', source)
        self.assertNotIn("'cherry-pick'", source)

    def test_plain_folder_is_unchanged(self) -> None:
        plain = Path(self._tmp.name) / "notes"
        plain.mkdir()
        self.assertEqual(Path(work_root_for(3, str(plain))).resolve(), plain.resolve())
        self.assertFalse(is_chat_worktree(str(plain)))


if __name__ == "__main__":
    unittest.main()
