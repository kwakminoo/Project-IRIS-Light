"""Restart must serve the frontend that was built in the workspace."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from iris.system.iris_ide_runtime import IrisIdeRuntimeManager


class IdeFrontendSyncTests(unittest.TestCase):
    def test_installed_old_bundle_is_replaced_and_stale_build_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "workspace"
            installed = Path(directory) / "runtime"
            files = {
                "src/browser/iris-ide-frontend-contribution.ts": ("source", 100),
                "lib/browser/iris-ide-frontend-contribution.js": ("new URI handler", 200),
                "lib/frontend/bundle.js": ("new bundled URI handler", 300),
            }
            for rel, (content, timestamp) in files.items():
                file = source / rel
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(content)
                os.utime(file, (timestamp, timestamp))
            target = installed / "lib/frontend/bundle.js"
            target.parent.mkdir(parents=True)
            target.write_text("old tree ID handler")
            manager = IrisIdeRuntimeManager()
            with patch("iris.system.iris_ide_runtime.runtime_source_dir", return_value=source), \
                 patch("iris.system.iris_ide_runtime.runtime_install_dir", return_value=installed):
                manager._sync_prebuilt_frontend()
                self.assertEqual(target.read_text(), "new bundled URI handler")
                self.assertEqual((installed / "lib/browser/iris-ide-frontend-contribution.js").read_text(),
                                 "new URI handler")
                # A source edit after compilation must not publish a stale build.
                os.utime(source / "src/browser/iris-ide-frontend-contribution.ts", (400, 400))
                target.write_text("installed newer version")
                manager._sync_prebuilt_frontend()
                self.assertEqual(target.read_text(), "installed newer version")
                # A compilation without a subsequent rebundle is also stale.
                os.utime(source / "src/browser/iris-ide-frontend-contribution.ts", (100, 100))
                os.utime(source / "lib/browser/iris-ide-frontend-contribution.js", (400, 400))
                manager._sync_prebuilt_frontend()
                self.assertEqual(target.read_text(), "installed newer version")


if __name__ == "__main__":
    unittest.main()
