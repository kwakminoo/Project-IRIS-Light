"""MainWindow ↔ Control Surface 액션 바인딩.

ponytail: UI 핸들러를 그대로 감싼다. 새 UX 없음.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from PyQt6.QtCore import QObject, Qt, pyqtSignal

from iris.storage.email_accounts import (
    add_email_account,
    find_account,
    load_email_accounts,
    remove_email_account,
)
from iris.storage.user_profile import UserProfile, load_user_profile, save_user_profile
from iris.system.control_surface import (
    ControlSurface,
    MainThreadInvoker,
    err_result,
    ok_result,
    resolve_control_token,
)
from iris.system.ide_launcher import ide_catalog, is_ide_installed
from iris.learning.permission import policy_for

if TYPE_CHECKING:
    from iris.ui.window.main_window import MainWindow


class _QtInvoker(QObject):
    _call = pyqtSignal(object, object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._call.connect(self._on_call, Qt.ConnectionType.QueuedConnection)

    def _on_call(self, fn: object, box: object) -> None:
        assert callable(fn) and isinstance(box, dict)
        try:
            box["value"] = fn()
            box["exc"] = None
        except Exception as exc:  # noqa: BLE001
            box["value"] = None
            box["exc"] = exc
        box["event"].set()

    def run(self, fn: Callable[[], Any], timeout: float = 15.0) -> Any:
        box: dict[str, Any] = {"event": threading.Event()}
        self._call.emit(fn, box)
        if not box["event"].wait(timeout):
            raise TimeoutError("Iris UI thread timeout")
        if box["exc"] is not None:
            raise box["exc"]
        return box["value"]


def _public_profile(p: UserProfile) -> dict[str, Any]:
    return {
        "name": p.name,
        "occupation": p.occupation,
        "hobbies": p.hobbies,
        "interests": p.interests,
        "work_tasks": p.work_tasks,
        "age": p.age,
        "gender": p.gender,
        "residence": p.residence,
        "contact": p.contact,
        "email": p.email,
        "preferred_ide": p.preferred_ide,
        "ide_exe_path": p.ide_exe_path,
        "ide_cli_path": p.ide_cli_path,
        "project_root": p.project_root,
        "project_parents": list(p.project_parents or []),
    }


def _profile_parents(window: MainWindow) -> list[Path]:
    from iris.system.project_ops import resolve_project_parents

    profile = load_user_profile(window._db)
    return resolve_project_parents(list(profile.project_parents or []))


def _ide_open_file_path(
    window: MainWindow,
    path: str,
    *,
    line: int = 1,
    column: int = 1,
    reuse_window: bool = True,
) -> dict[str, Any]:
    from iris.automation.ide_input import open_file_in_workspace, wait_ide_shows_file

    session = window._get_bound_ide_session(refresh=True)
    if session is None or not session.hwnd:
        return {
            "ok": False,
            "path": path,
            "error": "bound IDE session required",
            "line": line,
            "column": column,
        }
    ok = open_file_in_workspace(
        int(session.hwnd),
        path,
        workspace_root=session.workspace_root,
        pump=_qt_pump,
        pid=session.pid,
    )
    visible = False
    if ok:
        visible = wait_ide_shows_file(
            int(session.hwnd),
            path,
            timeout_sec=6.0,
            pump=_qt_pump,
        )
    return {
        "ok": bool(ok),
        "path": path,
        "error": None if ok else "bound IDE session quick open failed",
        "line": line,
        "column": column,
        "visible": visible,
        "hwnd": session.hwnd,
    }


def _bound_session(window: MainWindow, *, require_workspace: bool = False) -> tuple[Any, str]:
    session = window._get_bound_ide_session(refresh=True)
    if session is None:
        return None, "bound IDE session required"
    if require_workspace and (session.mode != "workspace" or not session.workspace_root):
        return None, "bound IDE workspace session required"
    return session, ""


def _qt_pump() -> None:
    try:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.processEvents()
    except Exception:
        pass


def start_control_surface(window: MainWindow) -> ControlSurface | None:
    """Control Surface 기동 + 액션 등록. 실패 시 None (앱은 계속)."""
    import os

    if getattr(window, "_test_mode", False):
        return None
    if os.environ.get("IRIS_CONTROL_ENABLED", "1").strip() in ("0", "false", "False"):
        return None

    host = (os.environ.get("IRIS_CONTROL_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = int((os.environ.get("IRIS_CONTROL_PORT") or "8765").strip() or "8765")
    except ValueError:
        port = 8765
    token = resolve_control_token()

    qt = _QtInvoker(window)
    invoker = MainThreadInvoker()
    invoker.bind(qt.run)
    surface = ControlSurface(invoker=invoker, host=host, port=port, token=token)
    _register_actions(window, surface)
    try:
        bound = surface.start()
    except OSError as exc:
        window._live_activity.append_instant_line(f"Iris control: bind failed ({exc})")
        return None

    # ponytail: sync는 UI 스레드에서 하지 않음 — /v1/state 프로브가 같은 스레드 invoker와
    # 데드락 나며 Windows "응답 없음"이 됨. HermesHealthWorker가 백그라운드에서 동기화.
    window._control_surface = surface  # type: ignore[attr-defined]
    window._control_qt_invoker = qt  # type: ignore[attr-defined]
    window._live_activity.append_instant_line(
        f"Iris control: listening on http://{host}:{bound} (MCP iris-control)"
    )
    return surface


def stop_control_surface(window: MainWindow) -> None:
    surface = getattr(window, "_control_surface", None)
    if surface is not None:
        try:
            surface.stop()
        except Exception:
            pass
        window._control_surface = None  # type: ignore[attr-defined]


def mark_control_ready(window: MainWindow) -> None:
    surface = getattr(window, "_control_surface", None)
    if surface is not None:
        surface.booting = False


def _log(window: MainWindow, action: str, ok: bool) -> None:
    status = "ok" if ok else "fail"
    try:
        window._live_activity.append_instant_line(f"Iris control: {action} {status}")
    except Exception:
        pass


def _register_actions(window: MainWindow, surface: ControlSurface) -> None:
    reg = surface.registry

    def ping(_args: dict[str, Any]) -> dict[str, Any]:
        return ok_result("ping", {"alive": True, "booting": surface.booting})

    def get_catalog(_args: dict[str, Any]) -> dict[str, Any]:
        return ok_result("get_catalog", {"actions": reg.catalog()})

    def get_state(_args: dict[str, Any]) -> dict[str, Any]:
        profile = load_user_profile(window._db)
        session = window._get_bound_ide_session(refresh=True)
        accounts = [
            {"id": a.id, "address": a.address, "label": a.label}
            for a in load_email_accounts(window._db)
        ]
        return ok_result(
            "get_state",
            {
                "booting": surface.booting,
                "ui_mode": window._ui_mode,
                "workspace_mode": window._workspace_mode,
                "preferred_ide": profile.preferred_ide,
                "project_root": profile.project_root,
                "project_parents": [str(p) for p in _profile_parents(window)],
                "ide_attached": bool(session),
                "ide_pid": session.pid if session else None,
                "ide_session": (
                    {
                        "active": session.active,
                        "ide_id": session.ide_id,
                        "hwnd": session.hwnd,
                        "pid": session.pid,
                        "workspace_root": session.workspace_root,
                        "mode": session.mode,
                        "source": session.source,
                        "last_seen_at": session.last_seen_at,
                    }
                    if session
                    else {
                        "active": False,
                        "ide_id": "",
                        "hwnd": None,
                        "pid": None,
                        "workspace_root": "",
                        "mode": "welcome",
                        "source": "",
                        "last_seen_at": 0.0,
                    }
                ),
                "hermes_online": bool(getattr(window, "_hermes_online", False)),
                "hermes_enabled": bool(window._settings.hermes_enabled),
                "model": window._settings.model_name or window._settings.ollama_model,
                "email_accounts": accounts,
                "selected_email_account_id": window._selected_email_account_id,
                "calendar": {
                    "year": getattr(getattr(window, "_calendar_page", None), "year", None),
                    "month": getattr(getattr(window, "_calendar_page", None), "month", None),
                    "selected_day": (
                        window._calendar_page.selected_day.isoformat()
                        if getattr(window, "_calendar_page", None) is not None
                        else ""
                    ),
                    "holiday_api_key": bool(
                        getattr(window._settings, "data_go_kr_service_key", "")
                    ),
                },
                "emulator_running": _emulator_running(),
                **_emulator_state_fields(),
            },
        )

    reg.register("ping", ping, summary="Iris alive check / ping")
    reg.register(
        "get_catalog",
        get_catalog,
        summary="List all Iris control actions (catalog)",
    )
    reg.register(
        "get_state",
        get_state,
        summary="Iris session state: ui_mode companion workspace IDE project_root model",
    )

    # --- window / IDE companion ---
    def window_minimize(_a: dict[str, Any]) -> dict[str, Any]:
        window.showMinimized()
        _log(window, "window.minimize", True)
        return ok_result("window.minimize", {})

    def window_toggle_maximize(_a: dict[str, Any]) -> dict[str, Any]:
        window._toggle_maximize()
        _log(window, "window.toggle_maximize", True)
        return ok_result("window.toggle_maximize", {"maximized": window.isMaximized()})

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

    def ide_open_folder(args: dict[str, Any]) -> dict[str, Any]:
        path = str(args.get("path") or args.get("folder") or args.get("project_root") or "").strip()
        if not path:
            return err_result("ide.open_folder", "path required")
        root = Path(path).expanduser()
        if not root.is_dir():
            return err_result("ide.open_folder", f"not a directory: {path}")
        new_window = bool(args.get("new_window", False))
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

    def project_list_parents(_a: dict[str, Any]) -> dict[str, Any]:
        parents = _profile_parents(window)
        profile = load_user_profile(window._db)
        return ok_result(
            "project.list_parents",
            {
                "parents": [str(p) for p in parents],
                "custom": list(profile.project_parents or []),
                "using_defaults": not bool(profile.project_parents),
            },
        )

    def project_find_similar(args: dict[str, Any]) -> dict[str, Any]:
        from iris.system.project_ops import find_similar_projects

        query = str(args.get("query") or args.get("name") or "").strip()
        if not query:
            return err_result("project.find_similar", "query required")
        limit = int(args.get("limit") or 8)
        parents = _profile_parents(window)
        hits = find_similar_projects(
            query, parents=parents, limit=max(1, min(limit, 20))
        )
        return ok_result(
            "project.find_similar",
            {
                "query": query,
                "matches": hits,
                "best": hits[0] if hits else None,
                "parents": [str(p) for p in parents],
            },
        )

    def project_open_similar(args: dict[str, Any]) -> dict[str, Any]:
        from iris.system.project_ops import pick_similar_project

        query = str(args.get("query") or args.get("name") or "").strip()
        if not query:
            return err_result(
                "project.open_similar",
                "query required — name a project, or use query like 'iris light'",
            )
        parents = _profile_parents(window)
        force = bool(args.get("force", False))
        best, hits, reason = pick_similar_project(
            query, parents=parents, force=force
        )
        if reason != "ok" or not best:
            hint = {
                "none": "no match — check project_parents in settings or give absolute path",
                "low_score": "weak match — ask user to pick, or force=true",
                "ambiguous": "multiple close matches — ask user, then ide.open_folder",
            }.get(reason, "could not pick")
            return err_result(
                "project.open_similar",
                f"{hint} (reason={reason})",
                {
                    "query": query,
                    "reason": reason,
                    "matches": hits,
                    "parents": [str(p) for p in parents],
                    "hint": "Call project.find_similar, ask user, then ide.open_folder with path",
                },
            )
        new_window = bool(args.get("new_window", False))
        err = window._open_ide_folder(best["path"], new_window=new_window, source="chat")
        ok = not err and window._ui_mode == "ide_companion"
        _log(window, "project.open_similar", ok)
        if not ok:
            return err_result(
                "project.open_similar",
                err or "open failed",
                {"match": best, "matches": hits, "ui_mode": window._ui_mode},
            )
        return ok_result(
            "project.open_similar",
            {
                "query": query,
                "match": best,
                "matches": hits,
                "reason": reason,
                "ui_mode": window._ui_mode,
                "ide_hwnd": getattr(window._ide_session, "hwnd", None),
            },
        )

    def project_create_scaffold(args: dict[str, Any]) -> dict[str, Any]:
        from iris.system.project_ops import create_scaffold

        name = str(args.get("name") or "").strip()
        if not name:
            return err_result("project.create_scaffold", "name required")
        parent = str(args.get("parent") or "").strip()
        if not parent:
            parents = _profile_parents(window)
            parent = str(parents[0]) if parents else str(Path.home() / "Desktop")
        template = str(args.get("template") or "empty").strip() or "empty"
        try:
            created = create_scaffold(parent, name, template=template)
        except Exception as exc:  # noqa: BLE001
            return err_result("project.create_scaffold", str(exc))
        open_ide = bool(args.get("open", True))
        result: dict[str, Any] = {"created": created}
        if open_ide:
            err = window._open_ide_folder(
                created["path"],
                new_window=bool(args.get("new_window", False)),
                source="chat",
            )
            result["open_error"] = err or None
            result["ui_mode"] = window._ui_mode
            if err:
                _log(window, "project.create_scaffold", False)
                return err_result(
                    "project.create_scaffold",
                    f"created but open failed: {err}",
                    result,
                )
            # 첫 소스 파일을 IDE 에디터에 보이게
            for rel in created.get("files") or []:
                if str(rel).endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".md")):
                    if str(rel).lower() == "readme.md":
                        continue
                    opened = _ide_open_file_path(
                        window, str(Path(created["path"]) / rel)
                    )
                    result["opened_file"] = opened
                    break
        _log(window, "project.create_scaffold", True)
        return ok_result("project.create_scaffold", result)

    def project_write_file(args: dict[str, Any]) -> dict[str, Any]:
        from iris.automation.ide_input import (
            open_file_in_workspace,
            typewriter_into_ide,
            wait_ide_shows_file,
        )
        from iris.system.ide_launcher import open_file_in_ide
        from iris.system.project_ops import (
            resolve_under_root,
            write_project_file,
            write_project_file_stream,
        )

        root = str(args.get("project_root") or args.get("root") or "").strip()
        if not root:
            profile = load_user_profile(window._db)
            root = (profile.project_root or "").strip()
        rel = str(args.get("rel_path") or args.get("path") or "").strip()
        content = args.get("content")
        if content is None:
            return err_result("project.write_file", "content required")
        if not root or not rel:
            return err_result("project.write_file", "project_root and rel_path required")
        do_open = bool(args.get("open", True))
        session, session_err = _bound_session(window, require_workspace=do_open)
        if do_open and session_err:
            return err_result("project.write_file", session_err)
        # open=true 이면 기본 live file stream. 명시 stream/typewriter=false 만 즉시 쓰기.
        if "typewriter" in args:
            do_type = bool(args.get("typewriter"))
        elif "stream" in args:
            do_type = bool(args.get("stream"))
        else:
            do_type = do_open
        text = str(content)
        try:
            _root, abs_path, norm_rel = resolve_under_root(root, rel)
            if do_open and session is not None:
                if str(_root) != str(Path(session.workspace_root).resolve()):
                    return err_result(
                        "project.write_file",
                        "requested project_root does not match bound IDE workspace",
                        {
                            "project_root": str(_root),
                            "bound_workspace_root": session.workspace_root,
                        },
                    )
            path_s = str(abs_path)
            if not do_open:
                written = write_project_file(root, rel, text)
                written["opened"] = False
                written["typed"] = False
                written["visible"] = False
                _log(window, "project.write_file", True)
                return ok_result("project.write_file", written)

            # 1) 빈 파일로 만들고 탭 열기
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text("", encoding="utf-8")
            hwnd = int(session.hwnd) if session is not None and session.hwnd else None
            pid = session.pid if session is not None else None
            opened = bool(
                hwnd
                and open_file_in_workspace(
                    hwnd,
                    path_s,
                    workspace_root=session.workspace_root if session is not None else "",
                    pump=_qt_pump,
                    pid=pid,
                )
            )
            visible = False
            if hwnd and opened:
                visible = wait_ide_shows_file(
                    hwnd,
                    path_s,
                    timeout_sec=float(args.get("visible_timeout_sec") or 6),
                    pump=_qt_pump,
                )
            if hwnd and opened and not visible:
                profile = load_user_profile(window._db)
                cli_opened, _cli_err = open_file_in_ide(
                    profile.preferred_ide,
                    path_s,
                    ide_exe_path=profile.ide_exe_path,
                    ide_cli_path=profile.ide_cli_path,
                    reuse_window=True,
                )
                if cli_opened:
                    visible = wait_ide_shows_file(
                        hwnd,
                        path_s,
                        timeout_sec=float(args.get("visible_timeout_sec") or 6),
                        pump=_qt_pump,
                    )
            typed = False
            streamed = False
            stream_result: dict[str, Any] = {}
            input_mode = str(args.get("input_mode") or "").strip().lower()
            if do_type and hwnd and opened and input_mode == "keyboard":
                typed = typewriter_into_ide(
                    hwnd,
                    text,
                    delay_ms=int(args["delay_ms"]) if args.get("delay_ms") is not None else None,
                    pump=_qt_pump,
                    pid=pid,
                )
                abs_path.write_text(text, encoding="utf-8")
            elif do_type and hwnd and opened:
                chunk_chars = int(
                    args.get("chunk_chars")
                    or max(12, min(48, max(1, len(text)) // 100))
                )
                chunk_delay_ms = int(args.get("chunk_delay_ms") or args.get("delay_ms") or 70)
                stream_result = write_project_file_stream(
                    root,
                    norm_rel,
                    text,
                    chunk_chars=chunk_chars,
                    chunk_delay_ms=chunk_delay_ms,
                    pump=_qt_pump,
                )
                streamed = True
            elif do_type:
                return err_result(
                    "project.write_file",
                    "bound IDE session could not open file for live write",
                    {"path": path_s, "opened": bool(opened), "visible": bool(visible)},
                )
            else:
                abs_path.write_text(text, encoding="utf-8")
                if not (hwnd and opened):
                    return err_result(
                        "project.write_file",
                        "bound IDE session could not open file",
                        {"path": path_s, "opened": bool(opened), "visible": bool(visible)},
                    )

            written = {
                "path": path_s,
                "rel_path": norm_rel,
                "bytes": len(text.encode("utf-8")),
                "opened": bool(opened),
                "open_error": None if opened else "quick open failed",
                "visible": bool(visible),
                "typed": bool(typed),
                "streamed": bool(streamed),
                "input_mode": "keyboard" if typed else ("file_watch" if streamed else "instant"),
                "chunks": int(stream_result.get("chunks") or 0),
                "chunk_chars": int(stream_result.get("chunk_chars") or 0),
                "chunk_delay_ms": int(stream_result.get("chunk_delay_ms") or 0),
            }
        except Exception as exc:  # noqa: BLE001
            return err_result("project.write_file", str(exc))
        _log(window, "project.write_file", True)
        return ok_result("project.write_file", written)

    def ide_open_file(args: dict[str, Any]) -> dict[str, Any]:
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

    def project_run(args: dict[str, Any]) -> dict[str, Any]:
        import time

        from iris.automation.ide_input import run_command_in_ide_terminal, trigger_default_build_task
        from iris.system.project_ops import (
            build_iris_terminal_command,
            build_run_command,
            iris_run_log_path,
            result_from_terminal_log,
            summarize_run,
            upsert_iris_run_task,
            wait_for_run_log,
        )

        root = str(args.get("project_root") or args.get("root") or args.get("cwd") or "").strip()
        if not root:
            profile = load_user_profile(window._db)
            root = (profile.project_root or "").strip()
        if not root:
            return err_result("project.run", "project_root required")
        root_p = Path(root).expanduser()
        if not root_p.is_dir():
            return err_result("project.run", f"not a directory: {root}")
        root_s = str(root_p.resolve())
        reveal = bool(args.get("reveal_terminal", True))
        session, session_err = _bound_session(window, require_workspace=True)
        if session_err:
            return err_result("project.run", session_err)
        if str(Path(session.workspace_root).resolve()) != root_s:
            return err_result(
                "project.run",
                "requested project_root does not match bound IDE workspace",
                {"project_root": root_s, "bound_workspace_root": session.workspace_root},
            )
        timeout_sec = float(args.get("timeout_sec") or 60)
        try:
            argv = build_run_command(
                command=args.get("command"),
                file=str(args.get("file") or args.get("rel_path") or ""),
            )
        except Exception as exc:  # noqa: BLE001
            return err_result("project.run", str(exc))

        log_p = iris_run_log_path(root_s)
        try:
            if log_p.is_file():
                log_p.unlink()
        except OSError:
            pass

        shell_cmd = build_iris_terminal_command(argv)
        tasks_path = ""
        try:
            tasks_path = upsert_iris_run_task(root_s, shell_cmd)
        except Exception as exc:  # noqa: BLE001
            tasks_path = ""

        ide_terminal = "failed"
        result: dict[str, Any]
        hwnd = int(session.hwnd) if session and session.hwnd else None
        pid = session.pid if session else None
        t0 = time.monotonic()

        if not reveal:
            return err_result("project.run", "project.run requires IDE integrated terminal")
        if not hwnd or not tasks_path:
            return err_result(
                "project.run",
                "bound IDE session missing or Iris run task could not be prepared",
                {"tasks_path": tasks_path or None, "hwnd": hwnd},
            )
        time.sleep(0.35)
        triggered = trigger_default_build_task(hwnd, pid=pid)
        if not triggered:
            return err_result("project.run", "failed to trigger IDE integrated terminal run task")
        waited = wait_for_run_log(
            log_p,
            timeout_sec=timeout_sec,
            stable_sec=0.8,
            pump=_qt_pump,
        )
        elapsed = time.monotonic() - t0
        if not waited.get("found"):
            rerun_ok = run_command_in_ide_terminal(hwnd, shell_cmd, pump=_qt_pump, pid=pid)
            if not rerun_ok:
                return err_result(
                    "project.run",
                    "IDE integrated terminal run started but no Iris log was captured",
                    {"tasks_path": tasks_path or None, "log_path": str(log_p)},
                )
            waited = wait_for_run_log(
                log_p,
                timeout_sec=timeout_sec,
                stable_sec=0.8,
                pump=_qt_pump,
            )
            elapsed = time.monotonic() - t0
            if not waited.get("found"):
                return err_result(
                    "project.run",
                    "IDE integrated terminal run started but no Iris log was captured",
                    {"tasks_path": tasks_path or None, "log_path": str(log_p)},
                )
        result = result_from_terminal_log(
            str(waited.get("text") or ""),
            argv=argv,
            cwd=root_s,
            elapsed_sec=elapsed,
        )
        ide_terminal = "ok"

        summary_bits = summarize_run(result)
        if ide_terminal == "ok":
            summary_bits["summary"] += " · output in IDE terminal"

        payload = {
            **result,
            **summary_bits,
            "ide_terminal": ide_terminal,
            "log_path": str(log_p) if log_p.is_file() else None,
            "tasks_path": tasks_path or None,
            "opened_log": False,
            "stdout_len": len(result.get("stdout") or ""),
            "stderr_len": len(result.get("stderr") or ""),
        }
        payload.pop("stdout", None)
        payload.pop("stderr", None)
        ok = int(result.get("exit_code") or 0) == 0 and not result.get("timed_out")
        _log(window, "project.run", ok)
        return ok_result("project.run", payload) if ok else err_result(
            "project.run",
            summary_bits.get("summary") or f"exit {result.get('exit_code')}",
            payload,
        )

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
        summary="Open folder in the bound IDE session by default; new window only when requested",
        risk="medium",
    )
    reg.register(
        "ide.open_file",
        ide_open_file,
        summary="Open a file in the currently bound IDE session editor",
        risk="medium",
    )
    reg.register(
        "project.list_parents",
        project_list_parents,
        summary="List project search parent folders (settings project_parents or built-in defaults)",
    )
    reg.register(
        "project.find_similar",
        project_find_similar,
        summary="Fuzzy-find project folders under configured parents by name (e.g. ai guitar tab → AI-Guitar-Tab-main)",
    )
    reg.register(
        "project.open_similar",
        project_open_similar,
        summary="Fuzzy-find best matching project and open in Companion; on ambiguous/low_score returns matches (use force=true to override)",
        risk="medium",
    )
    reg.register(
        "project.create_scaffold",
        project_create_scaffold,
        summary="Create project folder + template (gugudan|python-hello|empty), optionally open in IDE",
        risk="medium",
    )
    reg.register(
        "project.write_file",
        project_write_file,
        summary="Write file under the bound IDE workspace; open=true reveals tab then streams chunks",
        risk="medium",
    )
    reg.register(
        "project.run",
        project_run,
        summary="Run only in the bound IDE integrated terminal via Iris: Run task",
        risk="medium",
    )

    # --- profile / IDE prefs ---
    def profile_get(_a: dict[str, Any]) -> dict[str, Any]:
        return ok_result("profile.get", _public_profile(load_user_profile(window._db)))

    def profile_set(args: dict[str, Any]) -> dict[str, Any]:
        from iris.storage.user_profile import parse_project_parents

        profile = load_user_profile(window._db)
        fields = UserProfile.__dataclass_fields__
        changed: list[str] = []
        for key, val in args.items():
            if key in ("confirm",):
                continue
            if key not in fields:
                continue
            if key == "project_parents":
                profile.project_parents = parse_project_parents(val)
            else:
                setattr(profile, key, str(val or ""))
            changed.append(key)
        if "project_root" in changed and profile.project_root.strip():
            root = Path(profile.project_root).expanduser()
            if not root.is_dir():
                return err_result("profile.set", f"project_root not a directory: {profile.project_root}")
            profile.project_root = str(root.resolve())
        if "project_parents" in changed and profile.project_parents:
            cleaned: list[str] = []
            for raw in profile.project_parents:
                p = Path(raw).expanduser()
                if not p.is_dir():
                    return err_result(
                        "profile.set",
                        f"project_parents entry not a directory: {raw}",
                    )
                cleaned.append(str(p.resolve()))
            profile.project_parents = cleaned
        if "preferred_ide" in changed and profile.preferred_ide.strip():
            ide_id = profile.preferred_ide.strip().lower()
            profile.preferred_ide = ide_id
            if ide_id != "custom" and not is_ide_installed(ide_id, profile.ide_exe_path):
                return err_result("profile.set", f"IDE not installed: {ide_id}")
        save_user_profile(window._db, profile)
        _log(window, "profile.set", True)
        return ok_result("profile.set", {"changed": changed, "profile": _public_profile(profile)})

    def ide_set_preferred(args: dict[str, Any]) -> dict[str, Any]:
        ide_id = str(args.get("ide_id") or args.get("preferred_ide") or "").strip().lower()
        if not ide_id:
            return err_result("ide.set_preferred", "ide_id required")
        known = {s.id for s in ide_catalog()} | {"custom"}
        if ide_id not in known:
            return err_result("ide.set_preferred", f"unknown ide_id: {ide_id}", {"known": sorted(known)})
        profile = load_user_profile(window._db)
        if ide_id != "custom" and not is_ide_installed(ide_id, profile.ide_exe_path):
            return err_result("ide.set_preferred", f"IDE not installed: {ide_id}")
        profile.preferred_ide = ide_id
        if ide_id != "custom":
            profile.ide_exe_path = ""
        save_user_profile(window._db, profile)
        _log(window, "ide.set_preferred", True)
        return ok_result("ide.set_preferred", {"preferred_ide": ide_id})

    def ide_set_project_root(args: dict[str, Any]) -> dict[str, Any]:
        path = str(args.get("path") or args.get("project_root") or "").strip()
        if not path:
            return err_result("ide.set_project_root", "path required")
        root = Path(path).expanduser()
        if not root.is_dir():
            return err_result("ide.set_project_root", f"not a directory: {path}")
        profile = load_user_profile(window._db)
        profile.project_root = str(root.resolve())
        save_user_profile(window._db, profile)
        _log(window, "ide.set_project_root", True)
        return ok_result("ide.set_project_root", {"project_root": profile.project_root})

    def ide_list(_a: dict[str, Any]) -> dict[str, Any]:
        profile = load_user_profile(window._db)
        items = []
        for spec in ide_catalog():
            items.append(
                {
                    "id": spec.id,
                    "name": spec.name,
                    "installed": is_ide_installed(spec.id, ""),
                }
            )
        items.append(
            {
                "id": "custom",
                "name": "Custom",
                "installed": bool(profile.ide_exe_path and Path(profile.ide_exe_path).is_file()),
            }
        )
        return ok_result("ide.list", {"ides": items, "preferred_ide": profile.preferred_ide})

    reg.register("profile.get", profile_get, summary="Get user profile (no secrets)")
    reg.register(
        "profile.set",
        profile_set,
        summary="Set user profile fields: name preferred_ide project_root project_parents ide paths",
        risk="medium",
    )
    reg.register(
        "ide.set_preferred",
        ide_set_preferred,
        summary="Set preferred IDE id (cursor vscode pycharm … or custom)",
        risk="medium",
    )
    reg.register(
        "ide.set_project_root",
        ide_set_project_root,
        summary="Set project_root folder for IDE Companion / vibe coding",
        risk="medium",
    )
    reg.register("ide.list", ide_list, summary="List IDE catalog and install status")

    # --- workspaces ---
    def ws_assistant(_a: dict[str, Any]) -> dict[str, Any]:
        window._show_assistant_workspace()
        _log(window, "workspace.open_assistant", True)
        return ok_result("workspace.open_assistant", {"workspace_mode": window._workspace_mode})

    def ws_obsidian(_a: dict[str, Any]) -> dict[str, Any]:
        window._on_obsidian_icon()
        _log(window, "workspace.open_obsidian", True)
        return ok_result("workspace.open_obsidian", {"workspace_mode": window._workspace_mode})

    def ws_email(_a: dict[str, Any]) -> dict[str, Any]:
        window._on_email_icon()
        _log(window, "workspace.open_email", True)
        return ok_result("workspace.open_email", {"workspace_mode": window._workspace_mode})

    def ws_calendar(_a: dict[str, Any]) -> dict[str, Any]:
        window._on_calendar_icon()
        _log(window, "workspace.open_calendar", True)
        return ok_result("workspace.open_calendar", {"workspace_mode": window._workspace_mode})

    def ws_mobile(_a: dict[str, Any]) -> dict[str, Any]:
        window._on_mobile_icon()
        _log(window, "workspace.open_mobile", True)
        return ok_result(
            "workspace.open_mobile",
            {"emulator_running": _emulator_running()},
        )

    def ws_stub(name: str) -> HandlerFn:
        def _h(_a: dict[str, Any]) -> dict[str, Any]:
            return err_result(name, "not implemented in Iris UI yet (준비 중)")

        return _h

    reg.register(
        "workspace.open_assistant",
        ws_assistant,
        summary="Open assistant / home workspace (orb + chat)",
    )
    reg.register(
        "workspace.open_obsidian",
        ws_obsidian,
        summary="Open Iris Wiki / Obsidian workspace",
    )
    reg.register(
        "workspace.open_email",
        ws_email,
        summary="Open email workspace inbox",
    )
    reg.register(
        "workspace.open_calendar",
        ws_calendar,
        summary="Open calendar workspace (KR holidays + schedule)",
    )
    reg.register(
        "workspace.open_mobile",
        ws_mobile,
        summary="Launch Android emulator (mobile icon)",
    )
    for stub_id, label in (
        ("workspace.open_instagram", "Instagram"),
        ("workspace.open_discord", "Discord"),
        ("workspace.open_kakao", "KakaoTalk"),
        ("workspace.open_telegram", "Telegram"),
    ):
        reg.register(stub_id, ws_stub(stub_id), summary=f"{label} workspace (준비 중)", risk="low")

    def cal_list(_a: dict[str, Any]) -> dict[str, Any]:
        from iris.storage.calendar_events import events_as_dicts, list_events

        events = list_events(window._db)
        return ok_result("calendar.list_events", {"events": events_as_dicts(events)})

    def cal_add(a: dict[str, Any]) -> dict[str, Any]:
        from iris.infrastructure.calendar_agent import normalize_start_at
        from iris.storage.calendar_events import add_event, events_as_dicts

        title = str(a.get("title") or "").strip()
        start = str(a.get("start_at") or "").strip()
        if not title or not start:
            return err_result("calendar.add_event", "title and start_at required")
        end_raw = str(a.get("end_at") or "").strip()
        try:
            ev = add_event(
                window._db,
                title=title,
                start_at=normalize_start_at(start),
                end_at=normalize_start_at(end_raw) if end_raw else "",
                note=str(a.get("note") or "").strip(),
                place=str(a.get("place") or "").strip(),
            )
        except Exception as exc:
            return err_result("calendar.add_event", str(exc))
        window._sync_calendar_wiki()
        if getattr(window, "_workspace_mode", "") == "calendar":
            window._reload_calendar_month()
        return ok_result("calendar.add_event", {"event": events_as_dicts([ev])[0]})

    def cal_delete(a: dict[str, Any]) -> dict[str, Any]:
        from iris.storage.calendar_events import delete_event

        try:
            eid = int(a.get("id"))
        except (TypeError, ValueError):
            return err_result("calendar.delete_event", "id required")
        ok = delete_event(window._db, eid)
        if ok:
            window._sync_calendar_wiki()
            if getattr(window, "_workspace_mode", "") == "calendar":
                window._reload_calendar_month()
        return ok_result("calendar.delete_event", {"deleted": ok, "id": eid})

    reg.register("calendar.list_events", cal_list, summary="List calendar events")
    reg.register(
        "calendar.add_event",
        cal_add,
        summary="Add calendar event (title, start_at, optional end_at/note/place)",
        risk="medium",
    )
    reg.register(
        "calendar.delete_event",
        cal_delete,
        summary="Delete calendar event by id",
        risk="medium",
    )

    def cal_select_day(a: dict[str, Any]) -> dict[str, Any]:
        day = str(a.get("date") or a.get("day") or "").strip()
        if not day:
            return err_result("calendar.select_day", "date (YYYY-MM-DD) required")
        try:
            if getattr(window, "_workspace_mode", "") != "calendar":
                window._on_calendar_icon()
            selected = window._calendar_page.select_day_iso(day)
            window._reload_calendar_month()
        except Exception as exc:
            return err_result("calendar.select_day", str(exc))
        return ok_result(
            "calendar.select_day",
            {
                "date": selected.isoformat(),
                "year": window._calendar_page.year,
                "month": window._calendar_page.month,
            },
        )

    def cal_set_month(a: dict[str, Any]) -> dict[str, Any]:
        try:
            year = int(a.get("year"))
            month = int(a.get("month"))
        except (TypeError, ValueError):
            return err_result("calendar.set_month", "year and month required")
        try:
            if getattr(window, "_workspace_mode", "") != "calendar":
                window._on_calendar_icon()
            window._calendar_page.set_month(year, month)
            window._reload_calendar_month()
            window._refresh_calendar_holidays()
        except Exception as exc:
            return err_result("calendar.set_month", str(exc))
        return ok_result(
            "calendar.set_month",
            {"year": window._calendar_page.year, "month": window._calendar_page.month},
        )

    def cal_refresh_holidays(_a: dict[str, Any]) -> dict[str, Any]:
        if getattr(window, "_workspace_mode", "") != "calendar":
            window._on_calendar_icon()
        window._refresh_calendar_holidays()
        return ok_result(
            "calendar.refresh_holidays",
            {
                "year": window._calendar_page.year,
                "key_configured": bool(window._settings.data_go_kr_service_key),
            },
        )

    def cal_status(_a: dict[str, Any]) -> dict[str, Any]:
        from iris.storage.calendar_events import events_as_dicts, list_events

        page = getattr(window, "_calendar_page", None)
        events = list_events(window._db)
        return ok_result(
            "calendar.status",
            {
                "workspace_mode": getattr(window, "_workspace_mode", ""),
                "year": getattr(page, "year", None),
                "month": getattr(page, "month", None),
                "selected_day": (
                    page.selected_day.isoformat() if page is not None else ""
                ),
                "event_count": len(events),
                "events": events_as_dicts(events[:30]),
                "holiday_api_key": bool(window._settings.data_go_kr_service_key),
            },
        )

    reg.register(
        "calendar.select_day",
        cal_select_day,
        summary="Open calendar and select a day (date=YYYY-MM-DD)",
    )
    reg.register(
        "calendar.set_month",
        cal_set_month,
        summary="Open calendar and show year/month",
    )
    reg.register(
        "calendar.refresh_holidays",
        cal_refresh_holidays,
        summary="Refresh KR public holidays for current calendar year",
    )
    reg.register(
        "calendar.status",
        cal_status,
        summary="Calendar workspace status + upcoming events summary",
    )

    # --- Android emulator (adb; IrisLight_Pixel only) ---
    def emu_status(_a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import emulator_status

        return ok_result("emulator.status", emulator_status())

    def emu_launch(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import (
            AdbError,
            emulator_status,
            is_emulator_running,
            launch_emulator,
            read_launch_log_tail,
            restart_emulator_windowed,
        )

        headless = bool(a.get("headless", False))
        try:
            if is_emulator_running():
                from iris.system.android_emulator import is_emulator_headless

                if is_emulator_headless() and not headless:
                    proc = restart_emulator_windowed()
                    _log(window, "emulator.launch", True)
                    return ok_result(
                        "emulator.launch",
                        {
                            "pid": proc.pid,
                            "restarted_windowed": True,
                            **emulator_status(),
                        },
                    )
                return ok_result(
                    "emulator.launch",
                    {"already_running": True, **emulator_status()},
                )
            proc = launch_emulator(headless=headless)
            _log(window, "emulator.launch", True)
            window._live_activity.append_instant_line(
                f"Android 에뮬레이터 시작 (PID {proc.pid})"
            )
            return ok_result(
                "emulator.launch",
                {"pid": proc.pid, **emulator_status()},
            )
        except (OSError, AdbError, FileNotFoundError) as exc:
            _log(window, "emulator.launch", False)
            tail = read_launch_log_tail(lines=20)
            detail = str(exc)
            if tail:
                detail = f"{detail}\n--- launch log ---\n{tail[:800]}"
            return err_result("emulator.launch", detail)

    def emu_wait_ready(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, emulator_status, wait_for_boot

        timeout_s = float(a.get("timeout_s") or 180)
        try:
            serial = wait_for_boot(timeout_s=timeout_s)
            _log(window, "emulator.wait_ready", True)
            return ok_result(
                "emulator.wait_ready",
                {"serial": serial, **emulator_status()},
            )
        except AdbError as exc:
            return err_result("emulator.wait_ready", str(exc))

    def emu_kill(_a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, emulator_status, kill_emulator

        try:
            killed = kill_emulator()
            _log(window, "emulator.kill", True)
            return ok_result("emulator.kill", {"killed": killed, **emulator_status()})
        except AdbError as exc:
            return err_result("emulator.kill", str(exc))

    def emu_install(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, install_apk

        apk = str(a.get("apk") or "").strip()
        if not apk:
            return err_result("emulator.install", "apk path required")
        try:
            output = install_apk(apk)
            _log(window, "emulator.install", True)
            return ok_result("emulator.install", {"apk": apk, "output": output})
        except AdbError as exc:
            return err_result("emulator.install", str(exc))

    def emu_start_app(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, start_app

        package = str(a.get("package") or "").strip()
        activity = str(a.get("activity") or "").strip()
        if not package:
            return err_result("emulator.start_app", "package required")
        # convenience: "설정" → Settings
        if package.lower() in ("settings", "설정", "설정앱"):
            package = "com.android.settings"
            activity = ""
        try:
            start_app(package, activity)
            _log(window, "emulator.start_app", True)
            return ok_result(
                "emulator.start_app",
                {"package": package, "activity": activity or None},
            )
        except AdbError as exc:
            return err_result("emulator.start_app", str(exc))

    def emu_key(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, press_key

        key = str(a.get("key") or "").strip()
        if not key:
            return err_result("emulator.key", "key required")
        try:
            press_key(key)
            return ok_result("emulator.key", {"key": key.upper()})
        except AdbError as exc:
            return err_result("emulator.key", str(exc))

    def emu_input_text(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, input_text

        if "text" not in a:
            return err_result("emulator.input_text", "text required")
        text = str(a.get("text") or "")
        try:
            input_text(text)
            return ok_result("emulator.input_text", {"text": text})
        except AdbError as exc:
            return err_result("emulator.input_text", str(exc))

    def _as_int(name: str, raw: object) -> int:
        if isinstance(raw, bool) or raw is None:
            raise ValueError(f"{name} must be int")
        return int(raw)

    def emu_tap(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, tap

        try:
            x = _as_int("x", a.get("x"))
            y = _as_int("y", a.get("y"))
            tap(x, y)
            return ok_result("emulator.tap", {"x": x, "y": y})
        except (AdbError, ValueError, TypeError) as exc:
            return err_result("emulator.tap", str(exc))

    def emu_swipe(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, swipe

        try:
            x1 = _as_int("x1", a.get("x1"))
            y1 = _as_int("y1", a.get("y1"))
            x2 = _as_int("x2", a.get("x2"))
            y2 = _as_int("y2", a.get("y2"))
            duration_ms = int(a.get("duration_ms") or 300)
            swipe(x1, y1, x2, y2, duration_ms=duration_ms)
            return ok_result(
                "emulator.swipe",
                {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "duration_ms": duration_ms},
            )
        except (AdbError, ValueError, TypeError) as exc:
            return err_result("emulator.swipe", str(exc))

    def emu_screenshot(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, screenshot

        path = str(a.get("path") or "").strip()
        try:
            saved = screenshot(path)
            _log(window, "emulator.screenshot", True)
            return ok_result("emulator.screenshot", {"path": saved})
        except AdbError as exc:
            return err_result("emulator.screenshot", str(exc))

    def emu_ui_texts(_a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, ui_texts

        try:
            texts = ui_texts()
            return ok_result("emulator.ui_texts", {"texts": texts, "count": len(texts)})
        except AdbError as exc:
            return err_result("emulator.ui_texts", str(exc))

    def emu_tap_text(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, tap_text

        text = str(a.get("text") or "").strip()
        if not text:
            return err_result("emulator.tap_text", "text required")
        try:
            hit = tap_text(text, exact=bool(a.get("exact", False)))
            _log(window, "emulator.tap_text", True)
            return ok_result("emulator.tap_text", hit)
        except AdbError as exc:
            return err_result("emulator.tap_text", str(exc))

    def emu_play_install(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, play_install

        app = str(a.get("app") or a.get("package") or "").strip()
        if not app:
            return err_result("emulator.play_install", "app/package required")
        try:
            result = play_install(app, timeout_s=float(a.get("timeout_s") or 300))
            _log(window, "emulator.play_install", True)
            window._live_activity.append_instant_line(
                f"Play 설치 완료: {result['package']}"
            )
            return ok_result("emulator.play_install", result)
        except (AdbError, ValueError, TypeError) as exc:
            _log(window, "emulator.play_install", False)
            return err_result("emulator.play_install", str(exc))

    def emu_logcat(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, logcat_tail

        try:
            lines_n = int(a.get("lines") or 100)
            filt = str(a.get("filter") or "").strip()
            rows = logcat_tail(lines_n, filt)
            return ok_result(
                "emulator.logcat_tail",
                {"lines": rows, "count": len(rows), "filter": filt or None},
            )
        except (AdbError, ValueError, TypeError) as exc:
            return err_result("emulator.logcat_tail", str(exc))

    reg.register("emulator.status", emu_status, summary="Android emulator status (AVD serials)")
    reg.register(
        "emulator.launch",
        emu_launch,
        summary="Launch IrisLight_Pixel Android emulator",
        risk="medium",
    )
    reg.register(
        "emulator.wait_ready",
        emu_wait_ready,
        summary="Wait until adb serial + boot_completed",
        risk="low",
    )
    reg.register(
        "emulator.kill",
        emu_kill,
        summary="Kill IrisLight_Pixel Android emulator",
        risk="medium",
    )
    reg.register(
        "emulator.install",
        emu_install,
        summary="adb install -r APK on emulator",
        risk="medium",
    )
    reg.register(
        "emulator.start_app",
        emu_start_app,
        summary="Start app by package (optional activity)",
        risk="medium",
    )
    reg.register(
        "emulator.key",
        emu_key,
        summary="Send keyevent HOME|BACK|ENTER|APP_SWITCH|POWER",
        risk="medium",
    )
    reg.register(
        "emulator.input_text",
        emu_input_text,
        summary="Type text via adb input text",
        risk="medium",
    )
    reg.register(
        "emulator.tap",
        emu_tap,
        summary="Tap screen at x,y",
        risk="medium",
    )
    reg.register(
        "emulator.swipe",
        emu_swipe,
        summary="Swipe from x1,y1 to x2,y2",
        risk="medium",
    )
    reg.register(
        "emulator.screenshot",
        emu_screenshot,
        summary="Capture emulator screenshot to file",
        risk="medium",
    )
    reg.register(
        "emulator.ui_texts",
        emu_ui_texts,
        summary="List on-screen texts via uiautomator (no coordinates needed)",
        risk="low",
    )
    reg.register(
        "emulator.tap_text",
        emu_tap_text,
        summary="Tap the on-screen element whose text/description matches",
        risk="medium",
    )
    reg.register(
        "emulator.play_install",
        emu_play_install,
        summary="Install app from Play Store via market:// deep link + UI tree",
        risk="medium",
    )
    reg.register(
        "emulator.logcat_tail",
        emu_logcat,
        summary="Read recent logcat lines (optional filter)",
        risk="low",
    )

    # --- Learned workflows (ShowUI-Aloha) ---
    def learning_list(_a: dict[str, Any]) -> dict[str, Any]:
        mgr = getattr(window, "_learning", None)
        if mgr is None:
            return err_result("learning.list", "learning manager unavailable")
        enabled_only = bool(_a.get("enabled_only", False))
        items = []
        for wf in mgr.list_learned_workflows(enabled_only=enabled_only):
            items.append(
                {
                    "id": wf.id,
                    "trace_id": wf.trace_id,
                    "name": wf.name,
                    "summary": wf.summary,
                    "status": wf.status,
                    "primary_apps": wf.primary_apps,
                    "run_count": wf.run_count,
                    "enabled": bool(wf.enabled),
                    "trace_path": wf.trace_path,
                }
            )
        return ok_result("learning.list", {"workflows": items})

    def learning_get(args: dict[str, Any]) -> dict[str, Any]:
        mgr = getattr(window, "_learning", None)
        if mgr is None:
            return err_result("learning.get", "learning manager unavailable")
        wid = args.get("id") or args.get("workflow_id")
        if wid is None:
            return err_result("learning.get", "id required")
        wf = mgr.get_learned_workflow(int(wid))
        if wf is None:
            return err_result("learning.get", f"workflow {wid} not found")
        return ok_result(
            "learning.get",
            {
                "id": wf.id,
                "trace_id": wf.trace_id,
                "name": wf.name,
                "summary": wf.summary,
                "status": wf.status,
                "primary_apps": wf.primary_apps,
                "run_count": wf.run_count,
                "enabled": bool(wf.enabled),
                "trace_path": wf.trace_path,
                "source_session_id": wf.source_session_id,
            },
        )

    def learning_run(args: dict[str, Any]) -> dict[str, Any]:
        mgr = getattr(window, "_learning", None)
        if mgr is None:
            return err_result("learning.run", "learning manager unavailable")
        task = str(args.get("task") or "").strip()
        wid = args.get("id") or args.get("workflow_id")
        trace_id = str(args.get("trace_id") or "").strip()
        try:
            if wid is not None:
                run = mgr.run_learned_workflow(int(wid), task)
            elif trace_id:
                run = mgr.execute_workflow(trace_id, task)
            else:
                return err_result("learning.run", "id or trace_id required")
        except Exception as exc:
            return err_result("learning.run", str(exc)[:300])
        return ok_result(
            "learning.run",
            {
                "run_id": run.run_id,
                "workflow_id": run.workflow_id,
                "trace_id": run.trace_id,
                "task": run.task,
                "status": run.status,
                "message": run.message,
            },
        )

    def learning_run_status(args: dict[str, Any]) -> dict[str, Any]:
        mgr = getattr(window, "_learning", None)
        if mgr is None:
            return err_result("learning.run_status", "learning manager unavailable")
        run_id = str(args.get("run_id") or "").strip()
        if not run_id:
            return err_result("learning.run_status", "run_id required")
        run = mgr.get_workflow_run_status(run_id)
        if run is None:
            return err_result("learning.run_status", f"run {run_id} not found")
        return ok_result(
            "learning.run_status",
            {
                "run_id": run.run_id,
                "workflow_id": run.workflow_id,
                "trace_id": run.trace_id,
                "task": run.task,
                "status": run.status,
                "message": run.message,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
            },
        )

    def learning_status(_a: dict[str, Any]) -> dict[str, Any]:
        mgr = getattr(window, "_learning", None)
        if mgr is None:
            return err_result("learning.status", "learning manager unavailable")
        return ok_result(
            "learning.status",
            {
                "state": getattr(mgr.state, "value", str(mgr.state)),
                "session_id": mgr.session_id,
                "last_error": mgr.last_error,
            },
        )

    reg.register(
        "learning.list",
        learning_list,
        summary="List learned computer-use workflows",
        risk="low",
    )
    reg.register(
        "learning.get",
        learning_get,
        summary="Get learned workflow details",
        risk="low",
    )
    reg.register(
        "learning.run",
        learning_run,
        summary="Execute a learned workflow via Aloha Actor",
        risk="high",
        confirm_required=not policy_for(
            getattr(getattr(window, "_learning_prefs", None), "permission_level", "normal")
        ).allow_unrestricted_os_control,
    )
    reg.register(
        "learning.run_status",
        learning_run_status,
        summary="Get learned workflow run status",
        risk="low",
    )
    reg.register(
        "learning.status",
        learning_status,
        summary="Current learning recorder state",
        risk="low",
    )

    def learning_start(_a: dict[str, Any]) -> dict[str, Any]:
        mgr = getattr(window, "_learning", None)
        if mgr is None:
            return err_result("learning.start", "learning manager unavailable")
        from iris.learning.models import LearningState
        if mgr.state != LearningState.IDLE:
            return err_result("learning.start", f"cannot start: state={mgr.state.value}")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, window._start_learning_session)
        return ok_result("learning.start", {"message": "학습 세션 시작 중…"})

    def learning_stop(_a: dict[str, Any]) -> dict[str, Any]:
        mgr = getattr(window, "_learning", None)
        if mgr is None:
            return err_result("learning.stop", "learning manager unavailable")
        from iris.learning.models import LearningState
        if mgr.state != LearningState.RECORDING:
            return err_result("learning.stop", f"cannot stop: state={mgr.state.value}")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, window._stop_learning_session)
        return ok_result("learning.stop", {"message": "학습 녹화 종료 중…"})

    reg.register(
        "learning.start",
        learning_start,
        summary="Start demonstration recording session",
        risk="medium",
    )
    reg.register(
        "learning.stop",
        learning_stop,
        summary="Stop recording and process learned workflow",
        risk="medium",
    )

    # --- UI dialogs ---
    def ui_settings(_a: dict[str, Any]) -> dict[str, Any]:
        window._open_settings_dialog()
        _log(window, "ui.open_settings", True)
        return ok_result("ui.open_settings", {})

    def ui_profile(_a: dict[str, Any]) -> dict[str, Any]:
        window._open_user_profile_dialog()
        _log(window, "ui.open_user_profile", True)
        return ok_result("ui.open_user_profile", {})

    reg.register("ui.open_settings", ui_settings, summary="Open Iris settings dialog")
    reg.register(
        "ui.open_user_profile",
        ui_profile,
        summary="Open user profile dialog",
    )

    # --- settings values (direct, no dialog) ---
    def settings_get(_a: dict[str, Any]) -> dict[str, Any]:
        s = window._settings
        return ok_result(
            "settings.get",
            {
                "ollama_base_url": s.ollama_base_url,
                "ollama_model": s.ollama_model,
                "hermes_enabled": s.hermes_enabled,
                "hermes_command": s.hermes_command,
                "hermes_base_url": s.hermes_base_url,
                "hermes_api_key_set": bool(s.hermes_api_key),
            },
        )

    def settings_set(args: dict[str, Any]) -> dict[str, Any]:
        s = window._settings
        if "hermes_api_key" in args and not bool(args.get("confirm")):
            return err_result("settings.set", "confirm=true required to set hermes_api_key")
        changed: list[str] = []
        if "ollama_base_url" in args:
            s.ollama_base_url = str(args["ollama_base_url"] or "").strip() or s.ollama_base_url
            changed.append("ollama_base_url")
        if "ollama_model" in args or "model" in args:
            model = str(args.get("ollama_model") or args.get("model") or "").strip()
            if model:
                window._apply_selected_model(model, persist=True)
                changed.append("ollama_model")
        if "hermes_enabled" in args:
            s.hermes_enabled = bool(args["hermes_enabled"])
            changed.append("hermes_enabled")
        if "hermes_command" in args:
            s.hermes_command = str(args["hermes_command"] or "").strip() or s.hermes_command
            changed.append("hermes_command")
        if "hermes_base_url" in args:
            s.hermes_base_url = str(args["hermes_base_url"] or "").strip() or s.hermes_base_url
            changed.append("hermes_base_url")
        if "hermes_api_key" in args:
            s.hermes_api_key = str(args.get("hermes_api_key") or "")
            changed.append("hermes_api_key")
        window._status_header.set_model_name(s.model_name or s.ollama_model or "(unset)")
        window._refresh_hermes_health()
        _log(window, "settings.set", True)
        return ok_result("settings.set", {"changed": changed})

    reg.register("settings.get", settings_get, summary="Get Ollama/Hermes connection settings (no secret values)")
    reg.register(
        "settings.set",
        settings_set,
        summary="Set Ollama/Hermes settings; hermes_api_key needs confirm=true",
        risk="high",
        confirm_required=False,  # key path checks confirm itself
    )

    # --- email ---
    def email_list(_a: dict[str, Any]) -> dict[str, Any]:
        items = [
            {"id": a.id, "address": a.address, "label": a.label}
            for a in load_email_accounts(window._db)
        ]
        return ok_result("email.list_accounts", {"accounts": items})

    def email_set_account(args: dict[str, Any]) -> dict[str, Any]:
        account_id = str(args.get("account_id") or "").strip()
        if not account_id or find_account(window._db, account_id) is None:
            return err_result("email.set_account", "valid account_id required")
        if window._workspace_mode != "email":
            window._on_email_icon()
        window._on_email_account_changed(account_id)
        _log(window, "email.set_account", True)
        return ok_result("email.set_account", {"account_id": account_id})

    def email_select_folder(args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("folder") or args.get("name") or "받은편지함").strip()
        if window._workspace_mode != "email":
            window._on_email_icon()
        window._on_email_folder_selected(name)
        _log(window, "email.select_folder", True)
        return ok_result("email.select_folder", {"folder": name})

    def email_set_category(args: dict[str, Any]) -> dict[str, Any]:
        index = int(args.get("index") or 0)
        if window._workspace_mode != "email":
            window._on_email_icon()
        window._on_email_category(index)
        _log(window, "email.set_category", True)
        return ok_result("email.set_category", {"index": index})

    def email_refresh(_a: dict[str, Any]) -> dict[str, Any]:
        if window._workspace_mode != "email":
            window._on_email_icon()
        else:
            window._refresh_email_inbox()
        _log(window, "email.refresh_inbox", True)
        return ok_result("email.refresh_inbox", {})

    def email_open_message(args: dict[str, Any]) -> dict[str, Any]:
        uid = str(args.get("uid") or "").strip()
        if not uid:
            return err_result("email.open_message", "uid required")
        if window._workspace_mode != "email":
            window._on_email_icon()
        window._load_email_message(uid)
        _log(window, "email.open_message", True)
        return ok_result("email.open_message", {"uid": uid})

    def email_open_compose(_a: dict[str, Any]) -> dict[str, Any]:
        if window._workspace_mode != "email":
            window._on_email_icon()
        window._open_email_compose()
        _log(window, "email.open_compose", True)
        return ok_result("email.open_compose", {})

    def email_send(args: dict[str, Any]) -> dict[str, Any]:
        to = str(args.get("to") or "").strip()
        subject = str(args.get("subject") or "")
        body = str(args.get("body") or "")
        if not to:
            return err_result("email.send", "to required")
        if window._workspace_mode != "email":
            window._on_email_icon()
        window._send_email(to, subject, body)
        _log(window, "email.send", True)
        return ok_result("email.send", {"queued": True, "to": to})

    def email_add_account(args: dict[str, Any]) -> dict[str, Any]:
        address = str(args.get("address") or "").strip()
        password = str(args.get("password") or "")
        label = str(args.get("label") or "").strip()
        if not address or not password:
            return err_result("email.add_account", "address and password required")
        acc = add_email_account(window._db, address, password, label=label)
        _log(window, "email.add_account", True)
        return ok_result(
            "email.add_account",
            {"id": acc.id, "address": acc.address, "label": acc.label},
        )

    def email_remove_account(args: dict[str, Any]) -> dict[str, Any]:
        account_id = str(args.get("account_id") or "").strip()
        if not account_id:
            return err_result("email.remove_account", "account_id required")
        remove_email_account(window._db, account_id)
        if window._selected_email_account_id == account_id:
            window._selected_email_account_id = ""
        _log(window, "email.remove_account", True)
        return ok_result("email.remove_account", {"account_id": account_id})

    reg.register("email.list_accounts", email_list, summary="List email accounts (id/address/label, no passwords)")
    reg.register("email.set_account", email_set_account, summary="Select email account by id")
    reg.register(
        "email.select_folder",
        email_select_folder,
        summary="Select mailbox folder display name (받은편지함 등)",
    )
    reg.register("email.set_category", email_set_category, summary="Gmail category tab index")
    reg.register("email.refresh_inbox", email_refresh, summary="Refresh email inbox")
    reg.register("email.open_message", email_open_message, summary="Open email message by uid")
    reg.register("email.open_compose", email_open_compose, summary="Open email compose UI")
    reg.register(
        "email.send",
        email_send,
        summary="Send email (to, subject, body) — requires confirm=true",
        risk="high",
        confirm_required=True,
    )
    reg.register(
        "email.add_account",
        email_add_account,
        summary="Add email account (address, password, label) — requires confirm=true",
        risk="high",
        confirm_required=True,
    )
    reg.register(
        "email.remove_account",
        email_remove_account,
        summary="Remove email account by id — requires confirm=true",
        risk="high",
        confirm_required=True,
    )

    # --- wiki ---
    def wiki_list(_a: dict[str, Any]) -> dict[str, Any]:
        notes = [
            {"rel_path": n.rel_path, "title": n.title, "folder": n.folder, "source": n.source}
            for n in window._iris_wiki.list_notes()
        ]
        return ok_result("wiki.list_notes", {"notes": notes, "count": len(notes)})

    def wiki_open(args: dict[str, Any]) -> dict[str, Any]:
        rel = str(args.get("rel_path") or args.get("path") or "").strip()
        if not rel:
            return err_result("wiki.open_note", "rel_path required")
        window._on_obsidian_icon()
        window._obsidian_page.show_note(rel)
        window._left_sidebar.obsidian_detail.reload()
        _log(window, "wiki.open_note", True)
        return ok_result("wiki.open_note", {"rel_path": rel})

    def wiki_reload(_a: dict[str, Any]) -> dict[str, Any]:
        if window._workspace_mode != "obsidian":
            window._on_obsidian_icon()
        else:
            window._left_sidebar.obsidian_detail.reload()
            window._obsidian_page.reload_graph()
        _log(window, "wiki.reload", True)
        return ok_result("wiki.reload", {})

    reg.register("wiki.list_notes", wiki_list, summary="List Iris Wiki note paths")
    reg.register(
        "wiki.open_note",
        wiki_open,
        summary="Open Iris Wiki workspace and show note by rel_path",
    )
    reg.register("wiki.reload", wiki_reload, summary="Reload Iris Wiki graph/detail")

    # --- chat / activity / notify ---
    def chat_set_model(args: dict[str, Any]) -> dict[str, Any]:
        model = str(args.get("model") or "").strip()
        if not model:
            return err_result("chat.set_model", "model required")
        window._apply_selected_model(model, persist=True)
        combo = getattr(window._chat, "_model_combo", None)
        if combo is not None:
            for i in range(combo.count()):
                if combo.itemData(i) == model or combo.itemText(i) == model:
                    combo.blockSignals(True)
                    combo.setCurrentIndex(i)
                    combo.blockSignals(False)
                    break
        _log(window, "chat.set_model", True)
        return ok_result("chat.set_model", {"model": model})

    def chat_clear_history(_a: dict[str, Any]) -> dict[str, Any]:
        window._history.clear()
        _log(window, "chat.clear_history", True)
        return ok_result("chat.clear_history", {"history_len": 0})

    def activity_log(args: dict[str, Any]) -> dict[str, Any]:
        text = str(args.get("text") or args.get("message") or "").strip()
        if not text:
            return err_result("activity.log", "text required")
        window._live_activity.append_instant_line(text)
        return ok_result("activity.log", {})

    def notify_add(args: dict[str, Any]) -> dict[str, Any]:
        title = str(args.get("title") or "Iris").strip()
        message = str(args.get("message") or args.get("text") or "").strip()
        category = str(args.get("category") or "INFO").strip() or "INFO"
        window._notes.try_add_alert(
            target_id=0,
            category=category,
            title=title,
            message=message,
            focus_hint="",
            event_id=0,
        )
        return ok_result("notify.add_alert", {"title": title})

    reg.register(
        "chat.set_model",
        chat_set_model,
        summary="Select chat/Ollama model and sync Hermes",
        risk="medium",
    )
    reg.register(
        "chat.clear_history",
        chat_clear_history,
        summary="Clear Iris assistant chat history (not UI transcript)",
        risk="medium",
        confirm_required=True,
    )
    reg.register("activity.log", activity_log, summary="Append Live Activity line")
    reg.register("notify.add_alert", notify_add, summary="Add notification alert row")

    # catalog collision self-check at bind time
    names = [a["name"] for a in reg.catalog()]
    assert len(names) == len(set(names)), "duplicate control actions"


def _emulator_running() -> bool:
    try:
        from iris.system.android_emulator import is_emulator_running

        return bool(is_emulator_running())
    except Exception:
        return False


def _emulator_state_fields() -> dict[str, Any]:
    try:
        from iris.system.android_emulator import emulator_status

        st = emulator_status()
        return {
            "emulator_serial": st.get("serial"),
            "emulator_serials": st.get("serials") or [],
            "emulator_headless": bool(st.get("headless")),
            "emulator_avd": st.get("avd"),
            "emulator_phase": st.get("phase"),
            "emulator_adb_ready": bool(st.get("adb_ready")),
            "emulator_boot_completed": bool(st.get("boot_completed")),
            "emulator_keyboard_hint": st.get("keyboard_hint"),
        }
    except Exception:
        return {
            "emulator_serial": None,
            "emulator_serials": [],
            "emulator_headless": False,
            "emulator_avd": None,
            "emulator_phase": "stopped",
            "emulator_adb_ready": False,
            "emulator_boot_completed": False,
            "emulator_keyboard_hint": None,
        }


# typing alias for stub factory
HandlerFn = Callable[[dict[str, Any]], dict[str, Any]]
