"""창·IDE 컴패니언·파일 첨부 드래그 컨트롤 액션."""

from __future__ import annotations

from iris.system.control_surface import (
    ActionRegistry,
)
from iris.ui.control_actions.hosts import IdeHost

def _reload_ide_if_running(window: IdeHost, workspace: str) -> str:
    """켜진 IRIS IDE만 재기동한다. 플러그인 스캔은 프로세스 시작 때 한 번이다."""
    from iris.system.iris_ide_runtime import shared_iris_ide_runtime

    mgr = shared_iris_ide_runtime()
    if mgr.runtime_pid is None:
        return "not_running"
    try:
        mgr.stop()
        ok, detail = mgr.start(workspace)
    except Exception as exc:  # noqa: BLE001
        return f"error:{exc}"
    if not ok:
        return f"error:{detail}"

    def _load() -> None:
        load = getattr(window, "_load_theia_after_launch", None)
        if callable(load):
            load(mgr.base_url(), workspace)

    try:
        from iris.ui.control_bindings import _call_on_ui

        _call_on_ui(window, _load)
    except Exception as exc:  # noqa: BLE001
        return f"error:{exc}"
    return "reloaded"


def register_ide_actions(window: IdeHost, reg: ActionRegistry) -> None:
    from iris.ui.control_bindings import (
        Path,
        _bound_session,
        _ide_open_file_path,
        _log,
        err_result,
        iris_ide_edit_ok,
        iris_ide_query_ok,
        iris_ide_save_ok,
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
            from iris.runtime.chat_worktree import conversation_id_of, is_chat_worktree, work_root_for

            chosen = work_root_for(conversation_id_of(window, _a), str(root))
            if not is_chat_worktree(chosen):
                profile = load_user_profile(window._db)
                profile.project_root = str(Path(chosen).resolve())
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
        # frameless MainWindow의 modal 자식이면 닫힌 뒤 0xC0000409.
        path = QFileDialog.getExistingDirectory(None, "Open Folder", start)
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
        paths, _ok = QFileDialog.getOpenFileNames(None, "Open File", start)
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
        from iris.runtime.chat_worktree import conversation_id_of, work_root_for

        path = work_root_for(conversation_id_of(window, args), path)
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
        try:
            from iris.knowledge.ide_project_log import note_opened

            wiki = getattr(window, "_iris_wiki", None)
            if wiki is not None:
                note_opened(wiki, str(root.resolve()))
        except Exception:
            pass
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

    def _ide_project() -> tuple[str, str]:
        from iris.system.extension_scope import choose_extension_scope

        mode = str(getattr(window, "_ui_mode", "") or "")
        root = ""
        try:
            root = str(window._current_project_root() or "")
        except Exception:
            root = ""
        session = getattr(window, "_ide_session", None)
        bound = str(getattr(session, "workspace_root", "") or "").strip() if session is not None else ""
        if bound:
            root = bound
        scope, err = choose_extension_scope(mode, root, "project")
        if err or scope != "project":
            return "", err or "열린 프로젝트가 없습니다."
        return root, ""

    def ide_marketplace_search(args: dict[str, Any]) -> dict[str, Any]:
        from iris.system.project_marketplace import search_extensions

        root, err = _ide_project()
        if err:
            return err_result("ide.marketplace_search", err)
        query = str(args.get("query") or args.get("q") or "").strip()
        try:
            rows = search_extensions(query)
        except Exception as exc:  # noqa: BLE001
            return err_result("ide.marketplace_search", str(exc)[:300])
        return ok_result("ide.marketplace_search", {"project_root": root, "extensions": rows})

    def ide_marketplace_install(args: dict[str, Any]) -> dict[str, Any]:
        from iris.system.iris_ide_runtime import iris_ide_config_dir
        from iris.system.project_marketplace import install_extension

        root, err = _ide_project()
        if err:
            return err_result("ide.marketplace_install", err)
        ext_id = str(args.get("id") or args.get("extension_id") or "").strip()
        deploy = iris_ide_config_dir() / "deployedPlugins"
        try:
            installed = install_extension(root, ext_id, str(deploy))
        except Exception as exc:  # noqa: BLE001
            return err_result("ide.marketplace_install", str(exc)[:300])
        reload = _reload_ide_if_running(window, root)
        installed["reload"] = reload
        if reload.startswith("error:"):
            return err_result("ide.marketplace_install", reload[6:], installed)
        plugin: dict[str, Any] = {"id": installed.get("id"), "loaded": False, "reason": reload}
        if reload == "reloaded":
            try:
                client = window._iris_ide_bridge_client()
                plugin = client.plugin_loaded(str(installed.get("id") or ""))
            except Exception as exc:  # noqa: BLE001
                plugin = {
                    "id": installed.get("id"),
                    "loaded": False,
                    "reason": str(exc)[:200],
                }
        installed["plugin"] = plugin
        return ok_result("ide.marketplace_install", installed)

    def ide_project_log(args: dict[str, Any]) -> dict[str, Any]:
        from iris.knowledge.ide_project_log import note_update

        root, err = _ide_project()
        if err:
            return err_result("ide.project_log", err)
        wiki = getattr(window, "_iris_wiki", None)
        if wiki is None:
            return err_result("ide.project_log", "wiki unavailable")
        plan = str(args.get("plan") or "")
        decision = str(args.get("decision") or "")
        issue = str(args.get("issue") or "")
        progress = str(args.get("progress") or "")
        if not any(part.strip() for part in (plan, decision, issue, progress)):
            return err_result("ide.project_log", "plan, decision, issue, or progress required")
        try:
            rel = note_update(
                wiki,
                root,
                plan=plan,
                decision=decision,
                issue=issue,
                progress=progress,
            )
        except Exception as exc:  # noqa: BLE001
            return err_result("ide.project_log", str(exc)[:300])
        return ok_result("ide.project_log", {"rel_path": rel, "project_root": root})

    reg.register(
        "ide.marketplace_search",
        ide_marketplace_search,
        summary="Search Open VSX for the project open in IRIS IDE. Required: query. Does not install. Do not claim installed.",
        risk="low",
    )
    reg.register(
        "ide.marketplace_install",
        ide_marketplace_install,
        summary="Download an Open VSX VSIX into IRIS IDE deployedPlugins and pin it on the open project. Required: id as publisher.name. ok only when extension/package.json is on disk. reload=reloaded means the IDE process is restarting. reload=not_running means the next IDE start loads it. plugin.loaded true is the only signal the plugin host has the extension. Do not say a PDF tab or extension viewer is already open.",
        risk="medium",
    )
    def _iris_client() -> tuple[Any, str]:
        session, err = _bound_session(window, require_workspace=False)
        if err:
            return None, err
        if str(getattr(session, "ide_id", "") or "") != "iris_ide":
            return None, "IRIS IDE session required"
        try:
            return window._iris_ide_bridge_client(), ""
        except Exception as exc:  # noqa: BLE001
            return None, str(exc)

    def _bridge(action: str, call: Any) -> dict[str, Any]:
        client, err = _iris_client()
        if err or client is None:
            return err_result(action, err or "IRIS IDE bridge unavailable")
        try:
            return ok_result(action, call(client))
        except Exception as exc:  # noqa: BLE001
            return err_result(action, str(exc)[:400])

    def ide_diagnostics(_args: dict[str, Any]) -> dict[str, Any]:
        return _bridge("ide.diagnostics", lambda client: client.get_diagnostics())

    def ide_symbols(args: dict[str, Any]) -> dict[str, Any]:
        symbol = str(args.get("symbol") or args.get("query") or "")
        path = str(args.get("path") or "")

        def _symbols(client: Any) -> dict[str, Any]:
            out = client.goto_symbol(symbol, path=path)
            ok_q, q_err = iris_ide_query_ok(out)
            if not ok_q:
                raise ValueError(q_err)
            return out

        return _bridge("ide.symbols", _symbols)

    def ide_references(args: dict[str, Any]) -> dict[str, Any]:
        def _refs(client: Any) -> dict[str, Any]:
            out = client.find_references(
                str(args.get("path") or ""),
                line=int(args.get("line") or 0),
                column=int(args.get("column") or 0),
            )
            ok_q, q_err = iris_ide_query_ok(out)
            if not ok_q:
                raise ValueError(q_err)
            return out

        return _bridge("ide.references", _refs)

    def ide_definition(args: dict[str, Any]) -> dict[str, Any]:
        def _def(client: Any) -> dict[str, Any]:
            out = client.goto_definition(
                str(args.get("path") or ""),
                line=int(args.get("line") or 0),
                column=int(args.get("column") or 0),
            )
            ok_q, q_err = iris_ide_query_ok(out)
            if not ok_q:
                raise ValueError(q_err)
            return out

        return _bridge("ide.definition", _def)

    def ide_edit(args: dict[str, Any]) -> dict[str, Any]:
        op = str(args.get("op") or "insert").strip()
        text = args.get("text")
        if text is None:
            text = args.get("content")
        if text is None:
            return err_result("ide.edit", "text required")
        path = str(args.get("path") or "")

        def _edit(client: Any) -> dict[str, Any]:
            if op in ("replace_selection", "selection"):
                out = client.replace_selection(str(text), path=path)
            elif op in ("replace_range", "range"):
                end = args.get("end")
                out = client.replace_range(
                    str(text),
                    path=path,
                    start=int(args.get("start") or 0),
                    end=None if end is None else int(end),
                )
            elif op in ("apply", "document"):
                out = client.apply_text_edit(str(text), path=path)
            elif op in ("insert", "insert_text"):
                out = client.insert_text(str(text), path=path)
            else:
                raise ValueError(f"unknown edit op: {op}")
            ok_edit, edit_err = iris_ide_edit_ok(out)
            if not ok_edit:
                raise ValueError(edit_err)
            return out

        return _bridge("ide.edit", _edit)

    def ide_save(args: dict[str, Any]) -> dict[str, Any]:
        def _save(client: Any) -> dict[str, Any]:
            out = (
                client.save_all()
                if bool(args.get("all"))
                else client.save_file(str(args.get("path") or ""))
            )
            ok_save, save_err = iris_ide_save_ok(out)
            if not ok_save:
                raise ValueError(save_err)
            return out

        return _bridge("ide.save", _save)

    def ide_task(args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("name") or args.get("label") or "").strip()
        if not name:
            return err_result("ide.task", "name required")
        return _bridge("ide.task", lambda client: client.run_task(name))

    def ide_debug(args: dict[str, Any]) -> dict[str, Any]:
        op = str(args.get("op") or "start").strip()

        def _debug(client: Any) -> dict[str, Any]:
            if op == "stop":
                return client.stop_debug()
            if op == "continue":
                return client.continue_debug()
            if op != "start":
                raise ValueError(f"unknown debug op: {op}")
            return client.start_debug({"name": str(args.get("name") or args.get("configuration") or "")})

        return _bridge("ide.debug", _debug)

    def ide_plugin_status(args: dict[str, Any]) -> dict[str, Any]:
        ext_id = str(args.get("id") or args.get("extension_id") or "").strip()
        if not ext_id:
            return err_result("ide.plugin_status", "id required")
        return _bridge("ide.plugin_status", lambda client: client.plugin_loaded(ext_id))

    reg.register(
        "ide.diagnostics",
        ide_diagnostics,
        summary="Problems in the open IRIS IDE. reported false means the editor has not pushed markers yet — do not say the project is clean. An empty diagnostics list is clean only when reported is true.",
        risk="low",
    )
    reg.register(
        "ide.symbols",
        ide_symbols,
        summary="Document symbols from the open IRIS IDE editor. Optional symbol filter and path. ok only when queried is true. Empty items means none found, not a failed query. Timeout/unsupported is failure — do not invent symbols.",
        risk="low",
    )
    reg.register(
        "ide.references",
        ide_references,
        summary="References at the cursor or at path+line+column in the open IRIS IDE editor. ok only when queried is true. Empty items means none found.",
        risk="low",
    )
    reg.register(
        "ide.definition",
        ide_definition,
        summary="Definition at the cursor or at path+line+column in the open IRIS IDE editor. ok only when queried is true. Empty items means none found.",
        risk="low",
    )
    reg.register(
        "ide.edit",
        ide_edit,
        summary="Edit the open IRIS IDE buffer. op=insert|replace_selection|replace_range|apply, text required, optional path. ok only when via=editor. Disk append is not a selection replace and fails the action.",
        risk="medium",
    )
    reg.register(
        "ide.save",
        ide_save,
        summary="Save the open IRIS IDE editor buffer. Optional path, or all=true. ok only when via=editor (buffer flush). No open editor is a failure — do not claim saved from disk alone.",
        risk="medium",
    )
    reg.register(
        "ide.task",
        ide_task,
        summary="Run a tasks.json task in IRIS IDE by name. started true only after TaskService accepts it.",
        risk="medium",
    )
    reg.register(
        "ide.debug",
        ide_debug,
        summary="IRIS IDE debug. op=start needs name (launch configuration). op=stop or continue. No session is not success.",
        risk="medium",
    )
    reg.register(
        "ide.plugin_status",
        ide_plugin_status,
        summary="Ask the IRIS IDE plugin host whether extension id is loaded. loaded false does not mean the viewer is open.",
        risk="low",
    )
    reg.register(
        "ide.project_log",
        ide_project_log,
        summary="Update the Iris wiki note for the project open in IRIS IDE. Optional plan, decision, issue, progress. Secrets are not stored.",
        risk="low",
    )
