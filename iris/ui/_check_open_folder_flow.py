"""Reproduce Open Folder → Opening → Theia (run_bat-like)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from iris.system.iris_ide_runtime import shared_iris_ide_runtime
from iris.ui.qt_bootstrap import ensure_qt_webengine_ready


def main() -> int:
    shared_iris_ide_runtime().stop()
    ensure_qt_webengine_ready()
    app = QApplication(sys.argv)

    errs: list[str] = []

    def hook(t, v, _tb) -> None:  # noqa: ANN001
        errs.append(f"{t.__name__}: {v}")
        print("EXC", t.__name__, v, flush=True)

    sys.excepthook = hook

    from iris.storage.user_profile import load_user_profile, save_user_profile
    from iris.ui.window.main_window import MainWindow

    results = {
        "theia_ok": False,
        "session_cleared": False,
        "reopen_ok": False,
        "preferred_cursor_ok": False,
    }

    w = MainWindow(test_mode=True)
    profile = load_user_profile(w._db)
    profile.preferred_ide = "iris_ide"
    save_user_profile(w._db, profile)

    _orig_clear = w._clear_ide_session

    def _clear_logged(reason: str = "") -> None:
        print(f"CLEAR_SESSION reason={reason!r} ui={w._ui_mode}", flush=True)
        if reason in ("preferred IDE 변경", "IDE 창 종료"):
            results["session_cleared"] = True
        _orig_clear(reason)

    w._clear_ide_session = _clear_logged  # type: ignore[method-assign]
    w.show()

    folder = Path.home() / "IRIS-TEST"
    folder.mkdir(exist_ok=True)
    (folder / "hello.txt").write_text("hi", encoding="utf-8")
    folder_s = str(folder.resolve())

    kr = Path.home() / "IRIS 테스트 폴더"
    kr.mkdir(exist_ok=True)
    (kr / "a.txt").write_text("ko", encoding="utf-8")
    kr_s = str(kr.resolve())

    state = {"t0": time.time(), "phase": "wait_hero", "open_at": 0.0, "pass": 1}

    def tick() -> None:
        now = time.time()
        win = w._iris_ide_window
        sess = w._ide_session
        ui = w._ui_mode
        opening = win.is_opening() if win else None
        worker = w._iris_ide_launch_worker
        wr = worker.isRunning() if worker else False
        mgr = shared_iris_ide_runtime()
        print(
            f"p{state['pass']} t+{now - state['t0']:.1f}s mode={ui} "
            f"sess={sess.ide_id}/{sess.mode}/a={sess.active} "
            f"opening={opening} worker={wr} ws_open={mgr.workspace_open} "
            f"errs={len(errs)}",
            flush=True,
        )

        if state["phase"] == "wait_hero" and (ui == "ide_hero" or now - state["t0"] > 8):
            target = folder_s if state["pass"] == 1 else kr_s
            print("OPEN FOLDER", target, flush=True)
            err = w._open_iris_ide_folder(target, source="icon", from_hero=True)
            print("open_err", repr(err), flush=True)
            state["phase"] = "opening"
            state["open_at"] = now
        elif state["phase"] == "opening":
            if win and win.is_theia_loaded() and sess.active:
                print("SUCCESS theia loaded", flush=True)
                if state["pass"] == 1:
                    results["theia_ok"] = True
                    state["pass"] = 2
                    state["phase"] = "wait_hero"
                    state["t0"] = now
                    w._exit_ide_companion()
                    QTimer.singleShot(200, lambda: w._enter_iris_ide_hero(source="icon"))
                    QTimer.singleShot(
                        400,
                        lambda: w._on_ide_hero_void_ready() if w._hero_enter_pending else None,
                    )
                else:
                    results["reopen_ok"] = True
                    profile2 = load_user_profile(w._db)
                    profile2.preferred_ide = "cursor"
                    save_user_profile(w._db, profile2)
                    # force a session watch tick
                    w._refresh_ide_session_state()
                    results["preferred_cursor_ok"] = bool(
                        w._ide_session.active and w._ui_mode == "ide_companion"
                    )
                    print(
                        "preferred-cursor retention",
                        results["preferred_cursor_ok"],
                        flush=True,
                    )
                    state["phase"] = "done"
                    QTimer.singleShot(400, app.quit)
            elif results["session_cleared"] and now - state["open_at"] > 2:
                print("FAIL session cleared while opening", flush=True)
                state["phase"] = "done"
                QTimer.singleShot(200, app.quit)
            elif now - state["open_at"] > 150:
                print("TIMEOUT", flush=True)
                state["phase"] = "done"
                app.quit()

    w._enter_iris_ide_hero(source="icon")
    QTimer.singleShot(
        120,
        lambda: w._on_ide_hero_void_ready() if w._hero_enter_pending else None,
    )
    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(1000)
    app.exec()

    attr_errs = [e for e in errs if "workspace_open" in e]
    print("RESULTS", results, "attr_errs", len(attr_errs), "all_errs", errs, flush=True)
    shared_iris_ide_runtime().stop()
    if w._iris_ide_window is not None:
        try:
            w._close_iris_ide_window()
        except Exception:
            pass
    ok = (
        results["theia_ok"]
        and results["reopen_ok"]
        and results["preferred_cursor_ok"]
        and not results["session_cleared"]
        and not attr_errs
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
