r"""Exercise actual folder creation, hooks, Theia startup and page load on Windows.

Run with .venv\Scripts\python.exe scripts/check_ide_folder_open.py.
Only the parent-folder picker is substituted; the normal folder-created/opened
signals, MainWindow slots, native hooks, launch worker and WebEngine are real.
"""
from pathlib import Path
import os
import sys
import tempfile
import traceback
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    with tempfile.TemporaryDirectory(prefix="IRIS IDE 한글 검증 ") as temp:
        os.environ["IRIS_DB_PATH"] = str(Path(temp) / "test.db")
        from iris.ui.qt_bootstrap import ensure_qt_webengine_ready
        ensure_qt_webengine_ready()
        from PyQt6.QtCore import QTimer, qInstallMessageHandler
        from PyQt6.QtWidgets import QApplication
        from iris.ui.window.main_window import MainWindow
        from iris.system.iris_ide_runtime import shared_iris_ide_runtime
        from iris.storage import ide_recent_folders

        app = QApplication(sys.argv)
        diagnostic = open("ide-folder-native.log", "w", encoding="utf-8")
        def qt_message(kind, context, message):
            diagnostic.write(f"{kind}: {message}\n")
            if kind.name == "QtFatalMsg":
                diagnostic.write("".join(traceback.format_stack()))
            diagnostic.flush()
        qInstallMessageHandler(qt_message)
        app.setQuitOnLastWindowClosed(False)
        win = MainWindow(test_mode=True)
        state = {"error": None, "loaded": 0, "created": "", "passed": False}

        def finish(error=None):
            state["error"] = error
            timeout.stop()
            win.close()
            app.quit()

        def exception(kind, value, tb):
            traceback.print_exception(kind, value, tb, file=diagnostic)
            diagnostic.flush()
            finish(repr(value))
        sys.excepthook = exception

        def loaded(ok):
            if not ok:
                finish("Theia page failed to load")
                return
            state["loaded"] += 1
            print("THEIA_LOAD_OK", state["loaded"], flush=True)
            if state["loaded"] == 1:
                QTimer.singleShot(3000, reopen)
            else:
                QTimer.singleShot(5000, verify)

        def verify():
            mgr = shared_iris_ide_runtime()
            ide = win._iris_ide_window
            assert Path(mgr.workspace).resolve() == Path(state["created"]).resolve()
            assert ide.isVisible() and win.isVisible()
            assert Path(ide._loaded_workspace).resolve() == Path(state["created"]).resolve(), (
                ide._loaded_workspace, state["created"]
            )
            assert win._ide_snap_redirect._hook
            if "--drag" in sys.argv:
                assert win._chat._extra_h == 180
                assert win._orb_spacer.height() == 80
                win._chat.reset_height_expansion()
                app.processEvents()
                assert win._orb_spacer.height() == 260
            state["passed"] = True
            print("PASS created folder -> IDE loaded -> reopen -> IRIS alive", flush=True)
            finish()

        def reopen():
            if "--drag" in sys.argv:
                chat = win._chat
                top = chat.y()
                center = win._viz.particle_core().effective_center()
                chat._height_handle.drag_started.emit(700)
                for extra in range(0, 261, 5):
                    chat._height_handle.dragged.emit(700 - extra)
                    app.processEvents()
                    assert chat.y() == top - extra, (extra, top, chat.y())
                    assert win._viz.particle_core().effective_center() == center
                chat._height_handle.dragged.emit(520)
                app.processEvents()
                win.grab().save("ide-chat-drag-preview.png")
                print("PASS live IDE drag: continuous movement, stable orb and fade", flush=True)
            err = win._open_iris_ide_folder(state["created"], source="icon")
            if err:
                finish(err)

        def create():
            win._enter_iris_ide_hero(source="icon")
            win._ide_hero.folder_created.connect(lambda path: state.update(created=path))
            with patch("iris.ui.ide.iris_ide_hero_overlay.QFileDialog.getExistingDirectory", return_value=temp):
                win._ide_hero._pick_create()
            assert Path(state["created"]).is_dir()
            print("CREATED", state["created"], flush=True)
            ide = win._iris_ide_window
            ide.theia_load_finished.connect(loaded)
            worker = win._iris_ide_launch_worker
            if worker is not None:
                worker.finished_err.connect(finish)

        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(lambda: finish("IDE validation timed out"))
        timeout.start(120000)
        win.show()
        # Keep test folders out of the user's recent-workspace history.
        with patch.object(ide_recent_folders, "record_opened_folder"), patch(
            "iris.ui.ide.iris_ide_hero_overlay.record_opened_folder"
        ):
            QTimer.singleShot(500, create)
            app.exec()
        if state["error"] is not None or not state["passed"]:
            raise RuntimeError(state["error"] or "IDE did not load twice")


if __name__ == "__main__":
    main()
