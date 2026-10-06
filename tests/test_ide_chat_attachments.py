"""Explorer paths must become chat chips with their original names intact."""
from pathlib import Path
import tempfile
import unittest

from PyQt6.QtWidgets import QApplication
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.composer_attachments import attachment_filename

APP = QApplication.instance() or QApplication([])


class IdeChatAttachmentTests(unittest.TestCase):
    def test_files_folders_and_workspace_root_keep_exact_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            folder = root / "한글 폴더 #1%"
            folder.mkdir()
            file = folder / "원본 파일.py"
            file.write_text("print('iris')", encoding="utf-8")
            paths = [str(file), str(folder), str(root)]
            panel = ChatPanel()
            try:
                panel.set_workspace_root(str(root))
                received = []
                panel.files_attached.connect(lambda items: received.extend(items))
                panel.attach_drop_paths(paths)
                self.assertEqual(panel._input_area.attachment_strip.paths(), paths)
                self.assertEqual(received, paths)
                self.assertEqual([attachment_filename(p) for p in paths],
                                 [file.name, folder.name, root.name])
                panel.attach_drop_paths(paths)
                self.assertEqual(panel._input_area.attachment_strip.paths(), paths)
            finally:
                panel.deleteLater()
                APP.processEvents()


if __name__ == "__main__":
    unittest.main()
