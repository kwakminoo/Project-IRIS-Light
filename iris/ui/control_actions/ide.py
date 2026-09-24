"""창·IDE 컴패니언·파일 첨부 드래그 컨트롤 액션."""

from __future__ import annotations

from iris.system.control_surface import (
    ActionRegistry,
)
from iris.ui.control_actions.hosts import IdeHost

def register_ide_actions(window: IdeHost, reg: ActionRegistry) -> None:
    from iris.ui.control_bindings import (
        Path,
        _bound_session,
        _ide_open_file_path,
        _log,
        err_result,
        load_user_profile,
        ok_result,
        save_user_profile,
    )

    def window_minimize(_a: dict[str, Any]) -> dict[str, Any]:
        window.showMinimized()
        _log(window, "window.minimize", True)
        return ok_result("window.minimize", {})

    def window_toggle_maximize(_a: dict[str, Any]) -> dict[str, Any]:
        window._toggle_maximize()
        _log(window, "window.toggle_maximize", True)
        return ok_result("window.toggle_maximize", {"maximized": window.isMaximized()})

    def window_show(_a: dict[str, Any]) -> dict[str, Any]:
        window.showNormal()
        window.raise_()
        window.activateWindow()
        _log(window, "window.show", True)
        return ok_result(
            "window.show",
            {"visible": window.isVisible(), "minimized": window.isMinimized()},
        )

    def ide_enter(_a: dict[str, Any]) -> dict[str, Any]:
        path = str(_a.get("project_root") or "").strip()
        if path:
            root = Path(path).expanduser()
            if not root.is_dir():
                return err_result("ide.enter_companion", f"project_root not a directory: {path}")
            profile = load_user_profile(window._db)
            profile.project_root = str(root.resolve())
            save_user_profile(window._db, profile)
        before = window._ui_mode
        window._enter_ide_companion(source="chat")
        ok = window._ui_mode == "ide_companion"
        _log(window, "ide.enter_companion", ok)
        return (
            ok_result(
                "ide.enter_companion",
                {
                    "ui_mode": window._ui_mode,
                    "was": before,
                    "ide_hwnd": getattr(window._ide_session, "hwnd", None),
                },
            )
            if ok
            else err_result(
                "ide.enter_companion",
                "companion not entered (IDE missing or window not found)",
                {"ui_mode": window._ui_mode},
            )
        )

    def ide_exit(_a: dict[str, Any]) -> dict[str, Any]:
        window._exit_ide_companion()
        _log(window, "ide.exit_companion", True)
        return ok_result("ide.exit_companion", {"ui_mode": window._ui_mode})

    def ide_toggle(_a: dict[str, Any]) -> dict[str, Any]:
        window._on_ide_icon()
        _log(window, "ide.toggle_companion", True)
        return ok_result("ide.toggle_companion", {"ui_mode": window._ui_mode})

    def chat_attach(args: dict[str, Any]) -> dict[str, Any]:
        """IDE 탭/탐색기 컨텍스트 메뉴 → 컴포저 칩."""
        path = str(args.get("path") or "").strip()
        if not path:
            return err_result("chat.attach", "path required")
        if not window._attach_os_drop_paths([path]):
            return err_result("chat.attach", "chat panel unavailable")
        return ok_result("chat.attach", {"attached": path})

    def chat_drag_start(args: dict[str, Any]) -> dict[str, Any]:
        """IDE→채팅 companion DnD — OS OLE 대신 경로만 넘긴다 (WebEngine 경계 우회)."""
        raw = args.get("paths") or args.get("path") or []
        if isinstance(raw, str):
            paths = [raw]
        elif isinstance(raw, list):
            paths = [str(p).strip() for p in raw if str(p).strip()]
        else:
            paths = []
        if not paths:
            return err_result("chat.drag_start", "paths required")
        window._begin_ide_companion_drag(paths)
        return ok_result("chat.drag_start", {"paths": paths, "count": len(paths)})

    def chat_drag_end(args: dict[str, Any]) -> dict[str, Any]:
        # drag_start fetch가 drag_end보다 늦을 수 있어 args.paths를 우선 사용.
        raw = args.get("paths") or args.get("path") or []
        if isinstance(raw, str) and raw.strip():
            paths = [raw.strip()]
        elif isinstance(raw, list):
            paths = [str(p).strip() for p in raw if str(p).strip()]
        else:
            paths = []
        attached = window._finish_ide_companion_drag(paths or None)
        return ok_result(
            "chat.drag_end",
            {"attached": attached, "count": len(attached)},
        )

    def ide_pick_open_folder(_a: dict[str, Any]) -> dict[str, Any]:
        from PyQt6.QtWidgets import QFileDialog

        start = ""
        try:
            start = str(load_user_profile(window._db).project_root or "")
        except Exception:
            start = ""
        path = QFileDialog.getExistingDirectory(window, "Open Folder", start)
        if not path:
            return ok_result("ide.pick_open_folder", {"cancelled": True})
        return ide_open_folder({"path": path, "new_window": False})

    def ide_pick_open_file(_a: dict[str, Any]) -> dict[str, Any]:
        from PyQt6.QtWidgets import QFileDialog

        start = ""
        try:
            start = str(load_user_profile(window._db).project_root or "")
        except Exception:
            start = ""
        paths, _ok = QFileDialog.getOpenFileNames(window, "Open File", start)
        if not paths:
            return ok_result("ide.pick_open_file", {"cancelled": True, "opened": []})
        opened: list[str] = []
        errors: list[str] = []
        for p in paths:
            r = ide_open_file({"path": p})
            if r.get("ok"):
                opened.append(p)
            else:
                errors.append(str(r.get("error") or p))
        ok = bool(opened) and not errors
        body = {"opened": opened, "errors": errors}
        if not ok:
            return err_result("ide.pick_open_file", errors[0] if errors else "open failed", body)
        return ok_result("ide.pick_open_file", body)

    def ide_open_folder(args: dict[str, Any]) -> dict[str, Any]:
        path = str(args.get("path") or args.get("folder") or args.get("project_root") or "").strip()
        if not path:
            return err_result("ide.open_folder", "path required")
        root = Path(path).expanduser()
        if not root.is_dir():
            return err_result("ide.open_folder", f"not a directory: {path}")
        # 기본=새 창. False면 기존 Cursor(개발용 포함)를 가로채 타일함 — bac8f75 회귀 금지.
        new_window = bool(args.get("new_window", True))
        err = window._open_ide_folder(str(root), new_window=new_window, source="chat")
        ok = not err and window._ui_mode == "ide_companion"
        _log(window, "ide.open_folder", ok)
        if not ok:
            return err_result(
                "ide.open_folder",
                err or "companion not entered",
                {"ui_mode": window._ui_mode, "path": str(root.resolve())},
            )
        return ok_result(
            "ide.open_folder",
            {
                "path": str(root.resolve()),
                "ui_mode": window._ui_mode,
                "ide_hwnd": getattr(window._ide_session, "hwnd", None),
                "new_window": new_window,
            },
        )

    def ide_open_file(args: dict[str, Any]) -> dict[str, Any]:
        suppress = getattr(window, "_suppress_generated_file_fallback", None)
        if callable(suppress):
            suppress()
        path = str(args.get("path") or "").strip()
        if not path:
            root = str(args.get("project_root") or args.get("root") or "").strip()
            if not root:
                profile = load_user_profile(window._db)
                root = (profile.project_root or "").strip()
            rel = str(args.get("rel_path") or "").strip()
            if not root or not rel:
                return err_result("ide.open_file", "path or project_root+rel_path required")
            try:
                from iris.system.project_ops import resolve_under_root

                _root, abs_path, _rel = resolve_under_root(root, rel)
                path = str(abs_path)
            except Exception as exc:  # noqa: BLE001
                return err_result("ide.open_file", str(exc))
        line = int(args.get("line") or 1)
        column = int(args.get("column") or 1)
        _session, session_err = _bound_session(window, require_workspace=False)
        if session_err:
            return err_result("ide.open_file", session_err)
        opened = _ide_open_file_path(window, path, line=line, column=column, reuse_window=False)
        _log(window, "ide.open_file", bool(opened.get("ok")))
        if not opened.get("ok"):
            return err_result("ide.open_file", str(opened.get("error") or "open failed"), opened)
        return ok_result("ide.open_file", opened)

    reg.register(
        "window.minimize",
        window_minimize,
        summary="Minimize Iris window",
    )

    reg.register(
        "window.toggle_maximize",
        window_toggle_maximize,
        summary="Toggle maximize Iris window",
    )

    reg.register(
        "window.show",
        window_show,
        summary="Show / raise / activate Iris window (un-minimize)",
    )

    reg.register(
        "ide.enter_companion",
        ide_enter,
        summary="Enter IDE Companion using the current bound session or create one with preferred IDE",
    )

    reg.register(
        "ide.exit_companion",
        ide_exit,
        summary="Exit IDE Companion and clear the bound IDE session",
    )

    reg.register(
        "ide.toggle_companion",
        ide_toggle,
        summary="Toggle IDE Companion (same as IDE icon)",
    )

    reg.register(
        "ide.open_folder",
        ide_open_folder,
        summary="Open a folder in the IDE. The action name is ide.open_folder (not project.open_folder). args.path is required.",
        risk="medium",
    )

    reg.register(
        "ide.open_file",
        ide_open_file,
        summary="Open an existing file in the bound IDE workspace. Required: path, or project_root+rel_path. Relative paths are under the bound workspace from iris_get_state, not the shell cwd. Missing files are an error; do not create a substitute.",
        risk="medium",
    )

    reg.register(
        "ide.pick_open_folder",
        ide_pick_open_folder,
        summary="Native OS folder picker then open that folder in IRIS IDE",
        risk="medium",
    )

    reg.register(
        "ide.pick_open_file",
        ide_pick_open_file,
        summary="Native OS file picker then open selected files in the bound IDE",
        risk="medium",
    )

    reg.register(
        "chat.attach",
        chat_attach,
        summary="Attach a file path to the IRIS chat composer as an @reference chip",
    )

    reg.register(
        "chat.drag_start",
        chat_drag_start,
        summary="Begin IDE→chat companion drag (path list; OS DnD bypass for QWebEngine)",
    )

    reg.register(
        "chat.drag_end",
        chat_drag_end,
        summary="Finish IDE→chat companion drag — attach if cursor is over Iris",
    )
