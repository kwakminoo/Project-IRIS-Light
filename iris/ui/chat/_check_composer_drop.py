"""Composer 드롭 @경로 변환 · 칩 self-check."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.composer_attachments import composer_chip_label


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    panel = ChatPanel()
    root = Path(__file__).resolve().parents[3]
    panel.set_workspace_root(str(root))
    ref = panel._path_to_at_ref(str(root / "iris" / "ui" / "chat" / "chat_panel.py"))
    assert ref == "@iris/ui/chat/chat_panel.py", ref
    assert panel._path_to_at_ref("@integrations/iris-ide/tsconfig.json") == "@integrations/iris-ide/tsconfig.json"
    folder_ref = panel._path_to_at_ref(str(root / "iris" / "ui" / "chat"))
    assert folder_ref == "@iris/ui/chat", folder_ref
    panel._on_composer_drop_paths(
        [ref, str(root / "iris" / "assets" / "iris_icon.png"), str(root / "iris" / "ui" / "chat")]
    )
    chips = panel._input_area.attachment_strip.paths()
    assert ref in chips, chips
    assert folder_ref in chips, chips
    assert composer_chip_label(ref) == "chat_panel.py", composer_chip_label(ref)
    assert composer_chip_label(folder_ref) == "chat", composer_chip_label(folder_ref)
    assert panel.acceptDrops() is True
    assert panel._log.acceptDrops() is True
    print("composer_drop ok", ref, "folder", folder_ref, "chips", len(chips))
    app.quit()


if __name__ == "__main__":
    main()
