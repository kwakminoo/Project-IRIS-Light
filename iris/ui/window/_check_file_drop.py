"""File drop + IDE File-menu wiring self-check."""

from __future__ import annotations

from pathlib import Path
from weakref import WeakSet

from PyQt6.QtWidgets import QApplication, QWidget

from iris.ui.window.file_drop import arm_widget_tree


def main() -> None:
    import sys

    app = QApplication.instance() or QApplication(sys.argv)
    root = QWidget()
    child = QWidget(root)
    armed: WeakSet = WeakSet()

    class Filt(QWidget):
        def eventFilter(self, *_a) -> bool:
            return False

    filt = Filt()
    arm_widget_tree(root, filt, armed)
    assert root.acceptDrops()
    assert child.acceptDrops()
    root = Path(__file__).resolve().parents[3]
    src = root / "integrations" / "iris-ide" / "src" / "browser"
    contrib = (src / "iris-ide-frontend-contribution.ts").read_text(encoding="utf-8")
    module = (src / "iris-ide-frontend-module.ts").read_text(encoding="utf-8")
    assert "CommonMenus.FILE_OPEN" in contrib
    assert "ide.pick_open_folder" in contrib
    assert "WorkspaceOpenHandlerContribution" in contrib
    assert "WorkspaceOpenHandlerContribution" in module
    # ponytail: 소스가 OK여도 구식 bundle.js면 실행에 안 뜸 — 번들 마커 필수
    for label, bundle in (
        ("workspace", root / "integrations" / "iris-ide" / "lib" / "frontend" / "bundle.js"),
        ("install", Path.home() / ".iris-light" / "runtimes" / "iris-ide" / "lib" / "frontend" / "bundle.js"),
    ):
        assert bundle.is_file(), f"missing {label} bundle: {bundle}"
        text = bundle.read_text(encoding="utf-8", errors="ignore")
        assert "iris.ide.openFolder" in text, f"{label} bundle missing iris.ide.openFolder"
        assert "ide.pick_open_folder" in text, f"{label} bundle missing ide.pick_open_folder"
        assert "installComposerDragBridge" in text, f"{label} bundle missing drag bridge"
    print("file_drop_menu ok")
    app.quit()


if __name__ == "__main__":
    main()
