import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from iris.storage.database import Database
from iris.storage.local_access_prefs import SYSTEM, save_local_read_scope
from iris.system.control_surface import ActionRegistry
from iris.ui.control_actions.local_files import register_local_file_actions


class LocalFileAccessTests(unittest.TestCase):
    def test_default_denies_external_and_system_reads_explicit_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "outside.txt"
            target.write_text("hello-system", encoding="utf-8")
            db = Database(root / "access.db")
            window = SimpleNamespace(
                _db=db,
                _chat_session=SimpleNamespace(attachments=SimpleNamespace(roots={})),
            )
            registry = ActionRegistry()
            register_local_file_actions(window, registry)
            registry.set_human_confirm(lambda spec, args: True)

            denied = registry.invoke("local.read_file", {"path": str(target)})
            self.assertFalse(denied["ok"])

            save_local_read_scope(db, SYSTEM)
            read = registry.invoke("local.read_file", {"path": str(target)})
            self.assertTrue(read["ok"])
            self.assertEqual(read["result"]["content"], "hello-system")
            found = registry.invoke(
                "local.search_files", {"root": str(root), "query": "outside"}
            )
            self.assertEqual(found["result"]["matches"], ["outside.txt"])

            written = registry.invoke(
                "local.write_file",
                {"path": str(root / "new.txt"), "content": "fresh"},
            )
            self.assertTrue(written["ok"], written.get("error"))
            self.assertEqual((root / "new.txt").read_text(encoding="utf-8"), "fresh")
            missing = registry.invoke(
                "local.write_file", {"path": str(root / "no_content.txt")}
            )
            self.assertFalse(missing["ok"])
            self.assertEqual(missing["error"], "content required")
            db._conn.close()


if __name__ == "__main__":
    unittest.main()
