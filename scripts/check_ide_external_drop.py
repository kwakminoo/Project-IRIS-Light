"""Live Windows OLE drop check on the actual Theia Explorer and editor tabs.

Run with ``python -m scripts.check_ide_external_drop`` while Theia is running.
Uses the same CF_HDROP/DoDragDrop protocol as Windows File Explorer.
"""
from __future__ import annotations

import ctypes
import json
import sys
from ctypes import wintypes
from pathlib import Path

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready


def main() -> None:
    ensure_qt_webengine_ready()
    from PyQt6.QtCore import QPoint, Qt, QTimer
    from PyQt6.QtWidgets import QApplication
    from iris.system.iris_ide_runtime import IrisIdeRuntimeManager
    from iris.ui.workspaces.iris_ide_window import IrisIdeWindow
    from iris.ui.window.win_ole_drop import (
        _ole_prop, drag_hdrop_onto, ensure_explorer_drop_targets,
    )

    app = QApplication(sys.argv)
    runtime = IrisIdeRuntimeManager()
    window = IrisIdeWindow()
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    window.resize(1000, 700)
    window.move(20, 20)
    received = []
    window.files_dropped.connect(lambda paths: received.append(list(paths)))
    paths = [str((Path(__file__).resolve().parents[1] / "qa-fixtures" / name).resolve())
             for name in ("test.txt", "test.md")]
    assert all(Path(path).is_file() for path in paths)
    result = {"ok": False}
    user32 = ctypes.windll.user32
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    original_cursor = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(original_cursor))

    def fail(message):
        result["error"] = str(message)
        window.grab().save(str(Path(__file__).resolve().parents[1] / ".iris_light_test_tmp" / "ide-external-drop.png"))
        print(json.dumps(result, ensure_ascii=False), flush=True)
        window.close()
        app.quit()

    def check(surfaces):
        if not isinstance(surfaces, list):
            result["layout"] = surfaces
            QTimer.singleShot(1000, inspect)
            return
        try:
            assert isinstance(surfaces, list) and len(surfaces) == 2, f"Missing Theia surfaces: {surfaces}"
            hwnd = int(window.winId())
            # Reproduce show + loadFinished + delayed rearm.
            for _ in range(3):
                assert ensure_explorer_drop_targets(hwnd, window, target="ide")
            registrations = set(window._explorer_ole_hwnds)
            assert registrations, "No native drop target"
            ours = window._explorer_ole_target.addr
            assert all(_ole_prop(child) == ours for child in registrations)
            checked = []
            for surface in surfaces:
                point = window._view.mapToGlobal(QPoint(int(surface["x"]), int(surface["y"])))
                user32.SetCursorPos(point.x(), point.y())
                for _ in range(3):
                    received.clear()
                    effect = drag_hdrop_onto(hwnd, paths)
                    assert effect == 1 and received == [paths], (surface, effect, received)
                checked.append(surface["name"])
            result.update(ok=True, surfaces=checked, drops_per_surface=3,
                          files_per_drop=len(paths), native_targets=len(registrations))
            print(json.dumps(result), flush=True)
            window.close()
            app.quit()
        except Exception as exc:
            fail(exc)

    def inspect():
        # Read actual layout rather than assume Explorer/tab coordinates.
        window._view.page().runJavaScript("""(() => {
            const explorer = document.querySelector('#files');
            const tabs = Array.from(document.querySelectorAll('#theia-main-content-panel [role="tablist"], #theia-main-content-panel .lm-TabBar, #theia-main-content-panel .p-TabBar')).find(e => {
                const r = e.getBoundingClientRect(); return r.width > 100 && r.height > 0;
            });
            if (!explorer?.getBoundingClientRect().width || !tabs) {
                return {title:document.title, text:document.body.innerText.slice(0, 1200),
                    viewport:[innerWidth,innerHeight], api:Object.keys(window.theia || {}),
                    tabs:Array.from(document.querySelectorAll('[role=tablist]')).map(e=>e.outerHTML.slice(0,200))};
            }
            return [[explorer, 'Explorer'], [tabs, 'tabs']].filter(([e]) => e).map(([e, name]) => {
                const r = e.getBoundingClientRect();
                return {name, x: r.x + r.width / 2, y: r.y + Math.min(r.height / 2, 100)};
            });
        })()""", check)

    def prepare():
        from PyQt6.QtTest import QTest

        view = window._view
        view.setFocus()
        QTest.keyClick(view.focusProxy() or view, Qt.Key.Key_E,
                       Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        QTest.keyClick(view.focusProxy() or view, Qt.Key.Key_P, Qt.KeyboardModifier.ControlModifier)
        # Pick a file within the running workspace; Quick Open searches roots.
        candidate = next(Path(runtime.workspace).glob("*.py"), None)
        assert candidate is not None, "Workspace needs an editor file for tab validation"
        QTimer.singleShot(500, lambda: QTest.keyClicks(view.focusProxy() or view, candidate.name))
        QTimer.singleShot(3000, lambda: QTest.keyClick(view.focusProxy() or view, Qt.Key.Key_Return))

    window.load_theia(runtime.base_url(), workspace=runtime.workspace)
    QTimer.singleShot(8000, prepare)
    QTimer.singleShot(12000, inspect)
    QTimer.singleShot(30000, lambda: fail("Theia load timed out"))
    try:
        app.exec()
    finally:
        user32.SetCursorPos(original_cursor.x, original_cursor.y)
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
