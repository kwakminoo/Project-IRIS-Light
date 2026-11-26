"""프로젝트 파일 작성·실행·다이어그램 컨트롤 액션."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QApplication

from iris.system.control_surface import (
    ActionRegistry,
)
from iris.ui.control_actions.hosts import ProjectHost


def _on_qt_ui_thread() -> bool:
    app = QApplication.instance()
    return app is not None and QThread.currentThread() == app.thread()


def project_write_file(window: ProjectHost, args: dict[str, Any]) -> dict[str, Any]:
    from iris.ui.control_bindings import (
        Path,
        _bound_session,
        _bridge_call_pumping,
        _log,
        _qt_pump,
        ensure_iris_ide_workspace,
        err_result,
        iris_ide_editor_opened,
        iris_ide_save_ok,
        load_user_profile,
        ok_result,
        resolve_bound_work_root,
    )
    from iris.automation.ide_input import (
        open_file_in_workspace,
        typewriter_into_ide,
        wait_ide_shows_file,
    )
    from iris.system.ide_launcher import open_file_in_ide
    from iris.system.project_ops import (
        resolve_under_root,
        utf8_content_matches,
        write_project_file,
        write_project_file_stream,
    )

    root, root_err = resolve_bound_work_root(window, args)
    if root_err:
        return err_result("project.write_file", root_err)
    rel = str(args.get("rel_path") or args.get("path") or "").strip()
    if Path(rel).suffix.lower() == ".pdf":
        return err_result(
            "project.write_file",
            "PDF는 note.export_pdf 로만 만든다. 문자열로 .pdf 를 쓰지 않는다.",
        )
    content = args.get("content")
    if content is None:
        return err_result("project.write_file", "content required")
    if not root or not rel:
        return err_result("project.write_file", "project_root and rel_path required")

    def _logged(payload: dict) -> dict:
        try:
            from iris.knowledge.ide_project_log import note_file_written

            note_file_written(window, root, rel)
        except Exception:
            pass
        return ok_result("project.write_file", payload)

    do_open = bool(args.get("open", True))
    # Companion/IDE 코드 파일은 탭이 열려야 한다. open=false 로 디스크만 쓰는 우회 금지.
    _code_ext = {
        ".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".json", ".css", ".html",
        ".htm", ".md", ".rs", ".go", ".java", ".kt", ".cs", ".cpp", ".c", ".h", ".hpp",
        ".vue", ".svelte", ".toml", ".yaml", ".yml", ".sh", ".bat", ".ps1",
    }
    if Path(rel).suffix.lower() in _code_ext:
        do_open = True
    session, session_err = _bound_session(window, require_workspace=do_open)
    if do_open and session_err:
        return err_result("project.write_file", session_err)
    if session is not None:
        align_err = ensure_iris_ide_workspace(window, root, action="project.write_file")
        if align_err is not None:
            return align_err
        session, session_err = _bound_session(window, require_workspace=do_open)
        if do_open and session_err:
            return err_result("project.write_file", session_err)
    if session is not None and session.ide_id == "iris_ide":
        # Policy A: open/tab fail = err, but on_disk/content_match stay honest so
        # Verify/CHAT_ONLY do not treat disk-ok as "file never created".
        def _open_fail_payload(
            path_s: str,
            norm_rel: str,
            text: str,
            open_err: str,
            open_out: object = None,
        ) -> dict:
            on_disk = Path(path_s).is_file()
            match = utf8_content_matches(Path(path_s), text) if on_disk else False
            return err_result(
                "project.write_file",
                open_err,
                {
                    "path": path_s,
                    "rel_path": norm_rel,
                    "on_disk": on_disk,
                    "content_match": match,
                    "opened": False,
                    "visible": False,
                    "via": (open_out or {}).get("via") if isinstance(open_out, dict) else None,
                    "bridge": open_out,
                },
            )

        def _open_tab(client: object, norm_rel: str) -> tuple[object | None, str]:
            try:
                open_out = _bridge_call_pumping(lambda: client.open_file(norm_rel))
            except Exception as open_exc:  # noqa: BLE001
                return None, str(open_exc)
            visible, open_err = iris_ide_editor_opened(open_out)
            if not visible:
                return open_out, open_err or "IDE editor did not open"
            return open_out, ""

        try:
            client = window._iris_ide_bridge_client()
            _root, abs_path, norm_rel = resolve_under_root(root, rel)
            text = str(content)
            path_s = str(abs_path)
            if not do_open:
                written = write_project_file(root, rel, text)
                if written.get("content_match") is False:
                    return err_result(
                        "project.write_file",
                        str(written.get("error") or "UTF-8 content readback mismatch"),
                        written,
                    )
                written["opened"] = False
                written["visible"] = False
                written["on_disk"] = True
                _log(window, "project.write_file", True)
                return _logged(written)
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            if abs_path.is_file():
                open_out, open_err = _open_tab(client, norm_rel)
                if open_err:
                    return _open_fail_payload(path_s, norm_rel, text, open_err, open_out)
                saved = _bridge_call_pumping(lambda: client.write_file(norm_rel, text))
                saved_ok, save_err = iris_ide_save_ok(saved)
                if not saved_ok:
                    return _open_fail_payload(path_s, norm_rel, text, save_err, open_out)
            else:
                _bridge_call_pumping(lambda: client.create_file(norm_rel, text))
                open_out, open_err = _open_tab(client, norm_rel)
                if open_err:
                    return _open_fail_payload(path_s, norm_rel, text, open_err, open_out)
            match = utf8_content_matches(abs_path, text)
            written = {
                "path": path_s,
                "rel_path": norm_rel,
                "bytes": len(text.encode("utf-8")),
                "on_disk": True,
                "content_match": match,
                "opened": True,
                "visible": True,
                "typed": False,
                "streamed": False,
                "via": "iris_ide_bridge",
            }
            if match is False:
                return err_result(
                    "project.write_file",
                    "UTF-8 content readback mismatch",
                    written,
                )
            _log(window, "project.write_file", True)
            return _logged(written)
        except Exception as exc:  # noqa: BLE001
            # create succeeded but a later step raised: still report disk if present.
            try:
                _root, abs_path, norm_rel = resolve_under_root(root, rel)
                path_s = str(abs_path)
                text = str(content)
                if abs_path.is_file():
                    return _open_fail_payload(path_s, norm_rel, text, str(exc), None)
            except Exception:  # noqa: BLE001
                pass
            return err_result("project.write_file", str(exc))
    # open=true 이면 기본 live file stream. 명시 stream/typewriter=false 만 즉시 쓰기.
    # HTTP 워커(OFF_UI)에서는 Qt pump/타이프라이터 금지 — 즉시 디스크 쓰기.
    if "typewriter" in args:
        do_type = bool(args.get("typewriter"))
    elif "stream" in args:
        do_type = bool(args.get("stream"))
    else:
        do_type = do_open
    if not _on_qt_ui_thread():
        do_type = False
    text = str(content)
    try:
        _root, abs_path, norm_rel = resolve_under_root(root, rel)
        path_s = str(abs_path)
        if not do_open:
            written = write_project_file(root, rel, text)
            if written.get("content_match") is False:
                return err_result(
                    "project.write_file",
                    str(written.get("error") or "UTF-8 content readback mismatch"),
                    written,
                )
            written["opened"] = False
            written["typed"] = False
            written["visible"] = False
            _log(window, "project.write_file", True)
            return _logged(written)

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
        disk_write: dict[str, Any] = {}
        if do_type and hwnd and opened and input_mode == "keyboard":
            typed = typewriter_into_ide(
                hwnd,
                text,
                delay_ms=int(args["delay_ms"]) if args.get("delay_ms") is not None else None,
                pump=_qt_pump,
                pid=pid,
            )
            disk_write = write_project_file(root, norm_rel, text)
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
            disk_write = stream_result
            streamed = True
        elif do_type:
            return err_result(
                "project.write_file",
                "bound IDE session could not open file for live write",
                {"path": path_s, "opened": bool(opened), "visible": bool(visible)},
            )
        else:
            disk_write = write_project_file(root, norm_rel, text)
            if not (hwnd and opened):
                return err_result(
                    "project.write_file",
                    "bound IDE session could not open file",
                    {"path": path_s, "opened": bool(opened), "visible": bool(visible)},
                )
        if disk_write.get("content_match") is False:
            return err_result(
                "project.write_file",
                str(disk_write.get("error") or "UTF-8 content readback mismatch"),
                {
                    **disk_write,
                    "opened": bool(opened),
                    "visible": bool(visible),
                },
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
            "content_match": disk_write.get("content_match"),
            "input_mode": "keyboard" if typed else ("file_watch" if streamed else "instant"),
            "chunks": int(stream_result.get("chunks") or 0),
            "chunk_chars": int(stream_result.get("chunk_chars") or 0),
            "chunk_delay_ms": int(stream_result.get("chunk_delay_ms") or 0),
        }
    except Exception as exc:  # noqa: BLE001
        return err_result("project.write_file", str(exc))
    _log(window, "project.write_file", True)
    return _logged(written)

def project_run(window: ProjectHost, args: dict[str, Any]) -> dict[str, Any]:
    from iris.ui.control_bindings import (
        Path,
        _append_activity,
        _bound_session,
        _bridge_call_pumping,
        _log,
        _qt_pump,
        ensure_iris_ide_workspace,
        err_result,
        ok_result,
        resolve_bound_work_root,
        trusted_execution_context,
    )
    import time

    from iris.system.execution_runtime import default_runtime
    from iris.system.project_ops import (
        bind_python_argv,
        infer_dev_server_url,
        iris_run_log_path,
        is_static_web_file,
        open_preview_in_browser,
        plan_run,
        result_from_runtime_record,
        start_managed_run,
        static_web_file_uri,
        summarize_run,
        wait_managed_run,
    )
    from iris.system.terminal_output_mirror import advance_output_cursor, format_run_banner

    root, root_err = resolve_bound_work_root(window, args)
    if root_err:
        return err_result("project.run", root_err)
    root_p = Path(root).expanduser()
    if not root_p.is_dir():
        return err_result("project.run", f"not a directory: {root}")
    root_s = str(root_p.resolve())
    reveal = bool(args.get("reveal_terminal", True))
    session, session_err = _bound_session(window, require_workspace=True)
    if session_err:
        return err_result("project.run", session_err)
    align_err = ensure_iris_ide_workspace(window, root_s, action="project.run")
    if align_err is not None:
        return align_err
    session, session_err = _bound_session(window, require_workspace=True)
    if session_err:
        return err_result("project.run", session_err)

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
        plan = plan_run(
            command=args.get("command"),
            file=file_arg,
            project_root=root_p,
        )
        if plan.shell_command is not None:
            # Cursor-style: 문자열 명령을 셸에 그대로 (shlex/bind_python 금지).
            argv = [plan.shell_command]
            start_kwargs: dict[str, Any] = {"shell": plan.shell_command}
        else:
            argv = bind_python_argv(
                list(plan.argv or []),
                root_p,
                allow_create=False,
                file=file_arg or None,
            )
            start_kwargs = {"argv": argv}
    except Exception as exc:  # noqa: BLE001
        return err_result("project.run", str(exc))

    # Trusted Control context — prefer turn-frozen; never model session/workspace args.
    ctx = trusted_execution_context(window)
    session_id = str(ctx.effective_session_id() or "")
    workspace_id = str(ctx.workspace_id or ctx.workspace_root or root_s)
    from iris.ui.chat.shell_controller import (
        bind_block,
        bind_run,
        get_by_request,
        new_request,
        set_status,
    )
    from iris.ui.chat.shell_gate import take_shell_confirm_block

    cmd_preview = (
        start_kwargs.get("shell")
        if start_kwargs.get("shell")
        else " ".join(str(a) for a in argv)
    )
    # HF-05: request_id↔block_id from confirm stash (not FIFO pop(0)).
    prior_rid = str(args.pop("_iris_shell_request_id", "") or "").strip()
    block_id = take_shell_confirm_block(
        getattr(window, "_chat", None),
        command=str(cmd_preview or ""),
        request_id=prior_rid,
    )
    existing = get_by_request(prior_rid) if prior_rid else None
    if existing is not None:
        req = existing
        req.session_id = session_id or req.session_id
        req.workspace_id = workspace_id or req.workspace_id
        req.command = str(cmd_preview or "") or req.command
        if block_id:
            bind_block(req.request_id, block_id)
    else:
        req = new_request(
            session_id=session_id,
            workspace_id=workspace_id,
            command=str(cmd_preview or ""),
            block_id=block_id,
        )
        if block_id:
            bind_block(req.request_id, block_id)
    set_status(req.request_id, "approved")

    t0 = time.monotonic()
    try:
        run_id = start_managed_run(
            cwd=root_s,
            timeout_s=timeout_sec,
            session_id=session_id,
            workspace_id=workspace_id,
            owner="project.run",  # telemetry label only; ACL uses session_id
            **start_kwargs,
        )
    except Exception as exc:  # noqa: BLE001
        set_status(req.request_id, "failed")
        return err_result("project.run", str(exc))
    bind_run(req.request_id, run_id)

    # IDE mirror only — Runtime owns the process; Theia never re-executes the command.
    ide_terminal = "skipped"
    via = "execution_runtime"
    revealed = False
    shell_used = ""
    ide_client = None
    mirror_stop = False
    out_off = 0
    err_off = 0
    rt = default_runtime()

    def _append_mirror(text: str, *, stream: str = "") -> None:
        nonlocal ide_terminal, revealed, mirror_stop, ide_client, via
        if mirror_stop or ide_client is None or not text:
            return
        try:
            term = _bridge_call_pumping(
                lambda: ide_client.append_terminal_output(
                    text, cwd=root_s, run_id=run_id, stream=stream
                ),
                timeout=8.0,
            )
            via_m = str(term.get("via") or "theia_terminal")
            if via_m == "bridge_fallback" or term.get("appended") is False:
                if ide_terminal != "ok":
                    ide_terminal = "failed"
                mirror_stop = True
                ide_client = None
                return
            ide_terminal = "ok"
            revealed = bool(term.get("revealed", True))
            via = "theia_terminal"
        except Exception:  # noqa: BLE001 — bridge fail ≠ process fail
            if ide_terminal != "ok":
                ide_terminal = "failed"
            mirror_stop = True
            ide_client = None

    def _flush_stream(stream: str) -> None:
        nonlocal out_off, err_off
        if mirror_stop or ide_client is None:
            return
        off = out_off if stream == "stdout" else err_off
        data = rt.read_output(run_id, stream=stream, offset=off)
        text, nxt = advance_output_cursor(data, offset=off)
        if not text:
            return
        _append_mirror(text, stream=stream)
        if mirror_stop:
            return
        if stream == "stdout":
            out_off = nxt
        else:
            err_off = nxt

    def _mirror_pump() -> None:
        _qt_pump()
        if mirror_stop or ide_client is None:
            return
        _flush_stream("stdout")
        _flush_stream("stderr")

    if reveal and session is not None and session.ide_id == "iris_ide":
        try:
            ide_client = window._iris_ide_bridge_client()
            _append_mirror(format_run_banner(run_id), stream="banner")
        except Exception:  # noqa: BLE001 — bridge fail ≠ process fail
            ide_terminal = "failed"
            ide_client = None
            mirror_stop = True
    # Non-Theia IDE: no echo-only viz (User direct terminal unchanged; Iris mirrors Theia only).

    rec = wait_managed_run(
        run_id,
        timeout_s=timeout_sec,
        pump=_mirror_pump if ide_client is not None else _qt_pump,
    )
    if ide_client is not None and not mirror_stop:
        _flush_stream("stdout")
        _flush_stream("stderr")
    elapsed = time.monotonic() - t0
    stdout_text = str(
        (rt.read_output(run_id, stream="stdout").get("text") or "")
    )
    stderr_text = str(
        (rt.read_output(run_id, stream="stderr").get("text") or "")
    )
    result = result_from_runtime_record(
        rec,
        argv=argv,
        cwd=root_s,
        elapsed_sec=elapsed,
        stdout=stdout_text,
        stderr=stderr_text,
        via=via,
    )
    result["request_id"] = req.request_id
    if not result.get("confirmed") and not result.get("timed_out"):
        set_status(req.request_id, "failed")
        return err_result(
            "project.run",
            "run started but Runtime did not confirm an exit code",
            {
                "delivered": True,
                "executed": False,
                "run_id": run_id,
                "request_id": req.request_id,
                "status": result.get("status"),
                "exit_code": None,
                "via": via,
                "stdout_ref": result.get("stdout_ref"),
                "stderr_ref": result.get("stderr_ref"),
            },
        )

    preview_url = ""
    browser_status = "skipped"
    if open_browser:
        preview_url = str(args.get("preview_url") or "").strip() or (
            infer_dev_server_url(argv) or ""
        )
        if preview_url:
            time.sleep(1.2)
            browser_status = "ok" if open_preview_in_browser(preview_url) else "failed"
            if browser_status == "ok":
                _append_activity(window, f"미리보기: {preview_url}")

    summary_bits = summarize_run(result)
    if ide_terminal == "ok":
        summary_bits["summary"] += " · IDE terminal revealed"
    if browser_status == "ok" and preview_url:
        summary_bits["summary"] += f" · browser {preview_url}"

    log_p = iris_run_log_path(root_s)
    payload = {
        **result,
        **summary_bits,
        "delivered": True,
        "executed": True,
        "run_id": run_id,
        "request_id": req.request_id,
        "ide_terminal": ide_terminal,
        "revealed": revealed,
        "shell": shell_used or None,
        "log_path": str(log_p) if log_p.is_file() else None,
        "preview_url": preview_url or None,
        "browser": browser_status,
        "stdout_len": len(stdout_text),
        "stderr_len": len(stderr_text),
    }
    payload.pop("stdout", None)
    payload.pop("stderr", None)
    # Process status ≠ task success (W11-G): prefer helper ok.
    ok = bool(result.get("ok")) if "ok" in result else (
        result.get("exit_code") == 0 and not result.get("timed_out")
    )
    if result.get("timed_out"):
        set_status(req.request_id, "timed_out")
    elif str(result.get("status") or "") in ("cancelled", "interrupted"):
        set_status(req.request_id, str(result.get("status")))
    else:
        set_status(req.request_id, "completed" if ok else "failed")
    _log(window, "project.run", ok)
    if ok:
        return ok_result("project.run", payload)
    return err_result(
        "project.run",
        summary_bits.get("summary") or f"exit {result.get('exit_code')}",
        payload,
    )

def _paths_overlap(a: Path, b: Path) -> bool:
    try:
        ar = a.expanduser().resolve()
        br = b.expanduser().resolve()
    except OSError:
        return False
    if ar == br:
        return True
    try:
        br.relative_to(ar)
        return True
    except ValueError:
        pass
    try:
        ar.relative_to(br)
        return True
    except ValueError:
        return False


def _release_ide_for_delete(window: ProjectHost, target: Path) -> dict[str, Any]:
    """삭제 대상이 bound workspace와 겹치면 Companion/세션을 풀어 잠금을 푼다 (best-effort)."""
    from iris.ui.control_bindings import (
        _bound_session,
        _call_on_ui,
        _call_on_ui_unbounded,
    )

    info: dict[str, Any] = {"released": False}
    session, _err = _bound_session(window, require_workspace=False)
    if session is None:
        info["reason"] = "no session"
        return info
    ws = str(getattr(session, "workspace_root", "") or "").strip()
    if not ws:
        info["reason"] = "no workspace"
        return info
    try:
        ws_path = Path(ws).expanduser().resolve()
    except OSError:
        info["reason"] = "bad workspace"
        return info
    if not _paths_overlap(ws_path, target):
        info["reason"] = "workspace not overlapping"
        return info
    # 워크스페이스 루트·조상·자식을 지울 때는 창을 닫아 핸들을 푼다.
    # 불완전할 수 있음: Iris가 소유하지 않은 Cursor HWND는 남을 수 있다.
    exit_fn = getattr(window, "_exit_ide_companion", None)
    if callable(exit_fn):
        try:
            _call_on_ui_unbounded(window, exit_fn)
            info["released"] = True
            info["via"] = "exit_companion"
            return info
        except Exception as exc:  # noqa: BLE001
            info["exit_error"] = str(exc)
    clear_fn = getattr(window, "_clear_ide_session", None)
    if callable(clear_fn):
        try:
            _call_on_ui(window, lambda: clear_fn("project.delete"))
            info["released"] = True
            info["via"] = "clear_session"
        except Exception as exc:  # noqa: BLE001
            info["clear_error"] = str(exc)
    if not info.get("released"):
        info["note"] = (
            "best-effort unlock incomplete; Windows may still report "
            "Device or resource busy"
        )
    return info


def project_delete(window: ProjectHost, args: dict[str, Any]) -> dict[str, Any]:
    """프로젝트 폴더·파일 삭제. 터미널 rm 대신 이 경로를 쓴다."""
    from iris.system.project_ops import (
        delete_project_path,
        resolve_delete_target,
    )
    from iris.ui.control_bindings import (
        _bound_session,
        _call_on_ui,
        _log,
        _profile_parents,
        err_result,
        ok_result,
        resolve_bound_work_root,
    )

    rel = str(args.get("rel_path") or args.get("file") or "").strip()
    explicit = str(args.get("project_root") or args.get("root") or "").strip()
    if explicit:
        root, root_err = explicit, ""
    else:
        root, root_err = resolve_bound_work_root(window, args)
    if root_err or not root:
        return err_result(
            "project.delete",
            root_err or "project_root required (or bound IDE workspace)",
        )
    parents = _profile_parents(window)
    try:
        target, _rel_n, kind = resolve_delete_target(
            root, rel, parents=parents
        )
    except (FileNotFoundError, NotADirectoryError, OSError, ValueError) as exc:
        return err_result("project.delete", str(exc))
    release = _release_ide_for_delete(window, target)
    # 단일 파일이고 IRIS IDE 가 열려 있으면 브리지 delete 를 먼저 시도 (rename 과 동일).
    session, _session_err = _bound_session(window, require_workspace=False)
    if (
        kind == "file"
        and session is not None
        and getattr(session, "ide_id", "") == "iris_ide"
        and not release.get("released")
    ):
        try:
            client = _call_on_ui(window, window._iris_ide_bridge_client)
            if client is not None and rel:
                client.delete_file(rel.replace("\\", "/").lstrip("/"))
        except Exception:
            pass
    try:
        result = delete_project_path(root, rel, parents=parents)
    except (FileNotFoundError, NotADirectoryError, OSError, ValueError) as exc:
        return err_result(
            "project.delete",
            str(exc),
            {"release": release, "path": str(target)},
        )
    result["release"] = release
    _log(window, "project.delete", True)
    return ok_result("project.delete", result)


def project_rename_file(window: ProjectHost, args: dict[str, Any]) -> dict[str, Any]:
    """호출자가 넘긴 두 경로만 바꾼다. 문장에서 이름을 고르지 않는다."""
    from iris.system.project_ops import rename_project_file, resolve_under_root
    from iris.ui.control_bindings import (
        _bound_session,
        _log,
        err_result,
        ok_result,
        resolve_bound_work_root,
    )

    root, root_err = resolve_bound_work_root(window, args)
    if root_err:
        return err_result("project.rename_file", root_err)
    src = str(args.get("path") or args.get("from") or args.get("src") or "").strip()
    dest = str(args.get("new_path") or args.get("to") or args.get("dest") or "").strip()
    if not root or not src or not dest:
        return err_result("project.rename_file", "project_root, path, and new_path required")
    try:
        _root, src_path, src_rel = resolve_under_root(root, src)
        _root, dest_path, dest_rel = resolve_under_root(root, dest)
    except (OSError, ValueError) as exc:
        return err_result("project.rename_file", str(exc))
    if src_rel == dest_rel:
        return ok_result(
            "project.rename_file",
            {"path": str(src_path), "rel_path": src_rel, "from": src_rel},
        )
    if not src_path.is_file():
        return err_result("project.rename_file", "source file missing", {"path": src_rel})
    if dest_path.exists():
        return err_result("project.rename_file", "destination exists", {"new_path": dest_rel})
    session, _session_err = _bound_session(window, require_workspace=False)
    if session is not None and session.ide_id == "iris_ide" and not dest_path.exists():
        try:
            client = window._iris_ide_bridge_client()
            client.rename_file(src_rel, dest_rel)
        except Exception:
            pass
    if not dest_path.is_file():
        try:
            moved = rename_project_file(root, src_rel, dest_rel)
        except (OSError, ValueError) as exc:
            return err_result("project.rename_file", str(exc))
        if not moved:
            return err_result(
                "project.rename_file",
                "rename failed",
                {"path": src_rel, "new_path": dest_rel},
            )
        _root, dest_path, dest_rel = resolve_under_root(root, moved)
    _log(window, "project.rename_file", True)
    return ok_result(
        "project.rename_file",
        {"path": str(dest_path), "rel_path": dest_rel, "from": src_rel},
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
        _with_run_visibility,
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
        from iris.ui.control_bindings import resolve_bound_work_root

        root, root_err = resolve_bound_work_root(window, args)
        if root_err or not root:
            return err_result(
                "project.list_files",
                root_err or "project_root required (no bound IDE workspace)",
            )
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

    def project_read_file(args: dict[str, Any]) -> dict[str, Any]:
        from iris.system.project_ops import read_project_file
        from iris.ui.control_bindings import resolve_bound_work_root

        root, root_err = resolve_bound_work_root(window, args)
        if root_err or not root:
            return err_result(
                "project.read_file",
                root_err or "project_root required (no bound IDE workspace)",
            )
        rel = str(args.get("rel_path") or args.get("path") or "").strip()
        if not rel:
            return err_result("project.read_file", "rel_path required")
        start = args.get("start_line")
        end = args.get("end_line")
        try:
            payload = read_project_file(
                root,
                rel,
                max_bytes=int(args.get("max_bytes") or 1_048_576),
                start_line=int(start) if start is not None else None,
                end_line=int(end) if end is not None else None,
            )
        except (
            FileNotFoundError,
            IsADirectoryError,
            NotADirectoryError,
            OSError,
            ValueError,
        ) as exc:
            return err_result("project.read_file", str(exc))
        _log(window, "project.read_file", True)
        return ok_result("project.read_file", payload)

    def project_apply_patch(args: dict[str, Any]) -> dict[str, Any]:
        from iris.system.file_patch import apply_patch
        from iris.ui.control_bindings import resolve_bound_work_root

        root, root_err = resolve_bound_work_root(window, args)
        if root_err or not root:
            return err_result(
                "project.apply_patch",
                root_err or "project_root required (no bound IDE workspace)",
            )
        patch_text = str(args.get("patch_text") or args.get("patch") or "")
        if not patch_text.strip():
            return err_result("project.apply_patch", "patch_text required")
        expected_sha = args.get("expected_sha256")
        expected_mtime = args.get("expected_mtime_ns")
        try:
            payload = apply_patch(
                root,
                patch_text,
                expected_sha256=expected_sha if isinstance(expected_sha, dict) else None,
                expected_mtime_ns=(
                    {str(k): int(v) for k, v in expected_mtime.items()}
                    if isinstance(expected_mtime, dict)
                    else None
                ),
            )
        except (OSError, ValueError) as exc:
            return err_result("project.apply_patch", str(exc))
        _log(window, "project.apply_patch", bool(payload.get("ok")))
        if payload.get("ok"):
            return ok_result("project.apply_patch", payload)
        return err_result(
            "project.apply_patch",
            "patch conflict",
            payload if isinstance(payload, dict) else {},
        )

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
        rendered["opened"] = open_diagram_preview(
            window, str(rendered["html_path"]), title=title
        )
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
        confirm_required=True,
    )

    reg.register(
        "project.delete",
        lambda args: project_delete(window, args),
        summary=(
            "Delete a project folder or a path under it. "
            "Required: project_root. Optional: rel_path (omit to delete the whole project_root "
            "when it is under a known project parent). "
            "Closes IDE Companion first when that folder is the open workspace (best-effort unlock). "
            "Prefer this over terminal rm/Remove-Item. Refuses home, drive roots, and the Iris repo."
        ),
        risk="high",
    )

    reg.register(
        "project.list_files",
        project_list_files,
        summary="List files in the bound IDE workspace (query = case-insensitive substring) — use this before open_file/run when the path is unknown",
    )

    reg.register(
        "project.read_file",
        project_read_file,
        summary=(
            "Read a UTF-8 file body from the bound IDE workspace disk "
            "(rel_path or path; optional start_line/end_line/max_bytes). "
            "Missing, escape, directory, binary/NUL, or too-large fail — never invent content. "
            "Disk bytes only; dirty Monaco buffers need ide.save / ide.edit first."
        ),
        risk="low",
    )

    reg.register(
        "project.apply_patch",
        project_apply_patch,
        summary=(
            "Apply a Hermes-style or unified-diff patch under the bound IDE workspace. "
            "Required: patch_text (or patch). Conflicts when expected context or disk "
            "fingerprint is missing. Disk-updated only; IDE buffer refresh is follow-up."
        ),
        risk="medium",
        confirm_required=True,
    )

    reg.register(
        "project.write_file",
        _with_run_visibility(
            window,
            "project.write_file",
            _first_class_ide_trigger(window, lambda args: project_write_file(window, args)),
        ),
        summary=(
            "Write file under the bound IDE workspace. "
            "rel_path and content are required and come from the user request. "
            "If the user did not name a file, ask before writing. "
            "open=true reveals the tab then streams chunks."
        ),
        risk="medium",
        confirm_required=True,
    )

    reg.register(
        "project.rename_file",
        _first_class_ide_trigger(window, lambda args: project_rename_file(window, args)),
        summary=(
            "Rename a file inside the open project. "
            "Required: path (current relative path), new_path (new relative path). "
            "Look up path with project.list_files or the open editor. "
            "If either path is unknown, ask. Do not invent a filename."
        ),
        risk="medium",
        confirm_required=True,
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
            "on failure the error data carries archify diagnostics[] — fix the IR and retry. "
            "Call only when the user asks for structure, flow, sequence, or architecture, "
            "or when explaining or summarizing a multi-module structural change. "
            "One call per turn. Not for a single-file edit, bugfix, or run result. "
            "Opens in the Iris chat column, not a separate window. "
            "Do not use the architecture-diagram skill or write a standalone HTML diagram"
        ),
    )

    reg.register(
        "project.run",
        _with_run_visibility(window, "project.run", lambda args: project_run(window, args)),
        summary=(
            "Run a command via the shared Execution Runtime (run_id + status). "
            "When reveal_terminal, mirror Runtime stdout/stderr into the bound IDE terminal "
            "(same run_id; does not re-execute)."
        ),
        risk="medium",
        confirm_required=True,
    )
    from iris.runtime.chat_worktree import register_worktree_status

    register_worktree_status(reg, window)
    from iris.engine.types import assert_dangerous_actions_confirm

    assert_dangerous_actions_confirm(reg)
