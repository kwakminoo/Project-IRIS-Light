"""프로젝트 파일 작성·실행·다이어그램 컨트롤 액션."""

from __future__ import annotations

from iris.system.control_surface import (
    ActionRegistry,
)
from iris.ui.control_actions.hosts import ProjectHost

def project_write_file(window: ProjectHost, args: dict[str, Any]) -> dict[str, Any]:
    from iris.ui.control_bindings import Path, _bound_session, _bridge_call_pumping, _log, _qt_pump, err_result, load_user_profile, ok_result
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
    if session is not None and session.ide_id == "iris_ide":
        try:
            client = window._iris_ide_bridge_client()
            _root, abs_path, norm_rel = resolve_under_root(root, rel)
            text = str(content)
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
                _log(window, "project.write_file", True)
                return ok_result("project.write_file", written)
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            end = max(len(text) + 1, 999999)
            if abs_path.is_file():
                _bridge_call_pumping(lambda: client.open_file(norm_rel))
                _bridge_call_pumping(lambda: client.replace_range(text, path=norm_rel, start=0, end=end))
            else:
                _bridge_call_pumping(lambda: client.create_file(norm_rel, text))
                _bridge_call_pumping(lambda: client.open_file(norm_rel))
            written = {
                "path": path_s,
                "rel_path": norm_rel,
                "bytes": len(text.encode("utf-8")),
                "opened": True,
                "visible": True,
                "typed": False,
                "streamed": False,
                "via": "iris_ide_bridge",
            }
            _log(window, "project.write_file", True)
            return ok_result("project.write_file", written)
        except Exception as exc:  # noqa: BLE001
            return err_result("project.write_file", str(exc))
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

def project_run(window: ProjectHost, args: dict[str, Any]) -> dict[str, Any]:
    from iris.ui.control_bindings import Path, _append_activity, _bound_session, _bridge_call_pumping, _log, _qt_pump, err_result, load_user_profile, ok_result
    import time

    from iris.automation.ide_input import run_command_in_ide_terminal, trigger_default_build_task
    from iris.system.project_ops import (
        build_iris_terminal_command,
        build_run_command,
        infer_dev_server_url,
        iris_run_log_path,
        is_static_web_file,
        open_preview_in_browser,
        result_from_terminal_log,
        static_web_file_uri,
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

    file_arg = str(args.get("file") or args.get("rel_path") or "").strip()
    open_browser = bool(args.get("open_browser", True))
    # 정적 HTML/HTM → 기본 브라우저로 미리보기 (IDE 터미널 불필요)
    if not args.get("command") and is_static_web_file(file_arg):
        try:
            uri = static_web_file_uri(root_s, file_arg)
        except Exception as exc:  # noqa: BLE001
            return err_result("project.run", str(exc))
        opened = open_preview_in_browser(uri) if open_browser else False
        if open_browser and not opened:
            return err_result("project.run", f"failed to open browser preview: {uri}")
        payload = {
            "ok": True,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "elapsed_sec": 0.0,
            "argv": ["browser", uri],
            "cwd": root_s,
            "timed_out": False,
            "via": "browser",
            "preview_url": uri,
            "browser": "ok" if opened else "skipped",
            "summary": f"opened in browser · {Path(file_arg).name}",
            "ide_terminal": "skipped",
        }
        _append_activity(window, f"미리보기: {uri}")
        return ok_result("project.run", payload)

    timeout_sec = float(args.get("timeout_sec") or 60)
    try:
        argv = build_run_command(
            command=args.get("command"),
            file=file_arg,
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
    t0 = time.monotonic()
    if session.ide_id == "iris_ide":
        try:
            client = window._iris_ide_bridge_client()
            # 브리지는 Theia 통합 터미널 완료를 15s까지 기다린다 — UI 스레드를 막으면
            # 프런트엔드 폴러가 그 사이 fetch를 못 해 반드시 타임아웃(400)으로 끝난다.
            term = _bridge_call_pumping(
                lambda: client.run_terminal_command(shell_cmd, cwd=root_s, argv=argv),
                timeout=18.0,
            )
            via = str(term.get("via") or "iris_ide_bridge")
            queued = bool(term.get("queued"))
            if via == "bridge_fallback":
                return err_result(
                    "project.run",
                    "IDE integrated terminal unavailable (bridge ran command outside Theia — blocked)",
                    {"via": via, "command": shell_cmd},
                )
            if not queued and via != "theia_terminal":
                return err_result(
                    "project.run",
                    "IDE integrated terminal did not accept command",
                    {"via": via, "delivered": False, "executed": False, "command": shell_cmd},
                )
            shell_used = str(term.get("shell") or "")
            waited = wait_for_run_log(
                log_p,
                timeout_sec=min(timeout_sec, 12.0),
                stable_sec=0.8,
                pump=_qt_pump,
            )
            elapsed = time.monotonic() - t0
            if not waited.get("found"):
                return err_result(
                    "project.run",
                    "command was delivered but no run log or exit code was confirmed",
                    {
                        "delivered": True,
                        "executed": False,
                        "exit_code": None,
                        "via": via,
                        "shell": shell_used,
                        "log_path": str(log_p),
                        "command": shell_cmd,
                    },
                )
            result = result_from_terminal_log(
                str(waited.get("text") or ""),
                argv=argv,
                cwd=root_s,
                elapsed_sec=elapsed,
            )
            if not result.get("confirmed"):
                return err_result(
                    "project.run",
                    "command was delivered but the program exit code was not in the run log",
                    {
                        "delivered": True,
                        "executed": False,
                        "exit_code": None,
                        "via": via,
                        "shell": shell_used,
                        "log_path": str(log_p),
                        "stdout": result.get("stdout") or "",
                    },
                )
            payload = {
                **result,
                **summarize_run(result),
                "delivered": True,
                "executed": True,
                "via": via,
                "shell": shell_used,
                "ide_terminal": "ok",
                "log_path": str(log_p),
                "stdout_len": len(result.get("stdout") or ""),
            }
            payload.pop("stdout", None)
            payload.pop("stderr", None)
            ok = result.get("exit_code") == 0 and not result.get("timed_out")
            _log(window, "project.run", ok)
            if ok:
                return ok_result("project.run", payload)
            return err_result(
                "project.run",
                payload.get("summary") or f"exit {result.get('exit_code')}",
                payload,
            )
        except Exception as exc:  # noqa: BLE001
            return err_result("project.run", str(exc))
    hwnd = int(session.hwnd) if session and session.hwnd else None
    pid = session.pid if session else None

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
    if not result.get("confirmed"):
        return err_result(
            "project.run",
            "command was delivered but the program exit code was not in the run log",
            {
                "delivered": True,
                "executed": False,
                "exit_code": None,
                "log_path": str(log_p),
            },
        )
    ide_terminal = "ok"

    preview_url = ""
    browser_status = "skipped"
    if open_browser:
        preview_url = str(args.get("preview_url") or "").strip() or (
            infer_dev_server_url(argv) or ""
        )
        if preview_url:
            # 서버 기동 직후 짧게 대기 후 브라우저
            time.sleep(1.2)
            browser_status = "ok" if open_preview_in_browser(preview_url) else "failed"
            if browser_status == "ok":
                _append_activity(window, f"미리보기: {preview_url}")

    summary_bits = summarize_run(result)
    if ide_terminal == "ok":
        summary_bits["summary"] += " · output in IDE terminal"
    if browser_status == "ok" and preview_url:
        summary_bits["summary"] += f" · browser {preview_url}"

    payload = {
        **result,
        **summary_bits,
        "ide_terminal": ide_terminal,
        "log_path": str(log_p) if log_p.is_file() else None,
        "preview_url": preview_url or None,
        "browser": browser_status,
        "tasks_path": tasks_path or None,
        "opened_log": False,
        "stdout_len": len(result.get("stdout") or ""),
        "stderr_len": len(result.get("stderr") or ""),
    }
    payload.pop("stdout", None)
    payload.pop("stderr", None)
    ok = result.get("exit_code") == 0 and not result.get("timed_out")
    _log(window, "project.run", ok)
    return ok_result("project.run", payload) if ok else err_result(
        "project.run",
        summary_bits.get("summary") or f"exit {result.get('exit_code')}",
        payload,
    )

def register_project_actions(window: ProjectHost, reg: ActionRegistry) -> None:
    from iris.ui.control_bindings import (
        Path,
        _append_activity,
        _bound_session,
        _bridge_call_pumping,
        _first_class_ide_trigger,
        _ide_open_file_path,
        _log,
        _profile_parents,
        _qt_pump,
        err_result,
        load_user_profile,
        ok_result,
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
        new_window = bool(args.get("new_window", True))
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
                new_window=bool(args.get("new_window", True)),
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

    def project_list_files(args: dict[str, Any]) -> dict[str, Any]:
        from iris.system.project_ops import list_workspace_files

        root = str(args.get("project_root") or args.get("root") or "").strip()
        if not root:
            session = window._get_bound_ide_session(refresh=False)
            root = (session.workspace_root if session is not None else "") or (
                load_user_profile(window._db).project_root or ""
            )
        if not root:
            return err_result("project.list_files", "project_root required (no bound IDE workspace)")
        try:
            listed = list_workspace_files(
                root,
                query=str(args.get("query") or args.get("name") or ""),
                limit=int(args.get("limit") or 200),
            )
        except (NotADirectoryError, OSError, ValueError) as exc:
            return err_result("project.list_files", str(exc))
        _log(window, "project.list_files", True)
        return ok_result("project.list_files", listed)

    def diagram_render(args: dict[str, Any]) -> dict[str, Any]:
        import json

        from iris.system.archify_render import render_diagram
        from iris.ui.window.diagram_preview import open_diagram_preview

        kind = str(args.get("kind") or "").strip().lower()
        ir = args.get("ir")
        if isinstance(ir, str):
            try:
                ir = json.loads(ir)
            except json.JSONDecodeError as exc:
                return err_result("diagram.render", f"ir is not valid JSON: {exc}")
        title = str(args.get("title") or "")
        # ponytail: node 서브프로세스를 UI 스레드에서 기다리지 않는다 (연번 17과 동일 사유).
        rendered = _bridge_call_pumping(
            lambda: render_diagram(kind, ir if isinstance(ir, dict) else {}, title=title),
            timeout=150.0,
        )
        if not rendered.get("ok"):
            _log(window, "diagram.render", False)
            return err_result(
                "diagram.render",
                str(rendered.get("error") or "render failed"),
                {"diagnostics": rendered.get("diagnostics") or [], "stage": rendered.get("stage")},
            )
        rendered["opened"] = open_diagram_preview(window, str(rendered["html_path"]))
        _log(window, "diagram.render", True)
        return ok_result("diagram.render", rendered)

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
        "project.list_files",
        project_list_files,
        summary="List files in the bound IDE workspace (query = case-insensitive substring) — use this before open_file/run when the path is unknown",
    )

    reg.register(
        "project.write_file",
        _first_class_ide_trigger(window, lambda args: project_write_file(window, args)),
        summary="Write file under the bound IDE workspace; open=true reveals tab then streams chunks",
        risk="medium",
    )

    reg.register(
        "diagram.render",
        diagram_render,
        summary=(
            "Render a typed JSON IR into an interactive diagram and show it "
            "(kind = architecture|workflow|sequence|dataflow|lifecycle). "
            "Read integrations/archify/schemas/<kind>.schema.json for the IR shape "
            "(architecture needs explicit placement: layout {mode:\"grid\",cols:n} with 0-based "
            "row/col per component, or pos/size per component); "
            "on failure the error data carries archify diagnostics[] — fix the IR and retry"
        ),
    )

    reg.register(
        "project.run",
        lambda args: project_run(window, args),
        summary="Run only in the bound IDE integrated terminal via Iris: Run task",
        risk="medium",
    )
