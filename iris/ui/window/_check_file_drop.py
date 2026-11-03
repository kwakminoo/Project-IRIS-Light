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
    taint = QMimeData()
    taint.setText("file")
    taint.setHtml("<p>pdf</p>")
    taint.setData("chromium/x-renderer-taint", b"1")
    assert mime_has_attachable(taint) is False, "chromium taint가 파일 드롭으로 통과함"

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
    assert "seedCompanionDragSync" in contrib, "sync drag_start seed가 사라짐"
    assert "xhr.open(" in contrib and ", false)" in contrib, "sync XHR(open async=false) seed가 사라짐"
    assert "finishCompanionDrag" in contrib and "pointercancel" in contrib
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
    check_companion_drag_race()
    check_win_shell_drop_arm()
    check_explorer_overlay_drop()
    check_ole_explorer_drop()
    check_korean_explorer_names()
    check_occluded_click_stays_on_front_window()
    check_no_win32_drop_hooks()
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
        assert "seedCompanionDragSync" in text or ",!1)" in text or ", false)" in text, (
            f"{label} bundle missing sync drag seed"
        )
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


def check_companion_drag_race() -> None:
    """빠른 드롭 레이스 — pending 선도착 + 늦은 drag_end paths 둘 다 첨부."""
    from unittest.mock import MagicMock, patch

    from PyQt6.QtCore import QPoint, QRect

    from iris.ui.window.main_window import MainWindow

    inst = MagicMock(spec=MainWindow)
    inst._pending_ide_drag = []
    inst._attach_os_drop_paths = MagicMock(return_value=True)
    inst.frameGeometry = MagicMock(return_value=QRect(100, 100, 400, 800))

    bound_begin = MainWindow._begin_ide_companion_drag.__get__(inst, MainWindow)
    bound_finish = MainWindow._finish_ide_companion_drag.__get__(inst, MainWindow)

    # 1) sync seed가 pending을 먼저 채운 뒤, Iris 위 release(경로 없이)로 첨부
    with patch("PyQt6.QtWidgets.QApplication.instance", return_value=None):
        bound_begin([r"C:\proj\race.py"])
    assert inst._pending_ide_drag == [r"C:\proj\race.py"], "pending 선도착 실패"
    with patch("PyQt6.QtGui.QCursor.pos", return_value=QPoint(150, 200)):
        assert bound_finish() == [r"C:\proj\race.py"]
    assert inst._pending_ide_drag == []
    inst._attach_os_drop_paths.assert_called_with([r"C:\proj\race.py"])

    # 2) drag_start HTTP가 늦어 pending이 비어 있어도 drag_end paths로 첨부
    inst._pending_ide_drag = []
    inst._attach_os_drop_paths.reset_mock()
    with patch("PyQt6.QtGui.QCursor.pos", return_value=QPoint(150, 200)):
        assert bound_finish([r"C:\proj\late.py"]) == [r"C:\proj\late.py"]
    inst._attach_os_drop_paths.assert_called_with([r"C:\proj\late.py"])


def check_ole_explorer_drop() -> None:
    """탐색기와 같은 CF_HDROP이 금지 커서(effect 0) 없이 기존 첨부 콜백으로 간다."""
    import sys

    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QMainWindow

    from iris.ui.window.win_ole_drop import _ole_prop, drag_hdrop_onto, install_explorer_drop_target

    host = QMainWindow()
    host.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
    host.resize(280, 180)
    host.move(30, 30)
    host.setAcceptDrops(True)
    seen: list[tuple[str, list[str]]] = []

    def _on_explorer_file_drag(phase: str, paths: list[str]) -> None:
        seen.append((phase, list(paths)))

    host._on_explorer_file_drag = _on_explorer_file_drag  # type: ignore[method-assign]
    host.show()
    QApplication.instance().processEvents()
    hwnd = int(host.winId())
    assert install_explorer_drop_target(hwnd, host)
    user32 = ctypes.windll.user32
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
    rect = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    hit = 0
    cx = cy = 0
    for y in range(rect.top + 8, rect.bottom - 4, 12):
        for x in range(rect.left + 8, rect.right - 4, 20):
            user32.SetCursorPos(x, y)
            hit = int(user32.WindowFromPoint(wintypes.POINT(x, y)) or 0)
            if hit == hwnd:
                cx, cy = x, y
                break
        if hit == hwnd:
            break
    assert hit == hwnd, f"cursor never hit drop hwnd {hwnd} last={hit} rect={rect.left},{rect.top},{rect.right},{rect.bottom}"
    clip = wintypes.RECT(rect.left, rect.top, rect.right, rect.bottom)
    user32.ClipCursor.argtypes = [ctypes.POINTER(wintypes.RECT)]
    user32.ClipCursor(ctypes.byref(clip))
    user32.SetCursorPos(cx, cy)
    hit_now = int(user32.WindowFromPoint(wintypes.POINT(cx, cy)) or 0)
    assert hit_now == hwnd, f"cursor left drop hwnd before drag hit={hit_now}"
    first = str(Path(__file__).resolve())
    second = str((Path(__file__).resolve().parent / "file_drop.py"))
    ole_before = _ole_prop(hwnd)
    assert install_explorer_drop_target(hwnd, host)
    assert _ole_prop(hwnd) == ole_before, "같은 HWND에 Drop Target을 다시 등록함"
    try:
        for n in range(10):
            seen.clear()
            effect = drag_hdrop_onto(hwnd, [first, second])
            drops = [paths for phase, paths in seen if phase == "drop"]
            assert effect == 1 and drops == [[first, second]], f"drop {n} effect={effect} events={seen}"
            assert _ole_prop(hwnd) == ole_before, "OLE target replaced during repeated drops"
        from iris.ui.window.explorer_drop_overlay import ExplorerDropGuard

        guard = ExplorerDropGuard(host)
        guard.start()
        assert guard.overlay().isVisible() is False
        assert guard.overlay().acceptDrops() is False
        assert _ole_prop(hwnd) == ole_before, "overlay guard replaced the main OLE target"
    finally:
        user32.ClipCursor(None)
    host.close()


def check_korean_explorer_names() -> None:
    """CF_HDROP 한글·공백·괄호 파일명. 메인/IDE HWND 각각 10회."""
    import sys
    import tempfile

    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QMainWindow

    from PyQt6.QtWidgets import QApplication
    from iris.ui.chat.composer_attachments import attachment_filename, validate_files
    from iris.ui.window.win_ole_drop import drag_hdrop_onto, install_explorer_drop_target

    names = [
        "실전모의고사(엑셀).pdf",
        "보고서 최종본.pdf",
        "테스트 파일 01.txt",
        "IRIS_기능정리_v2.docx",
        "한글파일명.png",
    ]
    folder = Path(tempfile.mkdtemp(prefix="iris-drop-"))
    paths = []
    try:
        for name in names:
            path = folder / name
            path.write_bytes(b"iris-drop")
            paths.append(str(path))
        ok, errors = validate_files(paths)
        assert errors == [], errors
        assert [attachment_filename(p) for p in ok] == names, ok

        user32 = ctypes.windll.user32
        for label in ("main", "ide"):
            host = QMainWindow()
            host.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
            host.resize(320, 200)
            host.move(40, 40)
            host.setAcceptDrops(True)
            seen: list[list[str]] = []

            def _on_explorer_file_drag(phase: str, got: list[str], box=seen) -> None:
                if phase == "drop":
                    box.append(list(got))

            host._on_explorer_file_drag = _on_explorer_file_drag  # type: ignore[method-assign]
            host.show()
            QApplication.instance().processEvents()
            hwnd = int(host.winId())
            assert install_explorer_drop_target(hwnd, host, target=label)
            rect = wintypes.RECT()
            user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
            user32.SetCursorPos(rect.left + 24, rect.top + 24)
            user32.ClipCursor.argtypes = [ctypes.POINTER(wintypes.RECT)]
            user32.ClipCursor(ctypes.byref(rect))
            try:
                for n in range(10):
                    seen.clear()
                    effect = drag_hdrop_onto(hwnd, paths)
                    assert effect == 1, f"{label} drop {n} effect={effect}"
                    assert seen and [Path(p).name for p in seen[-1]] == names, seen
            finally:
                user32.ClipCursor(None)
                host.close()
    finally:
        import shutil

        shutil.rmtree(folder, ignore_errors=True)


def check_occluded_click_stays_on_front_window() -> None:
    """Iris가 뒤에 있을 때 사각형이 겹쳐도 앞 페이지 클릭을 가로채지 않는다."""
    from iris.ui.window.explorer_drop_overlay import cursor_targets_iris_window

    assert cursor_targets_iris_window(50, host_hwnd=1, overlay_hwnd=2) is False
    assert cursor_targets_iris_window(1, host_hwnd=1, overlay_hwnd=2) is True
    assert cursor_targets_iris_window(2, host_hwnd=1, overlay_hwnd=2) is True
    assert cursor_targets_iris_window(9, host_hwnd=1, ide_hwnd=9) is False
    assert cursor_targets_iris_window(0, host_hwnd=1) is True


def check_no_win32_drop_hooks() -> None:
    """탐색기 드롭 우회가 nativeEvent/WNDPROC 훅을 다시 넣지 않았는지."""
    root = Path(__file__).resolve().parents[3]
    banned = (
        "def nativeEvent",
        "class _DropNativeFilter",
        "GWL_WNDPROC",
        "SetWindowLongPtr",
        "CallWindowProc",
        "SetWindowsHookEx",
    )
    text = (root / "iris/ui/window/explorer_drop_overlay.py").read_text(encoding="utf-8")
    for token in banned:
        assert token not in text, f"explorer_drop_overlay reintroduced {token}"
    assert "_qt_modal_blocking" in text
    assert "_drop_guard_paused" in text
    assert "drop_target_global_rect" in text
    main = (root / "iris/ui/window/main_window.py").read_text(encoding="utf-8")
    # 스냅 레이아웃용 nativeEvent 만 허용. 드롭 훅은 기동 즉사라 금지.
    assert "windows_snap_native_reply" in main
    assert "WM_DROPFILES" not in main
    assert "QAbstractNativeEventFilter" not in main
    chrome = (root / "iris/ui/window/frameless_chrome.py").read_text(encoding="utf-8")
    for token in ("WM_DROPFILES", "SetWindowLongPtr", "CallWindowProc", "QAbstractNativeEventFilter"):
        assert token not in chrome, token


def check_explorer_overlay_drop() -> None:
    """별도 Qt overlay가 + 첨부와 같은 attach 콜백을 쓰는지."""
    import sys

    from PyQt6.QtCore import QMimeData, QPoint, QPointF, QUrl, Qt
    from PyQt6.QtGui import QDragEnterEvent, QDropEvent
    from PyQt6.QtWidgets import QMainWindow

    from iris.ui.window.explorer_drop_overlay import ExplorerDropGuard

    host = QMainWindow()
    host.setWindowTitle("overlay-host")
    host.resize(320, 240)
    host._pending_ide_drag = []
    attached: list[str] = []

    def _attach(paths: list[str]) -> bool:
        attached.extend(paths)
        return True

    host._attach_os_drop_paths = _attach  # type: ignore[method-assign]
    guard = ExplorerDropGuard(host)
    overlay = guard.overlay()
    assert overlay.acceptDrops() is False
    assert overlay.isVisible() is False
    host.show()
    QApplication.instance().processEvents()

    sample = Path(__file__).resolve()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(sample))])
    enter = QDragEnterEvent(
        QPoint(12, 16),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.dragEnterEvent(enter)
    assert enter.isAccepted(), "file dragEnter must accept"

    drop = QDropEvent(
        QPointF(12, 16),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.dropEvent(drop)
    assert [Path(p).resolve() for p in attached] == [sample], attached
    assert overlay.isVisible() is False, "drop 후 overlay 제거"

    extra = (sample.parent / "file_drop.py").resolve()
    multi = QMimeData()
    multi.setUrls([QUrl.fromLocalFile(str(sample)), QUrl.fromLocalFile(str(extra))])
    overlay.dropEvent(
        QDropEvent(
            QPointF(8, 8),
            Qt.DropAction.CopyAction,
            multi,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    assert [Path(p).resolve() for p in attached[-2:]] == [sample, extra], attached

    overlay.arm()
    QApplication.instance().processEvents()
    assert overlay.acceptDrops() is True
    assert overlay.isVisible() is True
    assert overlay._hint.text() == "파일을 여기에 놓아주세요"
    assert "dashed" not in overlay.styleSheet()
    overlay_src = (Path(__file__).resolve().parents[1] / "window" / "explorer_drop_overlay.py").read_text(encoding="utf-8")
    assert ".setWindowOpacity(" not in overlay_src
    overlay.dragEnterEvent(enter)
    assert overlay._active is True
    from PyQt6.QtGui import QDragLeaveEvent

    overlay.dragLeaveEvent(QDragLeaveEvent())
    assert overlay._active is False
    assert overlay.isVisible() is True
    overlay.disarm()
    assert overlay.isVisible() is False

    from iris.ui.window.explorer_drop_overlay import _drop_guard_paused, _qt_modal_blocking

    assert _qt_modal_blocking() is False
    assert _drop_guard_paused(host) is False
    class _RunningWorker:
        def isRunning(self) -> bool:
            return True

    host._iris_ide_launch_worker = _RunningWorker()
    assert _drop_guard_paused(host) is True
    host._iris_ide_launch_worker = None
    dlg = QMainWindow()  # not modal
    assert _qt_modal_blocking() is False
    dlg.close()

    if sys.platform == "win32":
        overlay.arm()
        QApplication.instance().processEvents()
        hwnd = int(overlay.winId())
        assert hwnd != 0
        import ctypes

        from iris.ui.window.win_shell_drop import WS_EX_TRANSPARENT, hwnd_drop_debug

        ex = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        assert not (ex & WS_EX_TRANSPARENT), hwnd_drop_debug(hwnd)
        assert not (ex & 0x00080000), hwnd_drop_debug(hwnd)
        overlay.disarm()
    from PyQt6.QtWidgets import QWidget

    from iris.ui.window.explorer_drop_overlay import drop_target_global_rect

    chat = QWidget(host)
    chat.setGeometry(20, 30, 120, 90)
    host._chat = chat
    chat.show()
    QApplication.instance().processEvents()
    rect = drop_target_global_rect(host)
    assert rect.width() == 120 and rect.height() == 90, rect

    # 마우스 버튼을 누르고만 있어도 안내 창을 올리지 않는다.
    hold = QWidget()
    hold.resize(180, 120)
    hold.show()
    QApplication.instance().processEvents()
    hold_guard = ExplorerDropGuard(hold)
    hold_guard.start()
    import iris.ui.window.explorer_drop_overlay as drop_mod

    old_lmb = drop_mod._lmb_down
    old_hit = drop_mod._cursor_on_drop_surface
    drop_mod._lmb_down = lambda: True
    drop_mod._cursor_on_drop_surface = lambda *_a, **_k: True
    try:
        hold_guard._press_inside = False
        hold_guard._tick()
        assert hold_guard.overlay().isVisible() is False
    finally:
        drop_mod._lmb_down = old_lmb
        drop_mod._cursor_on_drop_surface = old_hit
    hold.close()
    host.close()


if __name__ == "__main__":
    main()
