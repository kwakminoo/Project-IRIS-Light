"""Hermes가 직접 부르는 PDF·GitHub 확장·사진 코드 액션."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from iris.system.control_surface import ActionRegistry
from iris.ui.chat.file_write_claim import extracted_code, extract_image_code
from iris.ui.control_actions.project import project_write_file


def register_agent_turn_actions(window: Any, reg: ActionRegistry) -> None:
    from iris.ui.control_bindings import (
        _call_on_ui,
        _first_class_ide_trigger,
        err_result,
        ok_result,
    )

    def note_export_pdf(args: dict[str, Any]) -> dict[str, Any]:
        from iris.knowledge.pdf_export import save_pdf
        from iris.knowledge.pdf_job import compose_pdf_text, resolve_pdf_dest, source_list

        snap = _call_on_ui(window, lambda: _pdf_root(window))
        root = str(snap.get("project_root") or "") if isinstance(snap, dict) else ""
        content = compose_pdf_text(
            str(args.get("content") or ""),
            source_list(args),
            root,
        )
        if not content:
            return err_result("note.export_pdf", "content or sources required")
        dest = resolve_pdf_dest(str(args.get("path") or ""), root)
        saved = save_pdf(content, dest)
        if not saved.get("ok") or not dest.is_file():
            return err_result("note.export_pdf", str(saved.get("error") or "PDF 저장에 실패했습니다."))

        def _arm() -> None:
            window._turn_pdf_path = str(dest.resolve())

        _call_on_ui(window, _arm)
        return ok_result("note.export_pdf", {"path": str(dest.resolve())})

    def extension_install_github(args: dict[str, Any]) -> dict[str, Any]:
        from iris.system.github_extension_install import ExtensionRequest, install_from_request

        url = str(args.get("url") or "").strip()
        if not url:
            return err_result("extension.install_github", "url required")
        snap = _call_on_ui(window, lambda: _extension_context(window))
        if not isinstance(snap, dict):
            return err_result("extension.install_github", "scope unavailable")
        from iris.system.extension_scope import choose_extension_scope

        scope, scope_err = choose_extension_scope(
            str(snap.get("ui_mode") or ""),
            str(snap.get("project_root") or ""),
            str(args.get("scope") or ""),
        )
        if scope_err:
            return err_result("extension.install_github", scope_err)
        project_root = str(snap.get("project_root") or "") if scope == "project" else None
        kind = str(args.get("kind") or "auto").strip().lower()
        if kind not in ("auto", "mcp", "skill"):
            kind = "auto"
        secrets = args.get("secrets") if isinstance(args.get("secrets"), dict) else {}
        directory = str(args.get("directory") or "").strip() or None
        result = install_from_request(
            ExtensionRequest(url, kind),
            secrets={str(k): str(v) for k, v in secrets.items()},
            directory=directory,
            project_root=project_root,
        )
        data = result.to_dict()
        if result.status == "needs_input":
            pending = {
                "url": url,
                "kind": kind,
                "missing": list(result.missing_env),
                "need_dir": bool(result.need_dir) and not list(result.missing_env),
                "secrets": {str(k): str(v) for k, v in secrets.items()},
                "directory": directory or "",
            }

            def _arm() -> None:
                window._pending_ext = pending

            _call_on_ui(window, _arm)
            return ok_result("extension.install_github", data)
        if result.status in ("failed", "refused"):
            return err_result(
                "extension.install_github",
                result.message or "설치하지 못했습니다.",
                data,
            )
        data["scope"] = scope
        if result.mcp_added and scope == "iris":
            data["runtime"] = _restart_gateway(window)
        if result.status in ("installed", "already") and scope == "iris":
            def _sync() -> None:
                try:
                    from iris.ui.chat.skill_mcp_dialogs import _sync_wiki_catalog

                    _sync_wiki_catalog()
                except Exception:
                    pass

            _call_on_ui(window, _sync)
        return ok_result("extension.install_github", data)

    def project_write_image_code(args: dict[str, Any]) -> dict[str, Any]:
        image = str(args.get("image") or args.get("path") or "").strip()
        rel = str(args.get("rel_path") or args.get("rel") or "").strip()
        if not image:
            return err_result("project.write_image_code", "image required")
        if not Path(image).is_file():
            return err_result("project.write_image_code", "image file required")
        if not rel:
            return err_result("project.write_image_code", "rel_path required")
        snap = _call_on_ui(window, lambda: _vision_snap(window))
        if not isinstance(snap, dict) or not str(snap.get("model") or "").strip():
            return err_result("project.write_image_code", "model required")
        raw = extract_image_code(
            image,
            model=str(snap["model"]),
            ollama_base_url=str(snap.get("ollama_base_url") or ""),
            api_base_url=str(snap.get("api_base_url") or ""),
            api_key=str(snap.get("api_key") or ""),
            auth_style=str(snap.get("auth_style") or "bearer"),
        )
        code = extracted_code(raw)
        if not code:
            return err_result("project.write_image_code", "extraction had no code")
        root = str(args.get("project_root") or snap.get("project_root") or "").strip()
        payload = {
            "project_root": root,
            "rel_path": rel,
            "content": code,
            "open": True,
        }
        written = _write_on_ui(window, payload)
        if not isinstance(written, dict):
            return err_result("project.write_image_code", "write timed out")
        if not written.get("ok"):
            return err_result(
                "project.write_image_code",
                str(written.get("error") or "write failed"),
                written.get("result") if isinstance(written.get("result"), dict) else {},
            )
        out = dict(written)
        out["action"] = "project.write_image_code"
        return out

    reg.register(
        "note.export_pdf",
        note_export_pdf,
        summary="Make a PDF from content and/or source files. Required: content or sources. Optional path (open project, else Documents/IRIS/iris-note.pdf). Do not run PyMuPDF, reportlab, or pdf_create.py. Do not claim saved without ok and a real file.",
        risk="medium",
    )
    reg.register(
        "extension.install_github",
        extension_install_github,
        summary="Install a GitHub repo as MCP and/or skill. Required: url. kind=auto|mcp|skill. scope=project only in IRIS IDE (writes the open project). scope=iris only on the main Iris screen (Hermes). needs_input: ask and do not invent secrets. Do not claim installed without ok. Do not treat an IDE extension and a Hermes MCP as one install.",
        risk="medium",
    )
    reg.register(
        "project.write_image_code",
        _first_class_ide_trigger(window, project_write_image_code),
        summary="Read code from an image file and write it via project.write_file. Required: image (file path), rel_path. Ask when the target file is unknown. Do not claim written without ok.",
        risk="medium",
    )


def _pdf_root(window: Any) -> dict[str, str]:
    root = ""
    try:
        root = str(window._current_project_root() or "")
    except Exception:
        root = ""
    return {"project_root": root}


def _extension_context(window: Any) -> dict[str, str]:
    root = ""
    try:
        root = str(window._current_project_root() or "")
    except Exception:
        root = ""
    session = getattr(window, "_ide_session", None)
    bound = str(getattr(session, "workspace_root", "") or "").strip() if session is not None else ""
    if bound:
        root = bound
    return {"ui_mode": str(getattr(window, "_ui_mode", "") or ""), "project_root": root}


def _vision_snap(window: Any) -> dict[str, str]:
    from iris.storage.api_providers import get_api_provider, parse_runtime_model_id
    from iris.storage.user_profile import load_user_profile

    settings = window._settings
    model = ""
    chat = getattr(window, "_chat", None)
    current = getattr(chat, "current_model", None)
    if callable(current):
        model = str(current() or "").strip()
    if not model:
        model = str(getattr(window, "_saved_model", None) or "").strip()
    if not model:
        model = str(getattr(settings, "ollama_model", None) or "").strip()
    api_base = ""
    api_key = ""
    auth_style = "bearer"
    vision_model = model
    parsed = parse_runtime_model_id(model) if model else None
    if parsed is not None:
        provider = get_api_provider(getattr(window, "_db", None), parsed[0])
        vision_model = parsed[1]
        if provider is not None and provider.base_url:
            api_base = provider.base_url
            api_key = provider.api_key
            auth_style = provider.auth_style or "bearer"
    project_root = ""
    try:
        project_root = (load_user_profile(window._db).project_root or "").strip()
    except Exception:
        project_root = ""
    return {
        "model": vision_model,
        "ollama_base_url": str(getattr(settings, "ollama_base_url", "") or ""),
        "api_base_url": api_base,
        "api_key": api_key,
        "auth_style": auth_style,
        "project_root": project_root,
    }


def _write_on_ui(window: Any, payload: dict[str, Any]) -> dict[str, Any] | None:
    qt = getattr(window, "_control_qt_invoker", None)
    if qt is None:
        return project_write_file(window, payload)
    try:
        out = qt.run(lambda: project_write_file(window, payload), timeout=120.0)
    except Exception as exc:  # noqa: BLE001
        from iris.ui.control_bindings import err_result

        return err_result("project.write_image_code", str(exc)[:300])
    return out if isinstance(out, dict) else None


def _restart_gateway(window: Any) -> str:
    settings = window._settings
    try:
        from iris.system.hermes_gateway import restart_hermes_gateway

        ok = restart_hermes_gateway(
            str(getattr(settings, "hermes_base_url", "") or ""),
            api_key=str(getattr(settings, "hermes_api_key", "") or ""),
            command=str(getattr(settings, "hermes_command", "") or "hermes"),
            wait_sec=60.0,
        )
    except Exception as exc:  # noqa: BLE001
        return f"설정은 저장됐지만 gateway 재시작에 실패했습니다: {exc}"[:300]
    if ok:
        return "Hermes gateway를 재시작했습니다. 이제 이 MCP 도구를 사용할 수 있습니다."
    return "설정은 저장됐지만 gateway 재시작에 실패했습니다. Hermes를 다시 켜면 적용됩니다."
