"""Hermes uv mount failure detection / wipe helpers.

실행:
  .venv\\Scripts\\python.exe -m unittest tests.test_hermes_install_bypass -v
  .venv\\Scripts\\python.exe -m iris.system.hermes_install
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iris.system import hermes_install as hi


class HermesInstallBypassTests(unittest.TestCase):
    def test_detect_winerror_448(self) -> None:
        sample = (
            "Downloading cpython-3.11.16-windows-x86_64-none\n"
            "error: Failed to create Python minor version link directory\n"
            "  cause: 경로에 신뢰할 수 없는 탑재 지점이 포함되어 있기 때문에 "
            "경로를 통과할 수 없습니다. (os error 448)\n"
            "[X] Failed to install Python 3.11\n"
            "[X] Installation failed: Python 3.11 not available\n"
        )
        self.assertTrue(hi.looks_like_uv_python_mount_failure(sample))

    def test_detect_negative(self) -> None:
        self.assertFalse(hi.looks_like_uv_python_mount_failure("gateway /health timeout"))

    def test_force_retire_renames_locked_tree(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "hermes"
            agent = home / "hermes-agent"
            (agent / ".git" / "objects").mkdir(parents=True)
            (agent / ".git" / "objects" / "pack.idx").write_text("x", encoding="utf-8")
            with (
                patch.object(hi.gw, "hermes_home", return_value=home),
                patch.object(hi.gw, "stop_hermes_gateway", return_value=True),
                patch.object(hi, "_kill_hermes_tree_holders"),
            ):
                msg = hi.force_retire_hermes_agent()
            self.assertFalse(agent.exists())
            self.assertTrue("치움" in msg or "삭제" in msg, msg)


if __name__ == "__main__":
    unittest.main()
