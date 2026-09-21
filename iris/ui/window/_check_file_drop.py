"""File drop + IDE File-menu wiring self-check."""

from __future__ import annotations

from pathlib import Path
from weakref import WeakSet

from PyQt6.QtWidgets import QApplication, QWidget

from iris.ui.window.file_drop import arm_widget_tree


def check_chat_attach_action() -> None:
    """탭 컨텍스트 메뉴가 부르는 경로 — 컴포저까지 실제로 도달하는지."""
    from unittest.mock import MagicMock

    from iris.system.control_surface import ActionRegistry
    from iris.ui.control_bindings import _register_actions

    window = MagicMock()
    surface = MagicMock()
    surface.registry = reg = ActionRegistry()
    _register_actions(window, surface)

    out = reg.invoke("chat.attach", {"path": r"C:\proj\src\app.py"})
    assert out["ok"] is True, out.get("error")
    window._attach_os_drop_paths.assert_called_once_with([r"C:\proj\src\app.py"])

    assert reg.invoke("chat.attach", {})["ok"] is False, "빈 경로가 통과함"

    window._attach_os_drop_paths.return_value = False
    assert reg.invoke("chat.attach", {"path": "x.py"})["ok"] is False, "채팅 패널 부재가 성공으로 보고됨"


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

    # IDE 익스플로러 드래그가 실제로 넘기는 것 — Chromium DropData → QMimeData
    from PyQt6.QtCore import QMimeData

    from iris.ui.window.file_drop import mime_has_attachable, paths_from_mime

    mime = QMimeData()
    mime.setText("@src/app.py")
    mime.setData("text/x-iris-ref", b"@src/app.py")
    assert mime_has_attachable(mime)
    assert paths_from_mime(mime) == ["@src/app.py"], paths_from_mime(mime)

    plain = QMimeData()
    plain.setText("@src/app.py")
    assert paths_from_mime(plain) == ["@src/app.py"], "text/plain 단독 경로가 끊김"

    root = Path(__file__).resolve().parents[3]
    src = root / "integrations" / "iris-ide" / "src" / "browser"
    contrib = (src / "iris-ide-frontend-contribution.ts").read_text(encoding="utf-8")
    module = (src / "iris-ide-frontend-module.ts").read_text(encoding="utf-8")
    assert "CommonMenus.FILE_OPEN" in contrib
    assert "ide.pick_open_folder" in contrib
    assert "WorkspaceOpenHandlerContribution" in contrib
    assert "WorkspaceOpenHandlerContribution" in module
    # 탭은 Lumino 때문에 HTML5 dragstart가 없다 — companion DnD 우회 + 탭 pointer 제스처
    assert "SHELL_TABBAR_CONTEXT_MENU" in contrib, "탭 첨부 메뉴가 사라짐"
    assert "chat.drag_start" in contrib, "companion drag_start 우회가 사라짐"
    assert "chat.drag_end" in contrib, "companion drag_end 우회가 사라짐"
    assert "NAVIGATOR_CONTEXT_MENU" in contrib, "탐색기 첨부 메뉴가 사라짐"
    assert "onTabPointerDown" in contrib, "탭 pointer 제스처가 사라짐"
    assert "onTabHtml5DragStart" in contrib, "탭 HTML5 copy 드래그가 사라짐"
    assert "urisFromDragDataTransfer" in contrib, "Theia MIME 읽기가 사라짐"
    assert "patchDataTransferForCompanionDrag" in contrib, "Theia setData 가로채기가 사라짐"
    assert "getDraggedEditorUris" in contrib, "Theia explorer MIME 계약이 사라짐"
    assert "resolveControlIdentity" in (src / "iris-ide-bridge-identity.ts").read_text(encoding="utf-8")
    check_chat_attach_action()
    check_chat_drag_actions()
    check_finish_keeps_pending_outside()
    check_win_shell_drop_arm()
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
        assert "iris.ide.attachToChat" in text, f"{label} bundle missing attach-to-chat"
        assert "chat.drag_start" in text, f"{label} bundle missing chat.drag_start"
        assert "chat.drag_end" in text, f"{label} bundle missing chat.drag_end"
        assert "getDraggedEditorUris" in text or "theia-editor-dnd" in text, f"{label} missing editor dnd MIME"
    print("file_drop_menu ok")
    app.quit()


def check_chat_drag_actions() -> None:
    """companion DnD 우회 액션 — drag_start 보관 → drag_end 첨부."""
    from unittest.mock import MagicMock

    from iris.system.control_surface import ActionRegistry
    from iris.ui.control_bindings import _register_actions

    window = MagicMock()
    window._finish_ide_companion_drag.return_value = [r"C:\proj\a.py"]
    surface = MagicMock()
    surface.registry = reg = ActionRegistry()
    _register_actions(window, surface)

    out = reg.invoke("chat.drag_start", {"paths": [r"C:\proj\a.py"]})
    assert out["ok"] is True, out.get("error")
    window._begin_ide_companion_drag.assert_called_once_with([r"C:\proj\a.py"])

    end = reg.invoke("chat.drag_end", {"paths": [r"C:\proj\a.py"]})
    assert end["ok"] is True and end["result"]["attached"] == [r"C:\proj\a.py"]
    window._finish_ide_companion_drag.assert_called_once_with([r"C:\proj\a.py"])

    assert reg.invoke("chat.drag_start", {})["ok"] is False


def check_win_shell_drop_arm() -> None:
    """WS_EX_ACCEPTFILES가 실제로 켜지는지 — OLE 침묵 시 WM_DROPFILES 우회."""
    import sys

    if sys.platform != "win32":
        return
    import ctypes

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QMainWindow

    from iris.ui.window.win_shell_drop import enable_shell_file_drop

    win = QMainWindow()
    win.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
    win.resize(200, 100)
    win.show()
    QApplication.instance().processEvents()
    hwnd = int(win.winId())
    assert enable_shell_file_drop(hwnd)
    ex = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
    assert ex & 0x00000010, f"WS_EX_ACCEPTFILES missing: 0x{ex & 0xFFFFFFFF:08x}"
    win.close()


def check_finish_keeps_pending_outside() -> None:
    """탭 조기 drag_end: 커서 밖이면 pending 유지 (소실 금지)."""
    from unittest.mock import MagicMock, patch

    from PyQt6.QtCore import QPoint, QRect

    window = MagicMock()
    # 실제 메서드 바인딩
    from iris.ui.window.main_window import MainWindow

    inst = MagicMock(spec=MainWindow)
    inst._pending_ide_drag = []
    inst._attach_os_drop_paths = MagicMock(return_value=True)
    inst.frameGeometry = MagicMock(return_value=QRect(100, 100, 400, 800))

    bound_begin = MainWindow._begin_ide_companion_drag.__get__(inst, MainWindow)
    bound_finish = MainWindow._finish_ide_companion_drag.__get__(inst, MainWindow)

    with patch("PyQt6.QtWidgets.QApplication.instance", return_value=None):
        bound_begin([r"C:\proj\tab.py"])
    assert inst._pending_ide_drag == [r"C:\proj\tab.py"]

    with patch("PyQt6.QtGui.QCursor.pos", return_value=QPoint(0, 0)):
        assert bound_finish([r"C:\proj\tab.py"]) == []
    assert inst._pending_ide_drag == [r"C:\proj\tab.py"], "밖이면 pending 유지해야 함"

    with patch("PyQt6.QtGui.QCursor.pos", return_value=QPoint(150, 200)):
        assert bound_finish() == [r"C:\proj\tab.py"]
    assert inst._pending_ide_drag == []
    inst._attach_os_drop_paths.assert_called_with([r"C:\proj\tab.py"])


if __name__ == "__main__":
    main()
